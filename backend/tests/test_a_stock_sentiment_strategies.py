from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
import yaml

from app.backtest.strategy import StrategyBacktestService
from app.integrations.a_stock_sentiment_strategies import (
    migrate_strategies,
    render_strategy_report,
    sync_leader_pool_export,
    target_factor_id,
)
from app.strategy import config as strategy_config
from app.strategy.engine import StrategyDataContext, StrategyEngine


def _write_source(tmp_path: Path) -> tuple[Path, Path]:
    combinations = tmp_path / "strategy_combinations.yaml"
    profiles = tmp_path / "screening_profiles.yaml"
    combinations.write_text(
        yaml.safe_dump({
            "strategies": {
                "demo": {
                    "name": "演示策略",
                    "enabled": True,
                    "base_profile": "default",
                    "veto_rules": [
                        {"factor": "stk_behavior_decay", "op": ">=", "value": 70},
                    ],
                    "evidence_rules": [
                        {"factor": "stk_behavior_decay", "op": "<", "value": 50, "name": "衰退风险低"},
                        {
                            "factor": "stk_capital_flow_consensus",
                            "op": ">=",
                            "value": 55,
                            "name": "资金共识",
                        },
                    ],
                    "enhancements": {"capital_flow": True},
                    "execution": {
                        "allowed_entry_modes": ["weak_to_strong"],
                        "confirmation_deadline": "10:00:00",
                        "exit": {
                            "hard_stop_loss": 0.04,
                            "trailing_activation": 0.03,
                            "trailing_early_stop": 0.02,
                            "trailing_mid_profit": 0.08,
                            "trailing_mid_stop": 0.04,
                            "trailing_high_profit": 0.15,
                            "trailing_stop": 0.06,
                            "time_stop_days": 4,
                        },
                    },
                },
            },
        }, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    profiles.write_text(
        yaml.safe_dump({
            "screening_profiles": {
                "default": {
                    "hard_filters": [
                        {"factor": "stk_behavior_repair", "op": ">=", "value": 55},
                    ],
                    "priority_filters": [
                        {
                            "factor": "stk_behavior_repair",
                            "op": ">=",
                            "value": 70,
                            "priority": 1,
                            "min_keep": 2,
                        },
                    ],
                    "ranking": {
                        "weights": {
                            "stk_behavior_repair": 0.6,
                            "stk_behavior_decay": -0.4,
                            "stk_capital_flow_consensus": 0.2,
                        },
                        "top_n": 8,
                    },
                },
            },
        }, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return combinations, profiles


def test_migrate_strategy_resolves_inheritance_and_loads(tmp_path: Path) -> None:
    combinations, profiles = _write_source(tmp_path)
    data_dir = tmp_path / "data"

    migrations = migrate_strategies(combinations, profiles, data_dir)

    assert [item.source_id for item in migrations] == ["demo"]
    strategy_id = "custom_ass_demo"
    engine = StrategyEngine(strategy_dirs=[data_dir / "strategies" / "custom"])
    strategy = engine.get(strategy_id)
    assert strategy is not None
    assert strategy.stop_loss == -0.04
    assert strategy.max_hold_days == 4
    assert strategy.tiered_trailing == ((0.03, 0.02), (0.08, 0.04), (0.15, 0.06))
    assert strategy.meta["limit"] == 8
    assert engine.load_errors() == []

    repair = target_factor_id("stk_behavior_repair")
    decay = target_factor_id("stk_behavior_decay")
    frame = pl.DataFrame({
        repair: [60.0, 50.0, 80.0],
        decay: [20.0, 20.0, 80.0],
    })
    assert strategy.filter_fn is not None
    assert frame.filter(strategy.filter_fn(frame, {})).height == 1

    assert strategy.post_score_fn is not None
    assert strategy.optional_features == frozenset({
        target_factor_id("stk_capital_flow_consensus")
    })
    staged = strategy.post_score_fn(
        pl.DataFrame({
            "symbol": ["A", "B", "C"],
            repair: [60.0, 50.0, 80.0],
            decay: [20.0, 20.0, 80.0],
            target_factor_id("stk_capital_flow_consensus"): [None, None, None],
            "score": [50.0, 90.0, 80.0],
        }),
        {},
    ).sort("symbol")
    assert staged["symbol"].to_list() == ["B", "C"]
    assert staged["ass_priority_relaxed_count"].to_list() == [1, 0]
    assert staged["ass_evidence_passed"].to_list() == [1, 0]
    assert staged["ass_evidence_gaps"].to_list() == ["资金共识", "衰退风险低；资金共识"]

    override = strategy_config.load_override(data_dir, strategy_id)
    runtime_frame = pl.DataFrame({
        "symbol": ["000001.SZ"],
        "date": [date(2024, 1, 2)],
        "name": ["测试股票"],
        "close": [10.0],
        "amount": [100_000_000.0],
        "total_market_cap": [10_000_000_000.0],
        "is_st": [False],
        "listing_days": [1000],
        repair: [80.0],
        decay: [20.0],
        target_factor_id("stk_capital_flow_consensus"): [None],
    })
    result = engine.run(
        strategy_id,
        StrategyDataContext(
            asset_type="stock",
            timeframe="1d",
            as_of=date(2024, 1, 2),
            current=runtime_frame,
        ),
        overrides=override,
    )
    assert result.total == 1
    assert result.rows[0]["ass_evidence_gaps"] == "资金共识"
    with pytest.raises(ValueError, match="stk_behavior_repair"):
        engine.run(
            strategy_id,
            StrategyDataContext(
                asset_type="stock",
                timeframe="1d",
                as_of=date(2024, 1, 2),
                current=runtime_frame.with_columns(
                    pl.lit(None).cast(pl.Float64).alias(repair)
                ),
            ),
            overrides=override,
        )

    two_days = pl.concat([
        staged.with_columns(pl.lit(date(2024, 1, 2)).alias("date")),
        staged.with_columns(pl.lit(date(2024, 1, 2) + timedelta(days=1)).alias("date")),
    ])
    _, post_mask = StrategyBacktestService._apply_post_score(
        two_days,
        pl.Series([True] * two_days.height),
        strategy,
        {},
    )
    assert post_mask.sum() == 4

    assert override["scoring_directions"] == {decay: "low"}
    assert set(override["scoring"]) == {
        repair,
        decay,
        target_factor_id("stk_capital_flow_consensus"),
    }
    report = render_strategy_report(migrations, {"demo": 1})
    assert "custom_ass_demo" in report
    assert "最新候选" in report


def test_migration_refuses_to_overwrite_user_strategy(tmp_path: Path) -> None:
    combinations, profiles = _write_source(tmp_path)
    destination = tmp_path / "data" / "strategies" / "custom"
    destination.mkdir(parents=True)
    (destination / "custom_ass_demo.py").write_text("# user file\n", encoding="utf-8")

    try:
        migrate_strategies(combinations, profiles, tmp_path / "data")
    except FileExistsError as exc:
        assert "拒绝覆盖" in str(exc)
    else:
        raise AssertionError("user strategy should not be overwritten")


def test_migrated_strategy_fails_closed_when_ext_values_are_unavailable(tmp_path: Path) -> None:
    combinations, profiles = _write_source(tmp_path)
    data_dir = tmp_path / "data"
    migrate_strategies(combinations, profiles, data_dir)
    engine = StrategyEngine(strategy_dirs=[data_dir / "strategies" / "custom"])
    as_of = date(2024, 1, 2)
    context = StrategyDataContext(
        asset_type="stock",
        timeframe="1d",
        as_of=as_of,
        current=pl.DataFrame({
            "symbol": ["000001.SZ"],
            "date": [as_of],
            target_factor_id("stk_behavior_repair"): [None],
            target_factor_id("stk_behavior_decay"): [None],
        }),
    )

    with pytest.raises(ValueError, match="扩展时序数据按交易日精确对齐"):
        engine.run("custom_ass_demo", context)


def test_sync_leader_pool_export_writes_sparse_point_in_time_rows(tmp_path: Path) -> None:
    export = tmp_path / "leader_pool.json"
    export.write_text(json.dumps({
        "schema": "a-stock-sentiment-leader-pool/v1",
        "dates": [
            {"trade_date": "20240102", "codes": ["000001", "600000"]},
            {"trade_date": "20240103", "codes": []},
        ],
    }), encoding="utf-8")

    dates, rows = sync_leader_pool_export(export, tmp_path / "data")

    assert (dates, rows) == (1, 2)
    path = (
        tmp_path / "data" / "ext_data" / "a_stock_sentiment_leader_pool"
        / "timeseries" / "date=2024-01-02" / "part.parquet"
    )
    frame = pl.read_parquet(path).sort("symbol")
    assert frame["symbol"].to_list() == ["000001.SZ", "600000.SH"]
    assert frame["eligible"].to_list() == [1.0, 1.0]
    assert target_factor_id("stk_historical_leader_pool_eligible") == (
        "ext_a_stock_sentiment_leader_pool_eligible"
    )

    export.write_text(json.dumps({
        "schema": "a-stock-sentiment-leader-pool/v1",
        "dates": [{"trade_date": "20240102", "codes": ["000001"]}],
    }), encoding="utf-8")
    sync_leader_pool_export(export, tmp_path / "data")
    replaced = pl.read_parquet(path)
    assert replaced["symbol"].to_list() == ["000001.SZ"]
