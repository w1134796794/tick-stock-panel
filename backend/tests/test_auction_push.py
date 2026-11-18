from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.jobs import auction_push, daily_pipeline
from app.market_time import CN_TZ
from app.services import auction_benchmark
from app.tickflow.capabilities import CapabilitySet


@pytest.mark.parametrize("enabled", [False, True])
def test_scheduler_registers_opt_in_shanghai_window(tmp_path, monkeypatch, enabled):
    scheduler = Mock()
    monkeypatch.setattr(daily_pipeline, "AsyncIOScheduler", lambda **_: scheduler)
    monkeypatch.setattr(daily_pipeline.settings, "auction_feishu_push_enabled", enabled)
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    daily_pipeline.start_scheduler(repo, CapabilitySet(set()))

    jobs = [call for call in scheduler.add_job.call_args_list if call.kwargs["id"] == "auction_feishu_push"]
    assert len(jobs) == int(enabled)
    if enabled:
        job = jobs[0]
        assert job.args == (auction_push.push_auction_benchmark,)
        assert job.kwargs["args"] == [tmp_path]
        trigger = job.kwargs["trigger"]
        before = datetime(2026, 11, 19, 9, 25, tzinfo=CN_TZ)
        assert trigger.get_next_fire_time(None, before) == before.replace(minute=26)
        assert job.kwargs["max_instances"] == 1


@pytest.fixture
def push_env(monkeypatch):
    now = datetime(2026, 11, 19, 9, 26, tzinfo=CN_TZ)
    clock = Mock(return_value=now)
    calendar = Mock(return_value=True)
    fetch = Mock(return_value={
        "date": "2026-11-19",
        "item": [{"thscode": "600519.SH", "name": "贵州茅台",
                  "auction_pct": 1.25, "tags": ["白酒"]}],
    })
    send = Mock(return_value=True)
    url = "https://open.feishu.cn/open-apis/bot/v2/hook/test"
    monkeypatch.setattr(auction_push, "cn_now", clock)
    monkeypatch.setattr(auction_push.trading_day, "is_trading_day", calendar)
    monkeypatch.setattr(auction_benchmark, "_provider", lambda: SimpleNamespace(short_term_benchmark=fetch))
    monkeypatch.setattr(auction_push.preferences, "get_feishu_webhook_url", lambda: url)
    monkeypatch.setattr(auction_push.preferences, "get_feishu_webhook_secret", lambda: "test-secret")
    monkeypatch.setattr(auction_push.webhook_adapter, "send_feishu", send)
    return now, clock, calendar, fetch, send


def test_sends_exact_day_and_deduplicates_after_success(tmp_path, push_env):
    _, _, _, fetch, send = push_env
    auction_push.push_auction_benchmark(tmp_path)
    auction_push.push_auction_benchmark(tmp_path)

    fetch.assert_called_once_with("2026-11-19")
    send.assert_called_once()
    _, title, body = send.call_args.args
    assert "2026-11-19" in title
    assert "贵州茅台（600519.SH）" in body and "+1.25%" in body and "白酒" in body
    assert send.call_args.kwargs["secret"] == "test-secret"
    assert (tmp_path / "auction_benchmark/feishu_last_sent.txt").read_text().strip() == "2026-11-19"


@pytest.mark.parametrize("upstream_date", ["2026-11-18", None])
def test_rejects_stale_or_undated_rows(tmp_path, push_env, upstream_date):
    _, _, _, fetch, send = push_env
    fetch.return_value["date"] = upstream_date
    auction_push.push_auction_benchmark(tmp_path)
    send.assert_not_called()


def test_retries_on_a_later_slot_after_failure(tmp_path, push_env):
    now, clock, _, _, send = push_env
    send.side_effect = [False, True]
    auction_push.push_auction_benchmark(tmp_path)
    clock.return_value = now.replace(minute=27)
    auction_push.push_auction_benchmark(tmp_path)
    auction_push.push_auction_benchmark(tmp_path)
    assert send.call_count == 2


def test_skips_holiday_and_times_outside_window(tmp_path, push_env):
    now, clock, calendar, fetch, send = push_env
    calendar.return_value = False
    auction_push.push_auction_benchmark(tmp_path)
    calendar.return_value = True
    for minute in (25, 30):
        clock.return_value = now.replace(minute=minute)
        auction_push.push_auction_benchmark(tmp_path)
    fetch.assert_not_called()
    send.assert_not_called()
