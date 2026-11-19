from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl

from app.factors.ext_factors import ext_factor_specs
from app.integrations.a_stock_sentiment.leader_pool import rebuild_native_leader_pool
from app.integrations.a_stock_sentiment.native_pipeline import compute_native_factor_partitions
from app.integrations.a_stock_sentiment.providers import register_provider, unregister_provider
from app.integrations.a_stock_sentiment.registry import (
    CONFIG_ID,
    FACTOR_GROUPS,
    STOCK_FACTOR_IDS,
    STRATEGY_CONTEXT_CONFIG_ID,
    STRATEGY_CONTEXT_GROUPS,
    STRATEGY_CONTEXT_IDS,
)
from app.services.ext_data import ExtConfigStore


def _local_data(root: Path, days: int = 65, symbol_count: int = 2) -> date:
    data = root / "data"
    start = date(2024, 1, 2)
    symbols = (
        ["000001.SZ", "600000.SH"]
        if symbol_count == 2
        else [f"{index:06d}.SZ" for index in range(1, symbol_count + 1)]
    )
    for offset in range(days):
        d = start + timedelta(days=offset)
        rows = []
        for index, symbol in enumerate(symbols):
            close = 10 + offset * 0.1 + index
            rows.append(
                {
                    "symbol": symbol,
                    "date": d,
                    "open": close - 0.05,
                    "high": close + 0.1,
                    "low": close - 0.1,
                    "close": close,
                    "volume": 1000 + offset * 10,
                    "amount": (1000 + offset * 10) * close,
                    "turnover_rate": 5.0,
                    "consecutive_limit_ups": 0,
                    "consecutive_limit_downs": 0,
                }
            )
        part = data / "kline_daily_enriched" / f"date={d.isoformat()}" / "part.parquet"
        part.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(rows).write_parquet(part)
    inst = data / "instruments" / "instruments.parquet"
    inst.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": symbols,
            "name": [f"测试{index}" for index in range(len(symbols))],
            "float_shares": [1e9 + index * 1e6 for index in range(len(symbols))],
        }
    ).write_parquet(inst)
    return start + timedelta(days=days - 1)


def test_native_pipeline_registers_and_calculates_all_local_contracts(tmp_path: Path) -> None:
    last = _local_data(tmp_path)
    result = compute_native_factor_partitions(tmp_path / "data", start=last, end=last)
    assert result.factor_rows == 2 and result.context_rows == 2
    assert len(STOCK_FACTOR_IDS) == 42 and len(STRATEGY_CONTEXT_IDS) == 20
    factors = pl.read_parquet(
        tmp_path / "data" / "ext_data" / CONFIG_ID / "timeseries" / f"date={last}" / "part.parquet"
    )
    context = pl.read_parquet(
        tmp_path
        / "data"
        / "ext_data"
        / STRATEGY_CONTEXT_CONFIG_ID
        / "timeseries"
        / f"date={last}"
        / "part.parquet"
    )
    assert factors.columns == ["code", *STOCK_FACTOR_IDS, "symbol"]
    assert context.columns == ["code", *STRATEGY_CONTEXT_IDS, "symbol"]
    assert factors["D1_n_day_high_low"].null_count() == 0
    assert factors["D5_ma_bull_align"].to_list() == [100.0, 100.0]
    assert factors["E1_main_net_ratio"].null_count() == 2  # 无插件不伪造
    assert context["stk_amount_ratio_5d"].null_count() == 0


def test_native_factor_catalog_is_split_into_semantic_groups(tmp_path: Path) -> None:
    last = _local_data(tmp_path)
    data_dir = tmp_path / "data"
    compute_native_factor_partitions(data_dir, start=last, end=last)
    configs = {config.id: config for config in ExtConfigStore(data_dir).load_all()}

    factor_fields = {field.name: field.factor_group for field in configs[CONFIG_ID].fields}
    context_fields = {
        field.name: field.factor_group
        for field in configs[STRATEGY_CONTEXT_CONFIG_ID].fields
    }
    assert factor_fields == FACTOR_GROUPS
    assert context_fields == STRATEGY_CONTEXT_GROUPS

    native_specs = [
        spec for spec in ext_factor_specs(data_dir)
        if spec.id.startswith(f"ext_{CONFIG_ID}_")
        or spec.id.startswith(f"ext_{STRATEGY_CONTEXT_CONFIG_ID}_")
    ]
    assert len(native_specs) == 62
    assert {spec.id: spec.label for spec in native_specs} == {
        f"ext_{table_id}_{field.name}": field.label
        for table_id in (CONFIG_ID, STRATEGY_CONTEXT_CONFIG_ID)
        for field in configs[table_id].fields
    }
    assert {spec.group for spec in native_specs} == {
        "扩展·技术量价",
        "扩展·涨停与接力",
        "扩展·板块与主线",
        "扩展·资金流与交易",
        "扩展·情绪与行为",
        "扩展·龙虎榜与龙头",
        "扩展·市场环境",
    }
    assert all(spec.group != "扩展数据" for spec in native_specs)


def test_native_factor_frame_handles_late_float_after_null_inference_window(
    tmp_path: Path,
) -> None:
    """线上回归：前100只缺流通股本、后续才出现小数值时不得推断成 Null 列。"""
    last = _local_data(tmp_path, symbol_count=101)
    instruments = tmp_path / "data" / "instruments" / "instruments.parquet"
    pl.read_parquet(instruments).tail(1).write_parquet(instruments)

    result = compute_native_factor_partitions(tmp_path / "data", start=last, end=last)

    assert result.factor_rows == 101
    factors = pl.read_parquet(
        tmp_path / "data" / "ext_data" / CONFIG_ID
        / "timeseries" / f"date={last}" / "part.parquet"
    )
    assert factors["stk_float_mv_fit"].null_count() == 100
    assert factors["stk_float_mv_fit"].drop_nulls().dtype == pl.Float64


def test_native_moneyflow_provider_overrides_only_real_fields(tmp_path: Path) -> None:
    last = _local_data(tmp_path)
    register_provider(
        "moneyflow",
        lambda _: pl.DataFrame(
            {
                "symbol": ["000001.SZ"],
                "E1_main_net_ratio": [12.5],
                "E4_moneyflow_trend": [80.0],
            }
        ),
    )
    try:
        compute_native_factor_partitions(tmp_path / "data", start=last, end=last)
    finally:
        unregister_provider("moneyflow")
    factors = pl.read_parquet(
        tmp_path / "data" / "ext_data" / CONFIG_ID / "timeseries" / f"date={last}" / "part.parquet"
    )
    assert factors.filter(pl.col("symbol") == "000001.SZ")["E1_main_net_ratio"][0] == 12.5
    assert factors.filter(pl.col("symbol") == "600000.SH")["E1_main_net_ratio"][0] is None


def test_leader_pool_uses_prior_sessions_only(tmp_path: Path) -> None:
    last = _local_data(tmp_path)
    compute_native_factor_partitions(tmp_path / "data", start=last, end=last)
    prior = last - timedelta(days=1)
    compute_native_factor_partitions(tmp_path / "data", start=prior, end=prior)
    factor_path = (
        tmp_path / "data" / "ext_data" / CONFIG_ID / "timeseries" / f"date={prior}" / "part.parquet"
    )
    frame = pl.read_parquet(factor_path).with_columns(
        pl.when(pl.col("symbol") == "000001.SZ")
        .then(90.0)
        .otherwise(0.0)
        .alias("stk_mainline_leader_identity"),
        pl.when(pl.col("symbol") == "000001.SZ")
        .then(pl.col("stk_behavior_attention"))
        .otherwise(0.0)
        .alias("stk_behavior_attention"),
        pl.when(pl.col("symbol") == "000001.SZ")
        .then(pl.col("stk_behavior_acceleration"))
        .otherwise(0.0)
        .alias("stk_behavior_acceleration"),
        pl.when(pl.col("symbol") == "000001.SZ")
        .then(pl.col("stk_first_board_resonance_score"))
        .otherwise(0.0)
        .alias("stk_first_board_resonance_score"),
    )
    frame.write_parquet(factor_path)
    days, rows = rebuild_native_leader_pool(tmp_path / "data", last)
    assert days == 1 and rows == 2
    pool = pl.read_parquet(
        tmp_path
        / "data"
        / "ext_data"
        / "a_stock_sentiment_leader_pool"
        / "timeseries"
        / f"date={last}"
        / "part.parquet"
    )
    assert pool.sort("symbol")["eligible"].to_list() == [1.0, 0.0]
    pool_spec = next(
        spec for spec in ext_factor_specs(tmp_path / "data")
        if spec.id == "ext_a_stock_sentiment_leader_pool_eligible"
    )
    assert pool_spec.group == "扩展·龙虎榜与龙头"
