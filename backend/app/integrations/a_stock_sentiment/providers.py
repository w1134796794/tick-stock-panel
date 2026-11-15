"""可选增强因子插件契约。

提供者只返回其真实拥有的逐股日频数值。未注册提供者或缺失字段保持 null，
禁止用 0/50 冒充可用数据。eltdx/axdata/fuyao 可按此契约逐步增加实现。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import polars as pl

Provider = Callable[[date], pl.DataFrame]
_providers: dict[str, Provider] = {}


def register_provider(dataset: str, provider: Provider) -> None:
    if not dataset or not callable(provider):
        raise ValueError("dataset 和 provider 必须有效")
    _providers[dataset] = provider


def unregister_provider(dataset: str) -> None:
    _providers.pop(dataset, None)


def load_provider_frame(dataset: str, trade_date: date) -> pl.DataFrame:
    provider = _providers.get(dataset)
    if provider is None:
        # 正式数据源插件可选择实现 get_<dataset>_factors(date)；无需让因子层
        # 知道插件名，也不把 eltdx/axdata/fuyao SDK 引入计算模块。
        try:
            from app.data_providers import custom as custom_sources

            method_name = f"get_{dataset}_factors"
            for source in custom_sources.list_sources():
                if not source.get("available"):
                    continue
                candidate = custom_sources.get_provider(str(source["name"]))
                method = getattr(candidate, method_name, None)
                if callable(method):
                    provider = method
                    break
        except Exception:  # noqa: BLE001 - 插件发现失败按未提供处理
            provider = None
    if provider is None:
        return pl.DataFrame(schema={"symbol": pl.Utf8})
    frame = provider(trade_date)
    if not isinstance(frame, pl.DataFrame) or "symbol" not in frame.columns:
        raise ValueError(f"因子插件 {dataset} 必须返回含 symbol 的 Polars DataFrame")
    return frame.unique("symbol", keep="last")


def registered_datasets() -> tuple[str, ...]:
    return tuple(sorted(_providers))
