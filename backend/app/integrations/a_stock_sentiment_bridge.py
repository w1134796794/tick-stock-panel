"""兼容导入层：因子已改为 stock-panel 原生计算，不再连接外部数据库。"""

from __future__ import annotations

from pathlib import Path

from app.integrations.a_stock_sentiment.native_pipeline import (
    NativeFactorResult as SyncResult,
)
from app.integrations.a_stock_sentiment.native_pipeline import (
    compute_native_factor_partitions,
)
from app.integrations.a_stock_sentiment.registry import (
    CONFIG_ID,
    STOCK_FACTOR_IDS,
    STOCK_FACTOR_LABELS,
    STRATEGY_CONTEXT_CONFIG_ID,
    STRATEGY_CONTEXT_IDS,
    STRATEGY_CONTEXT_LABELS,
    register_native_tables,
    registered_factor_ids,
    strategy_context_factor_ids,
)

# 旧名称仅供已生成策略/第三方扩展导入；现在全部字段都由本地计算器负责。
SOURCE_MATERIALIZED_FACTORS = frozenset(STOCK_FACTOR_IDS)


def register_factor_table(data_dir: Path):
    return register_native_tables(Path(data_dir))[0]


def register_strategy_context_table(data_dir: Path):
    return register_native_tables(Path(data_dir))[1]


def sync_factor_partitions(*args, **kwargs):
    raise RuntimeError(
        "外部数据库同步桥已停用；请调用 compute_native_factor_partitions(data_dir, start=..., end=...)"
    )


__all__ = [
    "CONFIG_ID",
    "SOURCE_MATERIALIZED_FACTORS",
    "STOCK_FACTOR_IDS",
    "STOCK_FACTOR_LABELS",
    "STRATEGY_CONTEXT_CONFIG_ID",
    "STRATEGY_CONTEXT_IDS",
    "STRATEGY_CONTEXT_LABELS",
    "SyncResult",
    "compute_native_factor_partitions",
    "register_factor_table",
    "register_strategy_context_table",
    "registered_factor_ids",
    "strategy_context_factor_ids",
]
