import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from pricing import compute_suggestion

def test_compute_suggestion_respects_min_price():
    rows = [{"total": t} for t in [10, 11, 12, 100, 101, 102]]
    total, row, used = compute_suggestion(rows, min_price=50)
    assert total == 100
    assert row["total"] == 100
    assert all(r["total"] >= 50 for r in used)

def test_compute_suggestion_respects_max_price():
    rows = [{"total": t} for t in [10, 11, 12, 100, 101, 102]]
    total, row, used = compute_suggestion(rows, max_price=50)
    assert total == 10
    assert row["total"] == 10
    assert all(r["total"] <= 50 for r in used)
