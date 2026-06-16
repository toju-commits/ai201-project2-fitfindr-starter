"""
Tests for FitFindr Project 2.

These tests cover the important agent behaviors:
1. Search returns relevant listings.
2. Search respects no-result cases.
3. Query parsing extracts price and size.
4. The full agent loop succeeds on a happy path.
5. The full agent loop stops cleanly on no-results.

Why these tests matter:
The project is a multi-tool agent, so we need to test both individual tools
and the full chain.
"""
import sys
from pathlib import Path

# Add the project root folder to Python's import path.
# This lets tests import agent.py, tools.py, and utils/ even though the test file
# lives inside the tests/ folder.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent import parse_query, run_agent
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


def test_parse_query_extracts_size_and_price():
    """
    The parser should convert normal user language into structured parameters.
    """
    parsed = parse_query("platform sneakers size 8 under $60")

    assert parsed["description"] == "platform sneakers"
    assert parsed["size"] == "8"
    assert parsed["max_price"] == 60.0


def test_search_listings_finds_graphic_tee_under_budget():
    """
    Search should return relevant listings under the user's budget.
    """
    results = search_listings("vintage graphic tee", max_price=30)

    assert len(results) > 0
    assert results[0]["price"] <= 30
    assert "tee" in results[0]["title"].lower() or "graphic tee" in results[0]["style_tags"]


def test_search_listings_no_fake_boot_match():
    """
    Search should not return loose synonym-only matches.

    Example:
    If the user asks for black combat boots in size 8 and the dataset does not
    contain that item, we should return no results instead of pretending white
    sneakers are a match.
    """
    results = search_listings("black combat boots", size="8", max_price=60)

    assert results == []


def test_suggest_outfit_handles_empty_wardrobe():
    """
    Outfit suggestions should still work for a new user with no wardrobe.
    """
    item = search_listings("vintage graphic tee", max_price=30)[0]
    outfit = suggest_outfit(item, get_empty_wardrobe())

    assert isinstance(outfit, str)
    assert len(outfit.strip()) > 0


def test_create_fit_card_requires_outfit():
    """
    Fit card generation should fail gracefully when outfit text is missing.
    """
    result = create_fit_card("", {"title": "Test Item", "price": 10, "platform": "depop"})

    assert "outfit suggestion" in result.lower()


def test_run_agent_happy_path():
    """
    The full planning loop should complete for a valid query.
    """
    session = run_agent("platform sneakers size 8 under $60", get_example_wardrobe())

    assert session["error"] is None
    assert session["selected_item"] is not None
    assert session["outfit_suggestion"]
    assert session["fit_card"]


def test_run_agent_no_results_path():
    """
    The full planning loop should stop cleanly when no listing matches.
    """
    session = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())

    assert session["error"] is not None
    assert session["selected_item"] is None
    assert session["fit_card"] is None