"""盘前竞价榜单飞书推送。"""

from __future__ import annotations

import logging
import math
from datetime import time
from pathlib import Path

from app.market_time import cn_now
from app.services import auction_benchmark, preferences, trading_day, webhook_adapter
from app.services.fs_utils import atomic_write_text

logger = logging.getLogger(__name__)


def push_auction_benchmark(data_dir: Path) -> None:
    now = cn_now()
    if now.weekday() >= 5 or not time(9, 26) <= now.time() < time(9, 30):
        return

    day = now.date().isoformat()
    sent = data_dir / "auction_benchmark" / "feishu_last_sent.txt"
    try:
        last_sent = sent.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        last_sent = ""
    if last_sent == day:
        return

    url = preferences.get_feishu_webhook_url()
    if not webhook_adapter.is_valid_feishu_url(url):
        logger.warning("竞价榜单未推送：请配置有效的飞书 Webhook")
        return
    if trading_day.is_trading_day(now) is False:
        return

    lines = []
    for item in auction_benchmark.fetch_exact_auction_items(now.date()):
        symbol = item.get("thscode") or item.get("ticker")
        if not symbol:
            continue
        name = item.get("name") or symbol
        pct = item.get("auction_pct")
        change = f"{pct:+.2f}%" if isinstance(pct, (int, float)) and math.isfinite(pct) else "—"
        tags = item.get("tags")
        tag_text = "、".join(map(str, tags)) if isinstance(tags, list) else ""
        line = f"{len(lines) + 1}. {name}（{symbol}）  竞价 {change}"
        lines.append(f"{line}  |  {tag_text}" if tag_text else line)

    if not lines:
        logger.info("竞价榜单未推送：%s 暂无当日数据", day)
        return
    if cn_now().time() >= time(9, 30):
        return

    sent.parent.mkdir(parents=True, exist_ok=True)
    if not webhook_adapter.send_feishu(
        url, f"竞价异动榜单 · {day}", "\n".join(lines),
        secret=preferences.get_feishu_webhook_secret(), max_attempts=1,
    ):
        logger.warning("竞价榜单飞书推送失败: %s", day)
        return

    atomic_write_text(sent, day + "\n")
    logger.info("竞价榜单飞书推送成功: %s, %d 只", day, len(lines))
