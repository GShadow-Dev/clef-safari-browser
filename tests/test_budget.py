from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest


def test_failed_requests_keep_reservations_across_restarts(tmp_path):
    from clef_browser.budget import Budget, BudgetExceeded

    path = tmp_path / "usage.sqlite"
    budget = Budget(path, limit=30)
    reservation = budget.reserve("clef-flash", {"state": "x" * 1000})
    assert reservation.neurons > 0
    restarted = Budget(path, limit=30)
    assert restarted.usage()["reserved_neurons"] == reservation.neurons
    with pytest.raises(BudgetExceeded):
        restarted.reserve("clef-flash", {"state": "x" * 1000})


def test_concurrent_process_connections_cannot_overdraw(tmp_path):
    from clef_browser.budget import Budget, BudgetExceeded

    path = tmp_path / "usage.sqlite"
    Budget(path, limit=30)

    def reserve(_):
        try:
            Budget(path, limit=30).reserve("clef-flash", {"state": "x" * 1000})
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(reserve, range(6))) == 1
    assert Budget(path, limit=30).usage()["reserved_neurons"] <= 30


def test_budget_rolls_over_at_utc_midnight(tmp_path):
    from clef_browser.budget import Budget

    day = [datetime(2026, 10, 7, 23, 59, tzinfo=UTC)]
    budget = Budget(tmp_path / "usage.sqlite", clock=lambda: day[0])
    budget.reserve("clef", {"state": "hello"})
    assert budget.usage()["requests"] == 1
    day[0] = datetime(2026, 10, 8, tzinfo=UTC)
    assert budget.usage()["requests"] == 0


def test_unicode_and_schema_count_toward_reservation(tmp_path):
    from clef_browser.budget import Budget

    budget = Budget(tmp_path / "usage.sqlite")
    small = budget.reserve("clef-flash", {"state": "hi"})
    large = budget.reserve("clef-flash", {"state": "你" * 1000, "questions": {"a": "y" * 3000}})
    assert large.input_bound >= 6000
    assert large.neurons > small.neurons


def test_unexpected_usage_is_charged_and_stops_requests(tmp_path):
    from clef_browser.budget import Budget, BudgetExceeded

    budget = Budget(tmp_path / "usage.sqlite", limit=100)
    reservation = budget.reserve("clef", {"state": "hi"})
    with pytest.raises(BudgetExceeded):
        budget.record(reservation, {"input_tokens": 100000, "output_tokens": 0})
    assert budget.usage()["reserved_neurons"] > 100
    with pytest.raises(BudgetExceeded):
        budget.reserve("clef-flash", {"state": "hi"})


def test_paid_models_and_unsafe_limits_are_rejected(tmp_path):
    from clef_browser.budget import Budget

    with pytest.raises(ValueError):
        Budget(tmp_path / "usage.sqlite", limit=10001)
    with pytest.raises(ValueError):
        Budget(tmp_path / "usage.sqlite").reserve("glm-5.3", {"state": "hi"})


def test_usage_anomaly_blocks_new_process_until_next_utc_day(tmp_path):
    from clef_browser.budget import Budget, BudgetExceeded

    day = [datetime(2026, 10, 7, tzinfo=UTC)]
    path = tmp_path / "usage.sqlite"
    budget = Budget(path, clock=lambda: day[0])
    reservation = budget.reserve("clef-flash", {"state": "hi"})
    with pytest.raises(BudgetExceeded):
        budget.record(reservation, {"input_tokens": 3000, "output_tokens": 0})
    assert budget.usage()["reserved_neurons"] < 8000
    with pytest.raises(BudgetExceeded):
        Budget(path, clock=lambda: day[0]).reserve("clef-flash", {"state": "hi"})
    day[0] = datetime(2026, 10, 8, tzinfo=UTC)
    Budget(path, clock=lambda: day[0]).reserve("clef-flash", {"state": "hi"})
