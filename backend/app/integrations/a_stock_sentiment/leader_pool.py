"""基于本地每日因子结果滚动生成历史龙头资格。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from app.factors.ext_factors import ensure_synced
from app.services.ext_data import (
    ExtConfig,
    ExtConfigStore,
    ExtField,
    apply_config_mapping,
    write_ext_parquet,
)

from .registry import (
    CONFIG_ID,
    GROUP_LEADER,
    LEADER_POOL_CONFIG_ID,
    STRATEGY_CONTEXT_CONFIG_ID,
)

LEADER_POOL_FIELD = "eligible"


def _config(data_dir: Path) -> ExtConfig:
    store = ExtConfigStore(data_dir)
    old = store.get(LEADER_POOL_CONFIG_ID)
    config = ExtConfig(
        id=LEADER_POOL_CONFIG_ID,
        label="本地历史龙头池",
        mode="timeseries",
        fields=[
            ExtField(
                LEADER_POOL_FIELD,
                "float",
                "前20交易日历史龙头资格",
                factor_group=GROUP_LEADER,
            )
        ],
        description="由 stock-panel 本地因子与交易日历滚动计算；目标日只使用此前20个交易日。",
        symbol_map={"type": "computed", "from": "code", "method": "append_exchange"},
        code_map={"type": "mapped", "col": "code"},
        created_at=old.created_at if old else None,
        updated_at=old.updated_at if old else None,
    )
    if old is None or old.to_dict() != config.to_dict():
        store.upsert(config)
    ensure_synced(data_dir)
    return config


def _part(data_dir: Path, config_id: str, d: date) -> Path:
    return (
        data_dir / "ext_data" / config_id / "timeseries" / f"date={d.isoformat()}" / "part.parquet"
    )


def rebuild_native_leader_pool(
    data_dir: Path, trade_date: date, *, lookback: int = 20
) -> tuple[int, int]:
    """写入目标日资格；严格排除目标日，避免未来/当日信息泄漏。"""
    data_dir = Path(data_dir)
    config = _config(data_dir)
    factor_root = data_dir / "ext_data" / CONFIG_ID / "timeseries"
    prior = sorted(
        date.fromisoformat(p.name[5:])
        for p in factor_root.glob("date=*")
        if p.is_dir() and date.fromisoformat(p.name[5:]) < trade_date
    )[-max(1, int(lookback)) :]
    leaders: set[str] = set()
    for d in prior:
        fp = _part(data_dir, CONFIG_ID, d)
        cp = _part(data_dir, STRATEGY_CONTEXT_CONFIG_ID, d)
        if not fp.exists() or not cp.exists():
            continue
        factors = pl.read_parquet(fp)
        context = pl.read_parquet(cp).select(
            "symbol",
            "board_height",
            "stk_sector_mainline_score",
            "limit_progress",
        )
        rows = factors.join(context, on="symbol", how="left").filter(
            (pl.col("board_height") >= 2)
            | (pl.col("stk_mainline_leader_identity") >= 66)
            | ((pl.col("limit_progress") >= 0.95) & (pl.col("stk_sector_mainline_score") >= 65))
            | (
                (pl.col("stk_behavior_attention") >= 65)
                & (pl.col("stk_behavior_acceleration") >= 60)
            )
            | (pl.col("stk_first_board_resonance_score") >= 65)
        )
        leaders.update(rows["symbol"].drop_nulls().to_list())
    current_path = _part(data_dir, STRATEGY_CONTEXT_CONFIG_ID, trade_date)
    if not current_path.exists():
        return 0, 0
    current = pl.read_parquet(current_path, columns=["code", "symbol"])
    frame = current.with_columns(
        pl.col("symbol").is_in(sorted(leaders)).cast(pl.Float64).alias(LEADER_POOL_FIELD)
    )
    rows = write_ext_parquet(
        apply_config_mapping(frame, config, data_dir),
        config,
        data_dir,
        snapshot_date=trade_date,
        replace_existing=True,
    )
    return len(prior), rows
