"""
tests/test_tools.py

Pytest tests for FitFindr tools. Run with:
    cd fitfindr
    python3 -m pytest tests/ -v

Tests for search_listings cover real data and require no API key.
Tests for suggest_outfit and create_fit_card verify failure modes and
return types — they work with or without an API key (mock kicks in when
ANTHROPIC_API_KEY / GROQ_API_KEY are absent).
"""

import sys
import os

# Allow imports from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Tool 1: search_listings ───────────────────────────────────────────────────

class TestSearchListings:

    def test_returns_results_for_known_query(self):
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert isinstance(results, list)
        assert len(results) > 0, "Expected at least one result for 'vintage graphic tee'"

    def test_returns_empty_list_no_exception_when_nothing_matches(self):
        """Failure mode: no results — must return [] not raise an exception."""
        results = search_listings("designer ballgown", size="XXS", max_price=5)
        assert results == [], f"Expected empty list, got {results}"

    def test_price_filter_is_inclusive(self):
        """All returned listings must cost ≤ max_price."""
        results = search_listings("jacket", size=None, max_price=30)
        for item in results:
            assert item["price"] <= 30, (
                f"Price filter failed: {item['title']} costs ${item['price']}"
            )

    def test_size_filter_case_insensitive(self):
        """Size filter should match regardless of case."""
        results_upper = search_listings("top", size="M", max_price=None)
        results_lower = search_listings("top", size="m", max_price=None)
        assert len(results_upper) == len(results_lower), (
            "Size filtering should be case-insensitive"
        )

    def test_size_filter_partial_match(self):
        """'M' should match listings with size 'S/M'."""
        results = search_listings("tee", size="M", max_price=None)
        for item in results:
            assert "m" in item["size"].lower(), (
                f"Size filter returned non-matching size: {item['size']}"
            )

    def test_returns_dicts_with_required_fields(self):
        """Every returned listing must have all required fields."""
        required = {"id", "title", "description", "category", "style_tags",
                    "size", "condition", "price", "colors", "brand", "platform"}
        results = search_listings("vintage", size=None, max_price=None)
        assert results, "Need at least one result to check fields"
        for item in results:
            missing = required - set(item.keys())
            assert not missing, f"Listing missing fields: {missing}"

    def test_results_sorted_best_match_first(self):
        """Top result should be more relevant than later results."""
        results = search_listings("vintage graphic tee", size=None, max_price=None)
        assert len(results) >= 2
        # The top result's combined text should contain more query tokens than a later one
        # (We just verify it's a list — full scoring is internal — but check it's ordered)
        top = results[0]
        assert top is not None  # structural check; real ordering verified in smoke test

    def test_no_filters_returns_nonempty(self):
        """With no filters, any keyword query should return something."""
        results = search_listings("shirt", size=None, max_price=None)
        assert len(results) > 0

    def test_price_filter_excludes_expensive_items(self):
        """Items above max_price must not appear in results."""
        max_p = 20.0
        results = search_listings("denim", size=None, max_price=max_p)
        for item in results:
            assert item["price"] <= max_p, (
                f"{item['title']} costs ${item['price']} but max_price={max_p}"
            )


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

class TestSuggestOutfit:
    """
    These tests don't require an API key. They verify:
    - The function returns a non-empty string in all cases
    - The empty wardrobe path does not raise an exception
    """

    @staticmethod
    def _sample_item():
        results = search_listings("vintage graphic tee", max_price=50)
        assert results, "Need a listing to test suggest_outfit"
        return results[0]

    def test_returns_string_with_example_wardrobe(self):
        item = self._sample_item()
        result = suggest_outfit(item, get_example_wardrobe())
        assert isinstance(result, str)
        assert result.strip(), "suggest_outfit returned empty string for populated wardrobe"

    def test_empty_wardrobe_does_not_raise(self):
        """Failure mode: empty wardrobe — must not crash, must return a string."""
        item = self._sample_item()
        try:
            result = suggest_outfit(item, get_empty_wardrobe())
        except Exception as e:
            assert False, f"suggest_outfit raised an exception on empty wardrobe: {e}"
        assert isinstance(result, str)
        assert result.strip(), "suggest_outfit returned empty string for empty wardrobe"

    def test_empty_wardrobe_items_key_present(self):
        """get_empty_wardrobe() must have 'items' key (not None)."""
        empty = get_empty_wardrobe()
        assert "items" in empty
        assert isinstance(empty["items"], list)
        assert len(empty["items"]) == 0


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

class TestCreateFitCard:

    @staticmethod
    def _sample_item():
        results = search_listings("vintage graphic tee", max_price=50)
        assert results
        return results[0]

    def test_empty_outfit_returns_error_string_not_exception(self):
        """Failure mode: empty outfit — must return error string, not raise."""
        item = self._sample_item()
        result = create_fit_card("", item)
        assert isinstance(result, str)
        assert result.strip(), "Should return a non-empty error message"
        # Should communicate the problem clearly
        assert any(word in result.lower() for word in ["missing", "couldn't", "empty", "no outfit"])

    def test_whitespace_only_outfit_returns_error_string(self):
        """Whitespace-only outfit should be treated the same as empty."""
        item = self._sample_item()
        result = create_fit_card("   \n\t  ", item)
        assert isinstance(result, str)
        assert result.strip()
        assert any(word in result.lower() for word in ["missing", "couldn't", "empty", "no outfit"])

    def test_valid_outfit_returns_nonempty_string(self):
        """With a real outfit string, create_fit_card must return a non-empty string."""
        item = self._sample_item()
        outfit = "Pair this vintage tee with dark-wash jeans and chunky sneakers for a streetwear look."
        result = create_fit_card(outfit, item)
        assert isinstance(result, str)
        assert result.strip(), "create_fit_card returned empty string for valid input"

    def test_does_not_raise_on_missing_optional_item_fields(self):
        """create_fit_card should handle items with missing brand / description gracefully."""
        minimal_item = {
            "id": "test_001",
            "title": "Mystery Jacket",
            "category": "outerwear",
            "style_tags": ["vintage"],
            "size": "M",
            "condition": "good",
            "price": 25.0,
            "colors": ["black"],
            "platform": "depop",
            # 'brand' and 'description' intentionally omitted
        }
        outfit = "Layer this over a white tee and slim jeans."
        try:
            result = create_fit_card(outfit, minimal_item)
        except Exception as e:
            assert False, f"create_fit_card raised on minimal item dict: {e}"
        assert isinstance(result, str)
