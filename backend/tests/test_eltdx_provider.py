"""eltdx plugin contract tests without live network access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.data_providers.capabilities import build_capability_matrix
from app.plugins.eltdx import provider as ep
from app.plugins.eltdx.provider import EltdxProvider


def _bar(stamp: datetime, close: float = 10.2):
    return SimpleNamespace(
        time=stamp, open=10.0, high=10.5, low=9.9, close=close,
        volume_lots=1234.8, amount=1_250_000.0,
    )


def _snapshot():
    return SimpleNamespace(
        exchange="sz", code="000001", last_price=10.2, pre_close_price=10.0,
        open_price=10.05, high_price=10.3, low_price=9.95,
        total_hand=12345, amount=12_345_678.0,
    )


class _Bars:
    def __init__(self, stamp):
        self.stamp = stamp

    def get(self, codes, **kwargs):
        requested = [codes] if isinstance(codes, str) else list(codes)
        series = {code: SimpleNamespace(bars=(_bar(self.stamp),)) for code in requested}
        return series[requested[0]] if isinstance(codes, str) else series


class _Quotes:
    def get_snapshots(self, codes):
        return [_snapshot() for _ in codes]

    def get_depth(self, codes):
        def level(price, volume):
            return SimpleNamespace(price=price, volume=volume)

        return SimpleNamespace(records=(SimpleNamespace(
            exchange="sz", code="000001",
            buy_levels=(level(10.1, 100), level(10.0, 200)),
            sell_levels=(level(10.2, 300), level(10.3, 400)),
        ),))


class _Client:
    def __init__(self, stamp):
        self.bars = _Bars(stamp)
        self.quotes = _Quotes()
        self.codes = SimpleNamespace(all_a_shares=lambda: ["sz000001"])

    def close(self):
        pass


def _provider(stamp=None):
    provider = EltdxProvider()
    provider._client = _Client(stamp or datetime.now(timezone(timedelta(hours=8))))
    return provider


def test_manifest_and_declared_datasets():
    from app.data_providers.custom import loader

    manifest = loader.plugin_manifest("eltdx")
    assert manifest["entry"] == "app.plugins.eltdx.provider:EltdxProvider"
    assert manifest["datasets"] == ["realtime", "depth5", "daily", "minute", "full_minute"]
    assert set(EltdxProvider().config.datasets) == set(manifest["datasets"])


def test_availability_is_optional(monkeypatch):
    monkeypatch.setattr(ep, "_module_available", lambda: False)
    assert ep.availability()[0] is False
    monkeypatch.setattr(ep, "_module_available", lambda: True)
    assert ep.availability() == (True, "ok")


def test_realtime_maps_units_and_decimal_change():
    rows = _provider().get_realtime_symbols(["000001.SZ"])
    assert rows and rows[0]["symbol"] == "000001.SZ"
    assert rows[0]["volume"] == 12345
    assert rows[0]["amount"] == 12_345_678.0
    assert rows[0]["change_pct"] == pytest.approx(0.02)


def test_daily_and_minute_use_beijing_naive_timestamps():
    stamp = datetime(2026, 11, 16, 15, 0, tzinfo=timezone(timedelta(hours=8)))
    provider = _provider(stamp)
    daily = provider.get_daily(
        ["000001.SZ"], datetime(2026, 11, 1), datetime(2026, 11, 16, 23, 59),
    )
    assert daily.height == 1
    assert daily.row(0, named=True)["volume"] == 1234

    minute = provider.get_minute(
        ["000001.SZ"], datetime(2026, 11, 16, 9, 30), datetime(2026, 11, 16, 15, 1),
    )
    assert minute.height == 1
    assert minute.row(0, named=True)["datetime"] == datetime(2026, 11, 16, 15, 0)


def test_depth_and_full_minute_contracts():
    stamp = datetime.now(timezone(timedelta(hours=8)))
    provider = _provider(stamp)
    depth = provider.get_depth_batch(["000001.SZ"])
    assert depth["000001.SZ"]["bid_prices"] == [10.1, 10.0]
    assert depth["000001.SZ"]["ask_volumes"] == [300, 400]

    latest = provider.get_intraday_latest(["000001.SZ"], count=3)
    assert latest.height == 1
    assert latest.columns == list(ep._MINUTE_SCHEMA)


def test_capability_matrix_routes_only_real_eltdx_datasets(monkeypatch):
    from app.data_providers import capabilities

    monkeypatch.setattr(capabilities.custom_sources, "list_sources", lambda: [])
    monkeypatch.setattr(capabilities.custom_sources, "list_plugins", lambda: [{
        "name": "eltdx",
        "display_name": "eltdx",
        "datasets": list(ep._DATASETS),
        "available": True,
        "status": "ok",
    }])
    current = {row["field"]: "eltdx" for row in capabilities.CAPABILITY_REGISTRY}
    matrix = build_capability_matrix(current, tickflow_tier="none")
    by_id = {row["id"]: row for row in matrix["capabilities"]}
    for dataset in ep._DATASETS:
        assert by_id[dataset]["usable"] is True
        assert "eltdx" in [candidate["name"] for candidate in by_id[dataset]["candidates"]]
    assert by_id["adj_factor"]["usable"] is False
    assert by_id["financial"]["usable"] is False
