"""eltdx built-in optional data-source provider.

The provider is intentionally imported without importing :mod:`eltdx` at module
scope.  A build without the optional native wheel can therefore still discover
the card and report a useful pending reason instead of failing application
startup.

Implemented datasets:
  - realtime: full A-share snapshots in native batches
  - depth5: five-level books from the quote refresh endpoint
  - daily: raw-price stock/index daily OHLCV
  - minute: raw-price stock/index one-minute OHLCV
  - full_minute: current-day repair batches and small latest-bar batches

Unit contract:
  - ``volume_lots`` / quote ``total_hand`` are already lots (手)
  - ``amount`` is already yuan
  - realtime ``change_pct`` is the internal decimal ratio, not percentage points
  - native aware datetimes are stored as naive Asia/Shanghai wall-clock values
"""

from __future__ import annotations

import contextlib
import importlib.util
import logging
import math
import os
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from app.data_providers.base import ProviderRequestError

logger = logging.getLogger(__name__)

_DATASETS = ("realtime", "depth5", "daily", "minute", "full_minute")
_BEIJING = ZoneInfo("Asia/Shanghai")
_QUOTE_BATCH = 80
_BAR_BATCH = 75
_PAGE_SIZE = 800
_MAX_DAILY_BARS = 3000
_MAX_MINUTE_BARS = 12_000
_BAR_ASSET_TYPES = {"stock", "index"}

_DAILY_SCHEMA = {
    "symbol": pl.String,
    "date": pl.Date,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
    "amount": pl.Float64,
}
_MINUTE_SCHEMA = {
    "symbol": pl.String,
    "datetime": pl.Datetime("us"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "amount": pl.Float64,
}


def _module_available() -> bool:
    try:
        return importlib.util.find_spec("eltdx") is not None
    except Exception:  # noqa: BLE001 - a damaged native install may raise here
        return False


def availability() -> tuple[bool, str]:
    """Cold discovery check; never opens a market-data connection."""
    if not _module_available():
        return False, "eltdx 未安装（设置 BACKEND_EXTRAS=eltdx 后重建）"
    return True, "ok"


@dataclass
class _EltdxConfig:
    name: str = "eltdx"
    display_name: str = "eltdx"
    datasets: dict = field(default_factory=lambda: dict.fromkeys(_DATASETS))
    path: None = None
    builtin: bool = True


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _native_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    code = text.split(".", 1)[0]
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"非法 A 股代码: {symbol!r}")
    if text.endswith(".SH"):
        prefix = "sh"
    elif text.endswith(".BJ"):
        prefix = "bj"
    elif text.endswith(".SZ"):
        prefix = "sz"
    else:
        prefix = "sh" if code.startswith(("5", "6", "9")) else "bj" if code.startswith(("4", "8")) else "sz"
    return f"{prefix}{code}"


def _canonical_symbol(value: str, exchange: str | None = None) -> str:
    text = str(value or "").strip().lower()
    prefix = text[:2] if text[:2] in {"sh", "sz", "bj"} else str(exchange or "").lower()
    code = text[-6:]
    suffix = {"sh": ".SH", "sz": ".SZ", "bj": ".BJ"}.get(prefix)
    if suffix is None or len(code) != 6 or not code.isdigit():
        raise ValueError(f"eltdx 返回非法代码: {value!r}")
    return f"{code}{suffix}"


def _wall_clock(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(_BEIJING).replace(tzinfo=None)
    return value


def _quote_record(snapshot: Any, fallback_ms: int) -> dict | None:
    symbol = _canonical_symbol(getattr(snapshot, "code", ""), getattr(snapshot, "exchange", ""))
    last = _float(getattr(snapshot, "last_price", None))
    prev = _float(getattr(snapshot, "pre_close_price", None))
    if last is None and prev is None:
        return None
    change = last - prev if last is not None and prev is not None else None
    return {
        "symbol": symbol,
        "name": None,
        "last_price": last,
        "prev_close": prev,
        "open": _float(getattr(snapshot, "open_price", None)),
        "high": _float(getattr(snapshot, "high_price", None)),
        "low": _float(getattr(snapshot, "low_price", None)),
        "volume": int(getattr(snapshot, "total_hand", 0) or 0),
        "amount": _float(getattr(snapshot, "amount", None)),
        "change_pct": change / prev if change is not None and prev else None,
        "change_amount": change,
        "amplitude": None,
        "turnover_rate": None,
        # eltdx documents time_raw as an opaque protocol value.  Freshness uses
        # successful receive time rather than pretending it is HHMMSS.
        "timestamp": fallback_ms,
        "session": None,
    }


def _daily_rows(symbol: str, bars: list[Any], start_d: date | None, end_d: date) -> list[dict]:
    rows = []
    for bar in bars:
        stamp = getattr(bar, "time", None)
        if not isinstance(stamp, datetime):
            continue
        day = _wall_clock(stamp).date()
        if (start_d is not None and day < start_d) or day > end_d:
            continue
        volume = _float(getattr(bar, "volume_lots", None))
        rows.append({
            "symbol": symbol,
            "date": day,
            "open": _float(getattr(bar, "open", None)),
            "high": _float(getattr(bar, "high", None)),
            "low": _float(getattr(bar, "low", None)),
            "close": _float(getattr(bar, "close", None)),
            "volume": math.floor(volume) if volume is not None else None,
            "amount": _float(getattr(bar, "amount", None)),
        })
    return rows


def _minute_rows(
    symbol: str,
    bars: list[Any],
    start_dt: datetime | None,
    end_dt: datetime | None,
) -> list[dict]:
    if start_dt is not None:
        start_dt = _wall_clock(start_dt)
    if end_dt is not None:
        end_dt = _wall_clock(end_dt)
    rows = []
    for bar in bars:
        stamp = getattr(bar, "time", None)
        if not isinstance(stamp, datetime):
            continue
        stamp = _wall_clock(stamp)
        if (start_dt is not None and stamp < start_dt) or (end_dt is not None and stamp > end_dt):
            continue
        rows.append({
            "symbol": symbol,
            "datetime": stamp,
            "open": _float(getattr(bar, "open", None)),
            "high": _float(getattr(bar, "high", None)),
            "low": _float(getattr(bar, "low", None)),
            "close": _float(getattr(bar, "close", None)),
            "volume": _float(getattr(bar, "volume_lots", None)),
            "amount": _float(getattr(bar, "amount", None)),
        })
    return rows


class EltdxProvider:
    """Optional eltdx provider implementing the stock-panel plugin contract."""

    name = "eltdx"
    builtin = True

    def __init__(self) -> None:
        self.config = _EltdxConfig()
        self._client: Any = None
        self._client_lock = threading.RLock()

    def _get_client(self):
        with self._client_lock:
            if self._client is None:
                from eltdx import TdxClient

                host = os.getenv("ELTDX_HOST", "").strip()
                try:
                    timeout = max(float(os.getenv("ELTDX_TIMEOUT_SECONDS", "5") or 5), 1.0)
                except ValueError:
                    timeout = 5.0
                self._client = TdxClient(
                    timeout=timeout,
                    host=host or None,
                    probe_hosts=not bool(host),
                    pool_size=4,
                )
            return self._client

    def close(self) -> None:
        with self._client_lock:
            client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    @staticmethod
    def _series_map(result: Any, requested: list[str]) -> dict[str, Any]:
        if isinstance(result, dict):
            return result
        return {requested[0]: result} if len(requested) == 1 else {}

    def _all_symbols(self) -> list[str]:
        try:
            return list(self._get_client().codes.all_a_shares())
        except Exception as exc:
            raise ProviderRequestError(f"eltdx A 股股票池获取失败: {exc}") from exc

    # ---- realtime ----
    def get_realtime(self) -> list[dict]:
        try:
            return self._realtime_for_native(self._all_symbols())
        except ProviderRequestError as exc:
            logger.warning("eltdx 实时行情失败: %s", exc)
            return []

    def get_realtime_symbols(self, symbols: list[str], *, asset_type: str = "stock") -> list[dict] | None:
        if asset_type not in _BAR_ASSET_TYPES or not symbols:
            return []
        try:
            return self._realtime_for_native([_native_symbol(s) for s in symbols])
        except ProviderRequestError as exc:
            logger.warning("eltdx 订阅行情失败: %s", exc)
            return None

    def get_realtime_indices(self, symbols: list[str]) -> list[dict] | None:
        """补拉产品固定指数快照；结构与 realtime 数据集一致。"""
        return self.get_realtime_symbols(symbols, asset_type="index")

    def _realtime_for_native(self, native: list[str]) -> list[dict]:
        out: list[dict] = []
        client = self._get_client()
        for offset in range(0, len(native), _QUOTE_BATCH):
            chunk = native[offset : offset + _QUOTE_BATCH]
            try:
                snapshots = client.quotes.get_snapshots(chunk) or []
            except Exception as exc:
                raise ProviderRequestError(f"快照批次失败: {exc}") from exc
            received_ms = int(time.time() * 1000)
            for snapshot in snapshots:
                record = _quote_record(snapshot, received_ms)
                if record is not None:
                    out.append(record)
        return out

    # ---- daily ----
    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",
        on_chunk_done: Callable[[int, int], None] | None = None,
    ) -> pl.DataFrame:
        parts = [part for part in self.iter_daily(
            symbols, start_time, end_time, asset_type, on_chunk_done,
        ) if not part.is_empty()]
        return pl.concat(parts, how="diagonal_relaxed") if parts else pl.DataFrame(schema=_DAILY_SCHEMA)

    def iter_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",
        on_chunk_done: Callable[[int, int], None] | None = None,
    ) -> Iterator[pl.DataFrame]:
        if not symbols or asset_type not in _BAR_ASSET_TYPES:
            if on_chunk_done:
                on_chunk_done(0, 0)
            return
        kind_arg = {"kind": "index"} if asset_type == "index" else {}
        start_d = _wall_clock(start_time).date() if start_time else None
        end_d = _wall_clock(end_time).date() if end_time else datetime.now(_BEIJING).date()
        span = (end_d - start_d).days if start_d else _MAX_DAILY_BARS * 7 // 5
        count = max(1, min(_MAX_DAILY_BARS, int(span * 5 / 7) + 32))
        completed = 0
        client = self._get_client()
        for offset in range(0, len(symbols), _BAR_BATCH):
            canonical = symbols[offset : offset + _BAR_BATCH]
            native = [_native_symbol(s) for s in canonical]
            bars_by_code: dict[str, list[Any]] = {code: [] for code in native}
            for start in range(0, count, _PAGE_SIZE):
                page_count = min(_PAGE_SIZE, count - start)
                try:
                    result = client.bars.get(
                        native, period="day", start=start, count=page_count,
                        adjust="none", batch_size=_BAR_BATCH, **kind_arg,
                    )
                except Exception as exc:
                    raise ProviderRequestError(f"eltdx 日K批次失败: {exc}") from exc
                page = self._series_map(result, native)
                returned = []
                for code in native:
                    values = list(getattr(page.get(code), "bars", ()) or ())
                    bars_by_code[code].extend(values)
                    returned.append(len(values))
                if returned and max(returned) < page_count:
                    break
            for symbol, code in zip(canonical, native, strict=True):
                rows = _daily_rows(symbol, bars_by_code[code], start_d, end_d)
                yield pl.DataFrame(rows, schema=_DAILY_SCHEMA)
                completed += 1
                if on_chunk_done:
                    on_chunk_done(completed, len(symbols))

    # ---- minute / full minute ----
    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",
        freq: str = "1m",
        on_chunk_done: Callable[[int, int], None] | None = None,
    ) -> pl.DataFrame:
        parts = list(self.iter_minute(
            symbols, start_time, end_time, asset_type, freq, on_chunk_done,
        ))
        parts = [part for part in parts if not part.is_empty()]
        return pl.concat(parts, how="diagonal_relaxed") if parts else pl.DataFrame(schema=_MINUTE_SCHEMA)

    def iter_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",
        freq: str = "1m",
        on_chunk_done: Callable[[int, int], None] | None = None,
    ) -> Iterator[pl.DataFrame]:
        if not symbols or asset_type not in _BAR_ASSET_TYPES or freq != "1m":
            if on_chunk_done:
                on_chunk_done(0, 0)
            return
        kind_arg = {"kind": "index"} if asset_type == "index" else {}
        end_dt = _wall_clock(end_time) if end_time else datetime.now(_BEIJING).replace(tzinfo=None)
        start_dt = _wall_clock(start_time) if start_time else end_dt - timedelta(days=30)
        estimate = int(max((end_dt.date() - start_dt.date()).days, 1) * 5 / 7 * 240) + 480
        max_bars = min(max(estimate, 240), _MAX_MINUTE_BARS)
        client = self._get_client()
        for index, symbol in enumerate(symbols):
            native = _native_symbol(symbol)
            rows_by_time: dict[datetime, dict] = {}
            for start in range(0, max_bars, _PAGE_SIZE):
                count = min(_PAGE_SIZE, max_bars - start)
                try:
                    series = client.bars.get(
                        native, period="1min", start=start, count=count,
                        adjust="none", bar_time="start", **kind_arg,
                    )
                except Exception as exc:
                    raise ProviderRequestError(f"eltdx 分钟K {symbol} 失败: {exc}") from exc
                bars = list(getattr(series, "bars", ()) or ())
                rows = _minute_rows(symbol, bars, start_dt, end_dt)
                rows_by_time.update({row["datetime"]: row for row in rows})
                oldest = min((_wall_clock(bar.time) for bar in bars if isinstance(getattr(bar, "time", None), datetime)), default=None)
                if len(bars) < count or (oldest is not None and oldest <= start_dt):
                    break
            ordered = [rows_by_time[key] for key in sorted(rows_by_time)]
            yield pl.DataFrame(ordered, schema=_MINUTE_SCHEMA)
            if on_chunk_done:
                on_chunk_done(index + 1, len(symbols))

    def _batch_latest(self, symbols: list[str], count: int) -> pl.DataFrame:
        now = datetime.now(_BEIJING).replace(tzinfo=None)
        out: list[pl.DataFrame] = []
        client = self._get_client()
        for offset in range(0, len(symbols), _BAR_BATCH):
            canonical = symbols[offset : offset + _BAR_BATCH]
            native = [_native_symbol(s) for s in canonical]
            try:
                result = client.bars.get(
                    native, period="1min", count=count, adjust="none",
                    batch_size=_BAR_BATCH, bar_time="start",
                )
            except Exception as exc:
                raise ProviderRequestError(f"eltdx 全量分钟批次失败: {exc}") from exc
            by_code = self._series_map(result, native)
            for symbol, code in zip(canonical, native, strict=True):
                series = by_code.get(code)
                rows = _minute_rows(symbol, list(getattr(series, "bars", ()) or ()), None, now)
                if rows:
                    out.append(pl.DataFrame(rows, schema=_MINUTE_SCHEMA))
        return pl.concat(out, how="diagonal_relaxed") if out else pl.DataFrame(schema=_MINUTE_SCHEMA)

    def get_intraday_batch(
        self, symbols: list[str], count: int = 300, asset_type: str = "stock",
    ) -> pl.DataFrame:
        if not symbols or asset_type != "stock":
            return pl.DataFrame(schema=_MINUTE_SCHEMA)
        now = datetime.now(_BEIJING).replace(tzinfo=None)
        today = datetime.combine(now.date(), dt_time.min)
        frame = self._batch_latest(symbols, max(240, min(int(count), 480)) + 240)
        return frame.filter(pl.col("datetime") >= today) if not frame.is_empty() else frame

    def get_intraday_latest(self, symbols: list[str] | None = None, count: int = 3) -> pl.DataFrame:
        targets = list(symbols or [])
        if not targets:
            targets = [_canonical_symbol(code) for code in self._all_symbols()]
        return self._batch_latest(targets, max(1, min(int(count), 30)))

    # ---- depth ----
    def get_depth_batch(self, symbols: list[str]) -> dict[str, dict]:
        if not symbols:
            return {}
        out: dict[str, dict] = {}
        client = self._get_client()
        for offset in range(0, len(symbols), _QUOTE_BATCH):
            canonical = symbols[offset : offset + _QUOTE_BATCH]
            native = [_native_symbol(s) for s in canonical]
            try:
                page = client.quotes.get_depth(native)
            except Exception as exc:
                raise ProviderRequestError(f"eltdx 五档盘口失败: {exc}") from exc
            stamp = int(time.time() * 1000)
            for record in list(getattr(page, "records", ()) or ()):
                symbol = _canonical_symbol(getattr(record, "code", ""), getattr(record, "exchange", ""))
                bids = list(getattr(record, "buy_levels", ()) or ())
                asks = list(getattr(record, "sell_levels", ()) or ())
                if not bids or not asks:
                    continue
                out[symbol] = {
                    "bid_prices": [float(level.price) for level in bids],
                    "bid_volumes": [int(level.volume) for level in bids],
                    "ask_prices": [float(level.price) for level in asks],
                    "ask_volumes": [int(level.volume) for level in asks],
                    "timestamp": stamp,
                }
        return out

    # ---- settings-page smoke pulls ----
    def test_dataset(self, dataset: str, symbols: list[str] | None = None) -> dict:
        sample = list(symbols or [])[:3] or ["000001.SZ"]
        try:
            if dataset == "realtime":
                rows: Any = self.get_realtime_symbols(sample) or []
                count = len(rows)
                preview = rows[:5]
            elif dataset == "depth5":
                rows = self.get_depth_batch(sample)
                count = len(rows)
                preview = [{"symbol": key, **value} for key, value in list(rows.items())[:2]]
            elif dataset == "daily":
                frame = self.get_daily(sample, datetime.now() - timedelta(days=30), datetime.now())
                count, preview = frame.height, frame.head(5).to_dicts()
            elif dataset in {"minute", "full_minute"}:
                frame = self._batch_latest(sample, 5)
                count, preview = frame.height, frame.head(5).to_dicts()
            else:
                return {"provider": self.name, "dataset": dataset, "rows": 0, "error": "未声明该能力"}
            for row in preview:
                for key, value in list(row.items()):
                    if isinstance(value, (date, datetime)):
                        row[key] = value.isoformat()
            return {"provider": self.name, "dataset": dataset, "rows": count, "preview": preview}
        except Exception as exc:  # noqa: BLE001
            return {"provider": self.name, "dataset": dataset, "rows": 0, "error": str(exc)}
