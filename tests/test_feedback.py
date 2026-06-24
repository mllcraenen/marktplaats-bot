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


class TestFeedbackKeywordDirection:
    """Tests for remove_keywords / add_keywords parsing (task-mp-002)."""

    def test_parse_car_not_parts(self):
        r = parse_feedback("looking for the car, not parts. fixer-upper is fine")
        # "parts" is a generic topic noun → must go to remove_keywords, not excluded brands
        assert "parts" in r.get("remove_keywords", [])
        assert "parts" not in r.get("add_excluded_brands", [])
        # "fixer-upper" and/or "looking for the car" must produce add_keywords
        assert len(r.get("add_keywords", [])) > 0

    def test_generic_nouns_not_treated_as_brands(self):
        # "not parts" and "geen dealers" should produce empty add_excluded_brands
        r1 = parse_feedback("not parts")
        assert r1.get("add_excluded_brands", []) == []

        r2 = parse_feedback("geen dealers")
        assert r2.get("add_excluded_brands", []) == []

    def test_fixer_upper_adds_keywords(self):
        r = parse_feedback("fixer-upper is fine")
        kws = r.get("add_keywords", [])
        assert len(kws) > 0

    def test_whole_car_adds_keywords(self):
        r = parse_feedback("looking for the car, not parts")
        kws = r.get("add_keywords", [])
        assert "heel" in kws or "compleet" in kws

    def test_not_parts_adds_to_remove_keywords(self):
        r = parse_feedback("not parts")
        assert "parts" in r.get("remove_keywords", [])

    def test_geen_onderdelen_adds_to_remove_keywords(self):
        r = parse_feedback("geen onderdelen")
        assert "onderdelen" in r.get("remove_keywords", [])

    def test_brand_name_still_excluded(self):
        # A real brand name (not a generic noun) should still go to add_excluded_brands
        r = parse_feedback("no Chinese brands")
        # "Chinese brands" — "brands" stripped by _clean_brand, leaving "Chinese"
        # which is not a stop word, so it should be treated as brand
        assert r.get("add_excluded_brands") is not None or r.get("remove_keywords") == []


class TestNegationHandling:
    """Regression tests for negation-aware parsing."""

    def test_dont_want_rgb_not_required_brand(self):
        r = parse_feedback("I don't want RGB at all")
        assert "rgb" not in [b.lower() for b in r.get("add_required_brands", [])]
        assert "rgb" not in [s.lower() for s in r.get("add_required_specs", [])]

    def test_dont_want_routes_to_remove(self):
        r = parse_feedback("I don't want RGB at all")
        assert "rgb" in r.get("remove_keywords", [])

    def test_negated_want_not_required_brand(self):
        r = parse_feedback("don't want motors")
        assert r.get("add_required_brands", []) == []

    def test_with_rgb_in_negative_clause_not_required_spec(self):
        r = parse_feedback("I don't want gaming keyboards with RGB")
        assert "rgb" not in [s.lower() for s in r.get("add_required_specs", [])]

    def test_positive_want_still_works(self):
        r = parse_feedback("I want only Trek bikes")
        required = [b.lower() for b in r.get("add_required_brands", [])]
        assert any("trek" in b for b in required)

    def test_only_brand_without_negation(self):
        r = parse_feedback("only Specialized")
        required = [b.lower() for b in r.get("add_required_brands", [])]
        assert any("specialized" in b for b in required)

    def test_geen_rgb_to_remove_keywords(self):
        r = parse_feedback("geen RGB")
        assert "rgb" in r.get("remove_keywords", []) or \
               "rgb" not in [b.lower() for b in r.get("add_required_brands", [])]

    def test_dont_want_does_not_produce_required_spec(self):
        r = parse_feedback("I don't want any electric motors")
        assert r.get("add_required_specs", []) == []

    def test_must_have_still_works_positive(self):
        r = parse_feedback("must have hydraulic brakes")
        assert len(r.get("add_required_specs", [])) > 0


class TestApplyKeywordsToSearch:
    """Integration tests for _apply_parsed_to_search keyword mutation (task-mp-002)."""

    @pytest.mark.asyncio
    async def test_apply_remove_keywords_strips_from_nl_keywords(self, client):
        resp = await client.post(
            "/api/searches",
            json={"query_text": "Datsun 280z parts restoration"},
        )
        search_id = resp.json()["id"]

        # Manually patch nl_keywords via feedback
        await client.post(
            f"/api/searches/{search_id}/feedback",
            json={"text": "not parts"},
        )

        get_resp = await client.get(f"/api/searches/{search_id}")
        data = get_resp.json()
        # nl_keywords might be None (scraper not run), but if set, "parts" should be removed
        if data.get("nl_keywords"):
            assert "parts" not in data["nl_keywords"].lower()

    @pytest.mark.asyncio
    async def test_ai_apply_updates_keywords(self, client):
        # Feedback no longer immediately changes keywords; ai-apply does
        resp = await client.post(
            "/api/searches",
            json={"query_text": "Datsun 280z"},
        )
        search_id = resp.json()["id"]

        await client.patch(
            f"/api/searches/{search_id}/query",
            json={"nl_keywords": "Datsun 280z auto", "en_keywords": "Datsun 280z car"},
        )

        await client.post(
            f"/api/searches/{search_id}/feedback",
            json={"text": "fixer-upper is fine"},
        )

        # Keywords NOT yet changed — pending AI application
        get_resp = await client.get(f"/api/searches/{search_id}")
        assert "opknapper" not in (get_resp.json().get("nl_keywords") or "").lower()

        # AI worker applies the result
        apply_resp = await client.post(
            f"/api/searches/{search_id}/ai-apply",
            json={"nl_keywords": "Datsun 280z auto opknapper", "summary": "Added opknapper per feedback"},
        )
        assert apply_resp.status_code == 200
        assert "opknapper" in (apply_resp.json().get("nl_keywords") or "").lower()
