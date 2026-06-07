"""Tests for feedback parser (task-010)."""

import pytest
from marktplaats_bot.feedback import parse_feedback


class TestParseFeedback:
    def test_budget_euro_sign(self):
        r = parse_feedback("budget €300")
        assert r["max_budget"] == 300.0

    def test_budget_max_keyword(self):
        r = parse_feedback("max 500 euro")
        assert r["max_budget"] == 500.0

    def test_budget_dutch(self):
        r = parse_feedback("niet meer dan 200")
        assert r["max_budget"] == 200.0

    def test_budget_english(self):
        r = parse_feedback("under 150")
        assert r["max_budget"] == 150.0

    def test_radius_within(self):
        r = parse_feedback("within 10 km")
        assert r["radius_km"] == 10

    def test_radius_dutch(self):
        r = parse_feedback("binnen 15 km")
        assert r["radius_km"] == 15

    def test_exclude_business_english(self):
        r = parse_feedback("too many business listings")
        assert r["exclude_business"] is True

    def test_exclude_business_dutch(self):
        r = parse_feedback("geen bedrijven alsjeblieft")
        assert r["exclude_business"] is True

    def test_exclude_business_only_private(self):
        r = parse_feedback("only private sellers")
        assert r["exclude_business"] is True

    def test_lower_threshold(self):
        r = parse_feedback("not relevant enough")
        assert r.get("relevance_threshold", 60) < 60

    def test_raise_threshold(self):
        r = parse_feedback("too many results, irrelevant ones")
        assert r.get("relevance_threshold", 60) > 60

    def test_max_age(self):
        r = parse_feedback("maximum 5 jaar old")
        assert r["max_age_years"] == 5

    def test_max_age_english(self):
        r = parse_feedback("not older than 3 years")
        assert r["max_age_years"] == 3

    def test_empty_text_returns_empty_dict(self):
        r = parse_feedback("")
        assert r == {}

    def test_no_matches_returns_empty_dict(self):
        r = parse_feedback("looks great, keep it as is")
        assert r == {}

    def test_multiple_changes(self):
        r = parse_feedback("budget €400, binnen 20 km, geen bedrijven")
        assert r["max_budget"] == 400.0
        assert r["radius_km"] == 20
        assert r["exclude_business"] is True

    def test_decimal_budget(self):
        r = parse_feedback("max 299,99 euro")
        assert r["max_budget"] == pytest.approx(299.99)
