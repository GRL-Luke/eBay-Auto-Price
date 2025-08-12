import sys
from pathlib import Path

# Ensure modules importable
sys.path.append(str(Path(__file__).resolve().parents[1] / 'eBay_pricing_v6_5'))

from app import filter_rows_by_upc
from pricing import within_range, choose_and_suggest


def test_filter_rows_by_upc_discards_mismatch():
    rows = [
        {"total": 10, "upc": "123"},
        {"total": 11, "upc": "999"},
        {"total": 12},
    ]
    filtered = filter_rows_by_upc(rows, "123")
    assert len(filtered) == 2
    assert all(r.get("upc") in (None, "123") for r in filtered)


def test_within_range_excludes_far_ebay():
    amz = 100.0
    ebay = 150.0
    assert within_range(ebay, amz, pct=0.25) is False
    pick = choose_and_suggest(amz, None)
    assert pick["source"] == "Amazon"


def test_within_range_allows_ebay():
    amz = 100.0
    ebay = 90.0
    assert within_range(ebay, amz, pct=0.25) is True
    pick = choose_and_suggest(amz, ebay)
    assert pick["source"] == "eBay"
