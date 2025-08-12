import sys
from pathlib import Path

# Ensure pricing module is importable
sys.path.append(str(Path(__file__).resolve().parents[1] / "eBay_pricing_v6_5"))
from pricing import choose_and_suggest


def test_choose_and_suggest_prefers_lower_ebay():
    """When both competitors are available, the lower eBay price is undercut to $18.99."""
    result = choose_and_suggest(amazon_total=20.00, ebay_total=19.50)
    assert result["source"] == "eBay"
    assert result["suggested"] == 18.99


def test_choose_and_suggest_only_amazon():
    """With only Amazon provided, it is undercut and rounded to $14.99."""
    result = choose_and_suggest(amazon_total=15.75, ebay_total=None)
    assert result["suggested"] == 14.99
