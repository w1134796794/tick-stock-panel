from datetime import date
from types import SimpleNamespace

from app.api.strategy import _run_all_with_unavailable


class _Engine:
    def run_all(
        self,
        context,
        params_map=None,
        overrides_map=None,
        *,
        strategy_ids=None,
        parallel=True,
    ):
        if len(strategy_ids) > 1:
            raise ValueError("batch contains unavailable evidence")
        strategy_id = strategy_ids[0]
        if strategy_id == "missing":
            raise ValueError("missing local provider data")
        return {strategy_id: SimpleNamespace(total=7)}


def test_run_all_isolates_strategy_with_unavailable_evidence():
    results = _run_all_with_unavailable(
        _Engine(),
        object(),
        strategy_ids=["ready", "missing"],
        params_map={},
        overrides_map={},
        as_of=date(2026, 11, 13),
    )

    assert results["ready"] == {"total": 7, "as_of": "2026-11-13"}
    assert results["missing"] == {
        "total": 0,
        "as_of": "2026-11-13",
        "available": False,
        "error": "missing local provider data",
    }
