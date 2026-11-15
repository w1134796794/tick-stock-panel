from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl

from app.integrations.a_stock_sentiment.leader_pool import rebuild_native_leader_pool
from app.integrations.a_stock_sentiment.native_pipeline import compute_native_factor_partitions
from app.integrations.a_stock_sentiment.providers import register_provider, unregister_provider
from app.integrations.a_stock_sentiment.registry import (
    CONFIG_ID,
    STOCK_FACTOR_IDS,
    STRATEGY_CONTEXT_CONFIG_ID,
    STRATEGY_CONTEXT_IDS,
)


def _local_data(root: Path, days: int = 65) -> date:
    data = root / "data"
    start = date(2024, 1, 2)
    symbols = ["000001.SZ", "600000.SH"]
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
        {"symbol": symbols, "name": ["平安银行", "浦发银行"], "float_shares": [1e9, 2e9]}
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
