"""stock-panel 原生因子每日重算管道。

输入只来自 ``data_dir`` 下的本地 OHLCV、维表、主线/市场历史及已注册增强
插件。输出沿用扩展时序表存储，以保持筛选、策略、回测和模拟盘的消费契约。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

from app.price_limits import polars_limit_price, polars_price_limit_pct
from app.services.ext_data import apply_config_mapping, write_ext_parquet

from .providers import load_provider_frame
from .registry import (
    STOCK_FACTOR_IDS,
    STRATEGY_CONTEXT_IDS,
    register_native_tables,
)


@dataclass(frozen=True)
class NativeFactorResult:
    dates: tuple[str, ...]
    factor_rows: int
    context_rows: int
    registered_factors: int = len(STOCK_FACTOR_IDS)
    strategy_context_factors: int = len(STRATEGY_CONTEXT_IDS)


def _clip(value: float | None, default: float | None = None) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return default
    return max(0.0, min(100.0, float(value)))


def _activity_score(v: float | None) -> float | None:
    if v is None:
        return None
    if v <= 0:
        return 0.0
    if v < 0.6:
        return max(20.0, 20.0 + v / 0.6 * 20.0)
    if v < 1:
        return 40.0 + (v - 0.6) / 0.4 * 30.0
    if v < 2.2:
        return 70.0 + (v - 1) / 1.2 * 30.0
    if v < 3:
        return 100.0 - (v - 2.2) / 0.8 * 25.0
    if v < 5:
        return 75.0 - (v - 3) / 2 * 45.0
    return 20.0


def _amount_score(v: float | None) -> float | None:
    if v is None:
        return None
    if v <= 0:
        return 0.0
    if v < 0.4:
        return v / 0.4 * 15.0
    if v < 0.8:
        return 15.0 + (v - 0.4) / 0.4 * 60.0
    if v < 1.15:
        return 75.0 + (v - 0.8) / 0.35 * 25.0
    if v <= 1.5:
        return 100.0 - (v - 1.15) / 0.35 * 15.0
    if v <= 2.2:
        return 85.0 - (v - 1.5) / 0.7 * 40.0
    if v <= 3:
        return 45.0 - (v - 2.2) / 0.8 * 30.0
    return max(0.0, 15.0 - (v - 3) * 5.0)


def _new_high_score(v: float | None) -> float | None:
    if v is None:
        return None
    if v <= 0:
        return 0.0
    if v < 0.85:
        return v / 0.85 * 20.0
    if v < 0.95:
        return 20.0 + (v - 0.85) / 0.10 * 50.0
    if v < 1.02:
        return 70.0 + (v - 0.95) / 0.07 * 30.0
    if v <= 1.10:
        return 100.0 - (v - 1.02) / 0.08 * 20.0
    if v <= 1.20:
        return 80.0 - (v - 1.10) / 0.10 * 25.0
    return max(20.0, 55.0 - (v - 1.20) * 100.0)


def _board_score(v: int | float | None) -> float:
    return {0: 50.0, 1: 70.0, 2: 90.0, 3: 85.0, 4: 70.0, 5: 55.0}.get(int(v or 0), 35.0)


def _float_mv_score(value_yuan: float | None) -> float | None:
    if value_yuan is None or value_yuan <= 0:
        return None
    yi = value_yuan / 1e8
    if yi < 5:
        return 45.0
    if yi < 20:
        return 60.0 + (yi - 5) / 15 * 30.0
    if yi <= 80:
        return 90.0
    if yi <= 200:
        return 90.0 - (yi - 80) / 120 * 35.0
    if yi <= 500:
        return 55.0 - (yi - 200) / 300 * 25.0
    return 30.0


def _turnover_health(turnover: float | None, amount: float | None) -> float:
    value = float(turnover or 0.0)
    if value <= 0 and (amount or 0) > 0:
        value = float(amount) / 1e8
    if 3 <= value <= 15:
        return 80.0
    if 1 <= value < 3:
        return 60.0
    if 15 < value <= 25:
        return 50.0
    if value > 25:
        return 30.0
    return 40.0


def _vol_price(pct_points: float | None, ratio: float | None) -> float | None:
    if pct_points is None or ratio is None:
        return None
    if pct_points > 0 and ratio > 1:
        return min(100.0, ratio * 50 + 30)
    if pct_points > 0:
        return max(0.0, ratio * 40)
    if pct_points < 0 and ratio < 1:
        return 50.0
    return max(0.0, 50.0 - ratio * 20)


def _ma_align(row: dict) -> float | None:
    vals = [row.get(k) for k in ("ma5", "ma10", "ma20", "ma60", "close")]
    if any(v is None for v in vals):
        return None
    ma5, ma10, ma20, ma60, close = map(float, vals)
    return float(25 * sum((ma5 > ma10, ma10 > ma20, ma20 > ma60, close > ma5)))


def _native_base(history: pl.DataFrame) -> pl.DataFrame:
    history = history.sort(["symbol", "date"])

    def grouped(expr: pl.Expr) -> pl.Expr:
        return expr.over("symbol")

    history = history.with_columns(
        grouped(pl.col("close").shift(1)).alias("pre_close"),
        grouped(pl.col("volume").shift(1).rolling_mean(5)).alias("vol_avg5"),
        grouped(pl.col("amount").shift(1).rolling_mean(5)).alias("amount_avg5"),
        grouped(pl.col("high").rolling_max(20)).alias("high20"),
        grouped(pl.col("high").rolling_max(20)).alias("n_high"),
        grouped(pl.col("low").rolling_min(20)).alias("n_low"),
        grouped(pl.col("close").rolling_mean(5)).alias("ma5"),
        grouped(pl.col("close").rolling_mean(10)).alias("ma10"),
        grouped(pl.col("close").rolling_mean(20)).alias("ma20"),
        grouped(pl.col("close").rolling_mean(60)).alias("ma60"),
        grouped(pl.col("close").shift(20)).alias("close20"),
        grouped((pl.col("consecutive_limit_ups") > 0).cast(pl.Int8).rolling_sum(5)).alias(
            "limit_count5"
        ),
    ).with_columns(
        (pl.col("volume") / pl.col("vol_avg5")).alias("vol_ratio"),
        (pl.col("amount") / pl.col("amount_avg5")).alias("amount_ratio"),
        (pl.col("close") / pl.col("high20")).alias("new_high_ratio"),
        ((pl.col("close") / pl.col("pre_close") - 1.0) * 100.0).alias("pct_points"),
        ((pl.col("close") - pl.col("n_low")) / (pl.col("n_high") - pl.col("n_low")) * 100.0).alias(
            "d1"
        ),
    )
    history = (
        history.with_columns(
            polars_price_limit_pct(
                pl.col("symbol"),
                pl.col("date"),
                pl.col("name").fill_null("").str.to_uppercase().str.contains("ST"),
            ).alias("limit_pct"),
        )
        .with_columns(
            polars_limit_price(pl.col("pre_close"), pl.col("limit_pct"), up=True).alias(
                "limit_up_price"
            ),
            polars_limit_price(pl.col("pre_close"), pl.col("limit_pct"), up=False).alias(
                "limit_down_price"
            ),
        )
        .with_columns(
            ((pl.col("close") / pl.col("pre_close") - 1.0) / pl.col("limit_pct")).alias(
                "limit_progress"
            ),
            (pl.col("close") >= pl.col("limit_up_price") - 0.0051)
            .fill_null(False)
            .alias("is_limit_up"),
            (pl.col("low") <= pl.col("limit_down_price") + 0.0051)
            .fill_null(False)
            .alias("touched_limit_down"),
        )
    )
    return history


def _load_history(data_dir: Path, end: date) -> pl.DataFrame:
    files = sorted((data_dir / "kline_daily_enriched").glob("date=*/*.parquet"))
    files = [path for path in files if date.fromisoformat(path.parent.name[5:]) <= end]
    if not files:
        raise FileNotFoundError("本地 kline_daily_enriched 没有可计算数据")
    frame = pl.read_parquet(files)
    required = {
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "consecutive_limit_ups",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"enriched 缺少原生因子依赖: {sorted(missing)}")
    inst_path = data_dir / "instruments" / "instruments.parquet"
    instruments = (
        pl.read_parquet(inst_path)
        if inst_path.exists()
        else pl.DataFrame(schema={"symbol": pl.Utf8})
    )
    cols = [c for c in ("symbol", "name", "float_shares") if c in instruments.columns]
    frame = frame.join(
        instruments.select(cols).unique("symbol") if cols else instruments, on="symbol", how="left"
    )
    if "name" not in frame.columns:
        frame = frame.with_columns(pl.lit("").alias("name"))
    if "float_shares" not in frame.columns:
        frame = frame.with_columns(pl.lit(None).cast(pl.Float64).alias("float_shares"))
    if "turnover_rate" not in frame.columns:
        frame = frame.with_columns(pl.lit(None).cast(pl.Float64).alias("turnover_rate"))
    return _native_base(frame)


def _market_context(current: pl.DataFrame, data_dir: Path, trade_date: date) -> dict[str, float]:
    limit_up = int(current["is_limit_up"].sum())
    limit_down = int(
        (current["close"] <= current["limit_down_price"] + 0.0051).fill_null(False).sum()
    )
    broken = (
        int((current["high"] >= current["limit_up_price"] - 0.0051).fill_null(False).sum())
        - limit_up
    )
    denom = limit_up + max(broken, 0)
    score = None
    regime = data_dir / "regime_history" / "part.parquet"
    if regime.exists():
        row = pl.read_parquet(regime).filter(pl.col("date") == trade_date)
        if not row.is_empty() and "score" in row.columns:
            score = float(row["score"][0])
    if score is None:
        up_ratio = float((current["pct_points"] > 0).mean() or 0.0)
        score = _clip(
            up_ratio * 60
            + min(limit_up / 100, 1) * 25
            + (1 - limit_down / max(current.height, 1)) * 15,
            50.0,
        )
    return {
        "mkt_limit_up_count": float(limit_up),
        "mkt_limit_down_count": float(limit_down),
        "mkt_broken_rate": float(max(broken, 0) / denom * 100 if denom else 0),
        "mkt_market_score": float(score),
    }


def _attach_sector_scores(
    current: pl.DataFrame, data_dir: Path, trade_date: date, repo=None
) -> pl.DataFrame:
    defaults = [
        pl.lit(None).cast(pl.Float64).alias("sector_mainline"),
        pl.lit(None).cast(pl.Float64).alias("sector_persistence"),
        pl.lit(None).cast(pl.Float64).alias("sector_resonance"),
        pl.lit(None).cast(pl.Utf8).alias("primary_sector"),
    ]
    from app.services.rps_rotation import _load_concept_map_df

    path = data_dir / "mainline_history" / "part.parquet"
    if not path.exists():
        return current.with_columns(defaults)
    mainline = pl.read_parquet(path).filter(pl.col("date") == trade_date)
    joined_parts = []
    for kind in ("concept", "industry"):
        if repo is not None:
            mapping, _ = _load_concept_map_df(repo, kind)
        else:
            from app.services.ext_data import ExtConfigStore
            from app.services.market_overview_builder import (
                _dimension_field,
                _dimension_values,
                _read_ext_rows,
                _symbol_keys,
            )

            pairs = []
            for config in ExtConfigStore(data_dir).load_all():
                field = _dimension_field(config, kind)
                if not field:
                    continue
                for ext_row in _read_ext_rows(data_dir, config, field):
                    for key in _symbol_keys(ext_row, config):
                        pairs.extend(
                            (key, member) for member in _dimension_values(ext_row.get(field))
                        )
            mapping = (
                pl.DataFrame(
                    {"_sym_up": [x[0] for x in pairs], kind: [x[1] for x in pairs]}
                ).unique()
                if pairs
                else pl.DataFrame(schema={"_sym_up": pl.Utf8, kind: pl.Utf8})
            )
        scores = mainline.filter(pl.col("kind") == kind).select(
            pl.col("member").alias(kind), "score"
        )
        if mapping.is_empty() or scores.is_empty():
            continue
        joined_parts.append(
            mapping.join(scores, on=kind, how="inner").select(
                "_sym_up", pl.col(kind).alias("member"), "score"
            )
        )
    if not joined_parts:
        return current.with_columns(defaults)
    matches = pl.concat(joined_parts).sort(["_sym_up", "score"], descending=[False, True])
    agg = matches.group_by("_sym_up").agg(
        pl.col("score").head(3).mean().alias("sector_mainline"),
        pl.col("score").max().alias("sector_persistence"),
        pl.col("score").head(2).mean().alias("sector_resonance"),
        pl.col("member").first().alias("primary_sector"),
    )
    return (
        current.with_columns(pl.col("symbol").str.to_uppercase().alias("_sym_up"))
        .join(agg, on="_sym_up", how="left")
        .drop("_sym_up")
        .with_columns(
            pl.col("sector_mainline").fill_null(0.0),
            pl.col("sector_persistence").fill_null(0.0),
            pl.col("sector_resonance").fill_null(0.0),
        )
    )


def _lhb_frame(data_dir: Path, trade_date: date) -> pl.DataFrame:
    path = data_dir / "dragon_tiger" / f"date={trade_date.isoformat()}.json"
    if not path.exists():
        return pl.DataFrame(schema={"symbol": pl.Utf8})
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return pl.DataFrame(schema={"symbol": pl.Utf8})
    all_rows = (payload.get("all") or {}).get("stock_items") or []
    org_rows = (payload.get("org") or {}).get("stock_items") or []
    by_symbol: dict[str, dict] = {}
    for item in all_rows:
        symbol = str(item.get("thscode") or "").upper()
        if not symbol:
            continue
        row = by_symbol.setdefault(symbol, {"symbol": symbol, "net": 0.0, "org": 0.0, "appear": 0})
        row["net"] += float(item.get("net_value") or 0.0)
        row["appear"] += 1
    for item in org_rows:
        symbol = str(item.get("thscode") or "").upper()
        if not symbol:
            continue
        row = by_symbol.setdefault(symbol, {"symbol": symbol, "net": 0.0, "org": 0.0, "appear": 0})
        row["org"] += float(item.get("org_net_value") or 0.0)
        row["appear"] += 1
    if not by_symbol:
        return pl.DataFrame(schema={"symbol": pl.Utf8})
    frame = pl.DataFrame(list(by_symbol.values()))
    return frame.with_columns(
        pl.col("net")
        .rank(method="average", descending=False)
        .truediv(pl.len())
        .mul(100)
        .alias("stk_lhb_net_buy_score"),
        pl.col("org")
        .rank(method="average", descending=False)
        .truediv(pl.len())
        .mul(100)
        .alias("stk_lhb_institution_score"),
        pl.when(pl.col("org") > 0)
        .then(80.0)
        .when(pl.col("org") < 0)
        .then(20.0)
        .otherwise(50.0)
        .alias("stk_lhb_institution_consensus"),
        pl.col("appear").cast(pl.Float64).mul(25).clip(0, 100).alias("stk_lhb_repeat_persistence"),
        pl.lit(None).cast(pl.Float64).alias("stk_lhb_sector_resonance"),
        (100.0 - pl.col("appear").cast(pl.Float64).mul(15))
        .clip(0, 100)
        .alias("stk_lhb_crowding_risk"),
    ).select("symbol", *[c for c in STOCK_FACTOR_IDS if c.startswith("stk_lhb_")])


def _reversal_metrics(history: pl.DataFrame, trade_date: date) -> pl.DataFrame:
    rows = []
    for symbol, group in history.filter(pl.col("date") <= trade_date).group_by(
        "symbol", maintain_order=True
    ):
        h = group.sort("date").tail(80)
        if h.height < 21 or h["date"][-1] != trade_date:
            continue
        today = h.row(-1, named=True)
        contraction = recovery = 0.0
        pullback = reversal = 0.0
        tr = pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - pl.col("pre_close")).abs(),
            (pl.col("low") - pl.col("pre_close")).abs(),
        )
        h = h.with_columns(tr.alias("tr"))
        start = max(20, h.height - 16)
        for idx in range(h.height - 2, start - 1, -1):
            event = h.row(idx, named=True)
            if not event["is_limit_up"]:
                continue
            atr = float(h["tr"][max(0, idx - 13) : idx + 1].mean() or 0)
            before = h.slice(idx - 20, 20)
            platform = float(before["high"].max())
            support = (
                platform
                if event["close"] > platform and event["open"] <= platform
                else (event["open"] + event["close"]) / 2
            )
            after = h.slice(idx + 1)
            contraction = float((after["volume"].mean() or 0) / max(event["volume"], 1))
            peak = float(h["high"][idx:].max())
            if (
                after.height
                and float(after["close"].min()) >= support - 0.5 * atr
                and today["close"] < peak - 0.3 * atr
                and abs(today["close"] - support) <= 1.5 * atr
            ):
                pullback = 100.0
            break
        for idx in range(h.height - 1, max(19, h.height - 4), -1):
            event = h.row(idx, named=True)
            if not event["touched_limit_down"]:
                continue
            atr = float(h["tr"][max(0, idx - 13) : idx + 1].mean() or 0)
            floor = event["low"]
            target = (
                event["open"] if event["open"] - event["close"] > atr * 0.1 else event["pre_close"]
            )
            recovery = (today["close"] - event["close"]) / max(
                event["pre_close"] - event["close"], 0.01
            )
            consecutive = idx > 0 and bool(h["touched_limit_down"][idx - 1])
            if (
                not consecutive
                and float(h["close"][idx:].min()) >= floor
                and today["close"] <= target + atr
            ):
                reversal = 100.0
            break
        rows.append(
            {
                "symbol": symbol[0] if isinstance(symbol, tuple) else symbol,
                "stk_limit_pullback": pullback,
                "stk_limit_reversal": reversal,
                "stk_pullback_contraction": _clip((1.5 - contraction) * 100, 0.0),
                "stk_reversal_recovery": _clip(recovery * 100, 0.0),
            }
        )
    return pl.DataFrame(rows) if rows else pl.DataFrame(schema={"symbol": pl.Utf8})


def _intraday_limit_metrics(
    data_dir: Path, trade_date: date, current: pl.DataFrame
) -> dict[str, dict[str, float]]:
    """从本地分钟 K 计算首封、炸板和封板质量；ELTDX/axdata 只需先落标准分钟表。"""
    path = data_dir / "kline_minute" / f"date={trade_date.isoformat()}" / "part.parquet"
    if not path.exists():
        return {}
    minute = pl.read_parquet(path)
    if minute.is_empty() or not {"symbol", "datetime", "high", "close"} <= set(minute.columns):
        return {}
    limits = current.select("symbol", "limit_up_price", "primary_sector", "consecutive_limit_ups")
    minute = (
        minute.join(limits, on="symbol", how="inner")
        .filter(pl.col("limit_up_price").is_not_null())
        .sort(["symbol", "datetime"])
    )
    if minute.is_empty():
        return {}
    minute = minute.with_columns(
        (
            (pl.col("high") >= pl.col("limit_up_price") - 0.0051)
            | (pl.col("close") >= pl.col("limit_up_price") - 0.0051)
        ).alias("sealed")
    )
    output: dict[str, dict[str, float]] = {}
    sector_times: dict[str, list[tuple[str, int]]] = {}
    for symbol, group in minute.group_by("symbol", maintain_order=True):
        sym = symbol[0] if isinstance(symbol, tuple) else symbol
        hits = group.filter(pl.col("sealed"))
        if hits.is_empty():
            continue
        first = hits["datetime"][0]
        last = hits["datetime"][-1]
        seconds = first.hour * 3600 + first.minute * 60 + first.second
        opens = int(
            group.with_columns(pl.col("sealed").shift(1).fill_null(False).alias("prev"))
            .filter(pl.col("prev") & ~pl.col("sealed"))
            .height
        )
        text = first.strftime("%H:%M:%S")
        d3 = (
            90.0
            if text <= "09:35:00"
            else 75.0
            if text <= "10:00:00"
            else 60.0
            if text <= "10:30:00"
            else 45.0
            if text <= "11:30:00"
            else 30.0
            if text <= "14:00:00"
            else 15.0
        )
        seal_time = (
            95.0
            if text <= "09:35:00"
            else 82.0
            if text <= "10:00:00"
            else 68.0
            if text <= "10:30:00"
            else 52.0
            if text <= "11:30:00"
            else 38.0
            if text <= "14:00:00"
            else 22.0
        ) - min(opens, 4) * 6
        timing = (
            95.0
            if text <= "09:35:00"
            else 82.0
            if text <= "10:00:00"
            else 65.0
            if text <= "11:30:00"
            else 35.0
        )
        stability = max(0.0, 100.0 - opens * 14.0 - (min(opens, 4) * 4.0 if last > first else 0.0))
        output[sym] = {
            "D3_seal_strength": d3,
            "stk_seal_time_quality": max(0.0, seal_time),
            "stk_intraday_seal_quality": timing * 0.4 + stability * 0.35,
            "stk_first_board_leadership_score": 75.0,
        }
        sector = str(group["primary_sector"][0] or "")
        if sector and int(group["consecutive_limit_ups"][0] or 0) == 1:
            sector_times.setdefault(sector, []).append((sym, seconds))
    for peers in sector_times.values():
        if len(peers) <= 1:
            continue
        for sym, seconds in peers:
            output[sym]["stk_first_board_leadership_score"] = (
                sum(peer_seconds > seconds for _, peer_seconds in peers) / (len(peers) - 1) * 100.0
            )
    return output


def _calculate_date(
    history: pl.DataFrame, data_dir: Path, trade_date: date, repo=None
) -> tuple[pl.DataFrame, pl.DataFrame]:
    current = history.filter(pl.col("date") == trade_date)
    if current.is_empty():
        return pl.DataFrame(), pl.DataFrame()
    current = _attach_sector_scores(current, data_dir, trade_date, repo)
    market = _market_context(current, data_dir, trade_date)
    current = current.with_columns(
        pl.col("amount").rank(method="average").truediv(pl.len()).mul(100).alias("liquidity"),
        pl.col("pct_points")
        .rank(method="average")
        .over("primary_sector")
        .truediv(pl.len().over("primary_sector"))
        .mul(100)
        .fill_null(50)
        .alias("relative_sector"),
    )
    current = current.with_columns(
        pl.col("vol_ratio")
        .map_elements(_activity_score, return_dtype=pl.Float64)
        .alias("vol_score"),
        pl.col("amount_ratio")
        .map_elements(_amount_score, return_dtype=pl.Float64)
        .alias("amount_score"),
        pl.col("new_high_ratio")
        .map_elements(_new_high_score, return_dtype=pl.Float64)
        .alias("new_high_score"),
    )
    # 首板真实截面：同一主板块的首板密度、涨幅宽度和量价共振。
    sector_stats = current.group_by("primary_sector").agg(
        pl.len().alias("sector_size"),
        pl.col("is_limit_up").sum().alias("sector_limits"),
        (pl.col("pct_points") > 5).sum().alias("sector_strong"),
        pl.col("amount_score").mean().alias("sector_amount"),
    )
    current = current.join(sector_stats, on="primary_sector", how="left")
    is_first = pl.col("consecutive_limit_ups") == 1
    current = (
        current.with_columns(
            pl.when(is_first)
            .then((pl.col("sector_limits") / pl.col("sector_size") * 1250).clip(0, 100))
            .otherwise(0.0)
            .alias("fb_pioneer"),
            pl.when(is_first)
            .then((pl.col("sector_strong") / pl.col("sector_size") * 400).clip(0, 100))
            .otherwise(0.0)
            .alias("fb_breadth"),
            pl.when(is_first)
            .then(
                pl.col("sector_mainline").fill_null(50) * 0.35
                + pl.col("sector_limits").clip(0, 6) / 6 * 100 * 0.25
                + pl.col("sector_amount").fill_null(50) * 0.20
                + pl.col("amount_score").fill_null(50) * 0.20
            )
            .otherwise(0.0)
            .alias("fb_sync"),
        )
        .with_columns(
            pl.when(is_first)
            .then(
                pl.col("sector_amount").fill_null(50) * 0.55
                + pl.col("amount_score").fill_null(50) * 0.45
            )
            .otherwise(0.0)
            .alias("fb_amount"),
            pl.when(is_first).then(50.0).otherwise(0.0).alias("fb_new_theme"),
        )
        .with_columns(
            pl.when(is_first)
            .then(
                pl.col("fb_sync") * 0.3125
                + pl.col("fb_pioneer") * 0.1875
                + pl.col("fb_breadth") * 0.1875
                + pl.col("fb_amount") * 0.1875
                + pl.col("fb_new_theme") * 0.125
            )
            .otherwise(0.0)
            .alias("fb_resonance"),
        )
    )
    intraday = _intraday_limit_metrics(data_dir, trade_date, current)
    rows = []
    for row in current.iter_rows(named=True):
        minute_values = intraday.get(row["symbol"], {})
        board = _board_score(row.get("consecutive_limit_ups"))
        amount_score = row.get("amount_score")
        relative = float(row.get("relative_sector") or 50)
        sector = float(row.get("sector_mainline") or 50)
        crowd = {0: 50, 1: 90, 2: 78, 3: 58, 4: 35, 5: 18}.get(
            int(row.get("limit_count5") or 0), 18
        )
        repair_quality = (
            95.0
            if (row.get("open", 0) / max(row.get("pre_close") or 1, 1e-9) - 1)
            < 0
            < (row.get("pct_points") or 0)
            else min(45.0, 25 + max((row.get("pct_points") or 0), 0) * 2)
        )
        behavior_attention = _clip(
            sector * 0.4
            + relative * 0.2
            + (amount_score or 50) * 0.15
            + board * 0.15
            + crowd * 0.1,
            50,
        )
        behavior_acceleration = _clip(
            sector * 0.25
            + relative * 0.2
            + (amount_score or 50) * 0.1
            + board * 0.1
            + crowd * 0.1
            + 50 * 0.25,
            50,
        )
        behavior_divergence = _clip(
            (100 - crowd) * 0.35
            + max(0, (row.get("amount_ratio") or 1) - 1.5) / 1.5 * 20
            + (100 - relative) * 0.2
            + 30,
            50,
        )
        behavior_repair = _clip(
            repair_quality * 0.35 + relative * 0.25 + sector * 0.25 + (amount_score or 50) * 0.15,
            50,
        )
        behavior_decay = _clip(
            (100 - crowd) * 0.35 + (100 - relative) * 0.3 + (100 - sector) * 0.25 + 5, 50
        )
        trend = 0.0
        if row.get("ma20") is not None:
            trend += 12 if (row.get("ma5") or 0) > (row.get("ma10") or 0) > 0 else 0
            trend += 14 if (row.get("ma10") or 0) > (row.get("ma20") or 0) > 0 else 0
            trend += 14 if row["close"] > row["ma20"] > 0 else 0
            if row.get("ma60") is not None:
                trend += 18 if row["ma20"] > row["ma60"] > 0 else 0
                trend += 12 if row["close"] > row["ma60"] > 0 else 0
            trend += max(
                0, min(20, (row["close"] / (row.get("close20") or row["close"]) - 1) * 100)
            )
            trend += 10 if (row.get("new_high_score") or 0) >= 70 else 0
            trend += 10 if (row.get("limit_count5") or 0) >= 2 else 0
        rows.append(
            {
                "code": row["symbol"].split(".")[0],
                "symbol": row["symbol"],
                "D1_n_day_high_low": row.get("d1"),
                "D2_vol_price_coord": _vol_price(row.get("pct_points"), row.get("vol_ratio")),
                # 源公式在没有首封分钟证据时返回中性 50；分钟插件接入后覆盖该值。
                "D3_seal_strength": minute_values.get("D3_seal_strength", 50.0),
                "D4_turnover_health": _turnover_health(row.get("turnover_rate"), row.get("amount")),
                "D5_ma_bull_align": _ma_align(row),
                "stk_board_height": board,
                "stk_seal_time_quality": minute_values.get("stk_seal_time_quality", 50.0),
                "stk_float_mv_fit": _float_mv_score((row.get("float_shares") or 0) * row["close"]),
                "E1_main_net_ratio": None,
                "E2_retail_net_ratio": None,
                "E3_large_buy_ratio": None,
                "E4_moneyflow_trend": None,
                "stk_capital_flow_consensus": None,
                "stk_intraday_seal_quality": minute_values.get("stk_intraday_seal_quality", 50.0),
                "stk_first_board_sector_sync_score": row.get("fb_sync") or 0.0,
                "stk_first_board_leadership_score": minute_values.get(
                    "stk_first_board_leadership_score", 0.0
                ),
                "stk_first_board_sector_pioneer_score": row.get("fb_pioneer"),
                "stk_first_board_breadth_score": row.get("fb_breadth"),
                "stk_first_board_amount_surge_score": row.get("fb_amount"),
                "stk_first_board_new_theme_score": row.get("fb_new_theme"),
                "stk_first_board_resonance_score": row.get("fb_resonance"),
                "stk_sector_rotation_momentum": _clip(
                    sector * 0.7 + (row.get("pct_points") or 0) * 3, 50
                ),
                "stk_crowding_decay_5d": float(crowd),
                "stk_relative_strength_sector": relative,
                "stk_behavior_attention": behavior_attention,
                "stk_behavior_acceleration": behavior_acceleration,
                "stk_behavior_divergence": behavior_divergence,
                "stk_behavior_repair": behavior_repair,
                "stk_behavior_decay": behavior_decay,
                "stk_capital_flow_persistence": None,
                "stk_attention_consensus": None,
                "stk_attention_crowding_risk": None,
                "stk_kpl_leader_quality": None,
                "stk_mainline_leader_identity": _clip(trend, 0),
                "stk_margin_acceleration": None,
                "stk_block_trade_risk": None,
            }
        )
    # 全市场行数远超 Polars 默认的前 100 行推断窗口。部分可选依赖（如流通
    # 股本、分钟封板证据）可能恰好前 100 行全为空、后续才出现小数；依赖推断
    # 会把该列定成 Null/I64 并在追加首个 Float64 时中止整条盘后流水线。
    factors = pl.DataFrame(
        rows,
        schema_overrides={
            "code": pl.Utf8,
            "symbol": pl.Utf8,
            **dict.fromkeys(STOCK_FACTOR_IDS, pl.Float64),
        },
    )
    # 本地缓存龙虎榜是真实插件数据；其余增强源可通过 providers.register_provider 接入。
    for plugin in (
        _lhb_frame(data_dir, trade_date),
        *[
            load_provider_frame(x, trade_date)
            for x in (
                "moneyflow",
                "attention",
                "margin",
                "block_trade",
                "leader_identity",
                "intraday_limit",
            )
        ],
    ):
        if plugin.is_empty():
            continue
        staged = factors.join(plugin, on="symbol", how="left", suffix="_plugin")
        replacement = [
            pl.coalesce(pl.col(f"{c}_plugin"), pl.col(c)).alias(c)
            for c in STOCK_FACTOR_IDS
            if f"{c}_plugin" in staged.columns
        ]
        if replacement:
            staged = staged.with_columns(replacement)
        factors = staged.drop([c for c in staged.columns if c.endswith("_plugin")])
    for factor in STOCK_FACTOR_IDS:
        if factor not in factors.columns:
            factors = factors.with_columns(pl.lit(None).cast(pl.Float64).alias(factor))
    context = current.select(
        pl.col("symbol").str.split(".").list.first().alias("code"),
        "symbol",
        pl.col("consecutive_limit_ups").cast(pl.Float64).alias("board_height"),
        pl.col("limit_progress"),
        pl.col("amount_ratio").alias("stk_amount_ratio_5d"),
        pl.col("consecutive_limit_ups")
        .map_elements(_board_score, return_dtype=pl.Float64)
        .alias("stk_board_position"),
        pl.col("liquidity").alias("stk_liquidity_percentile"),
        pl.col("new_high_score").alias("stk_new_high_20d"),
        ((pl.col("pct_points") + 10) * 5).clip(0, 100).alias("stk_pct_chg_1d"),
        pl.col("sector_mainline").alias("stk_sector_mainline_score"),
        pl.col("sector_persistence").alias("stk_sector_persistence_score"),
        pl.col("sector_resonance").alias("stk_sector_resonance_score"),
        pl.col("vol_ratio").alias("stk_vol_ratio_5d"),
        (
            pl.col("pct_points").add(10).mul(5).clip(0, 100) * 0.55
            + pl.col("new_high_score").fill_null(50) * 0.45
        ).alias("tech_score"),
    )
    reversal = _reversal_metrics(history, trade_date)
    if not reversal.is_empty():
        context = context.join(reversal, on="symbol", how="left")
    for key in (
        "stk_limit_pullback",
        "stk_limit_reversal",
        "stk_pullback_contraction",
        "stk_reversal_recovery",
    ):
        if key not in context.columns:
            context = context.with_columns(pl.lit(None).cast(pl.Float64).alias(key))
    context = context.with_columns(*[pl.lit(value).alias(key) for key, value in market.items()])
    return factors.select("code", *STOCK_FACTOR_IDS, "symbol"), context.select(
        "code", *STRATEGY_CONTEXT_IDS, "symbol"
    )


def compute_native_factor_partitions(
    data_dir: Path, *, start: date | None = None, end: date | None = None, repo=None
) -> NativeFactorResult:
    data_dir = Path(data_dir)
    factor_cfg, context_cfg = register_native_tables(data_dir)
    available = sorted(
        date.fromisoformat(p.name[5:])
        for p in (data_dir / "kline_daily_enriched").glob("date=*")
        if p.is_dir()
    )
    if not available:
        raise FileNotFoundError("本地 enriched 数据为空")
    end = end or available[-1]
    start = start or end
    targets = [d for d in available if start <= d <= end]
    history = _load_history(data_dir, end)
    factor_rows = context_rows = 0
    for index, trade_date in enumerate(targets):
        factors, context = _calculate_date(history, data_dir, trade_date, repo)
        if factors.is_empty():
            continue
        factor_rows += write_ext_parquet(
            apply_config_mapping(factors, factor_cfg, data_dir),
            factor_cfg,
            data_dir,
            snapshot_date=trade_date,
            keep_strategy_cache=True,
            replace_existing=True,
        )
        context_rows += write_ext_parquet(
            apply_config_mapping(context, context_cfg, data_dir),
            context_cfg,
            data_dir,
            snapshot_date=trade_date,
            keep_strategy_cache=index < len(targets) - 1,
            replace_existing=True,
        )
    return NativeFactorResult(tuple(d.isoformat() for d in targets), factor_rows, context_rows)
