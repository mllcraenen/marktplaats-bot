"""Tests for the rule-based analyzer (task-009)."""

import pytest
from marktplaats_bot.analyzer import (
    analyse,
    detect_seller_type,
    score_deal,
    score_quality,
    score_relevance,
)
from marktplaats_bot.scraper import ScrapedListing


def make_listing(**kwargs) -> ScrapedListing:
    defaults = dict(
        listing_id="123456",
        title="Vintage fiets",
        url="https://www.marktplaats.nl/a123456-vintage-fiets",
        price=150.0,
        distance_km=5.0,
        posted_at=None,
        photo_count=3,
        description="Mooie vintage fiets in goede staat. 28 inch wielen.",
        seller_type="unknown",
        seller_name="",
    )
    defaults.update(kwargs)
    return ScrapedListing(**defaults)


# ---------------------------------------------------------------------------
# detect_seller_type
# ---------------------------------------------------------------------------

class TestDetectSellerType:
    def test_explicit_private(self):
        assert detect_seller_type(make_listing(seller_type="private")) == "private"

    def test_explicit_business(self):
        assert detect_seller_type(make_listing(seller_type="business")) == "business"

    def test_btw_in_description(self):
        listing = make_listing(description="Prijs excl. btw, zakelijk")
        assert detect_seller_type(listing) == "business"

    def test_kvk_number_in_description(self):
        listing = make_listing(description="KvK 12345678, leverancier")
        assert detect_seller_type(listing) == "business"

    def test_dealer_keyword(self):
        listing = make_listing(description="Wij zijn dealer en groothandel")
        assert detect_seller_type(listing) == "business"

    def test_webshop_keyword(self):
        listing = make_listing(description="Gekocht via webshop, teruggestuurde retour")
        assert detect_seller_type(listing) == "business"

    def test_plain_listing_is_private(self):
        listing = make_listing(description="Goede fiets, goed onderhouden")
        assert detect_seller_type(listing) == "private"

    def test_seller_name_business(self):
        listing = make_listing(seller_name="Dealer Rotterdam", seller_type="unknown", description="")
        assert detect_seller_type(listing) == "business"


# ---------------------------------------------------------------------------
# score_relevance
# ---------------------------------------------------------------------------

class TestScoreRelevance:
    def _call(self, listing, keywords=None, specs=None, brands=None, excl_brands=None,
              budget=None, excl_biz=False):
        return score_relevance(
            listing,
            query_keywords=keywords or [],
            required_specs=specs or [],
            required_brands=brands or [],
            excluded_brands=excl_brands or [],
            max_budget=budget,
            exclude_business=excl_biz,
        )

    def test_baseline_no_filters(self):
        listing = make_listing()
        score, _ = self._call(listing)
        assert score == 50

    def test_keyword_match_boosts_score(self):
        listing = make_listing(title="Vintage fiets Batavus")
        score, reason = self._call(listing, keywords=["vintage", "fiets"])
        assert score > 50
        assert "keywords" in reason

    def test_no_keyword_match(self):
        listing = make_listing(title="Auto Ford", description="Nette auto in goede staat")
        score, _ = self._call(listing, keywords=["fiets", "vintage"])
        assert score == 50  # no match = no bonus (baseline)

    def test_required_brand_hit(self):
        listing = make_listing(title="Batavus fiets")
        score, reason = self._call(listing, brands=["Batavus"])
        assert score > 50
        assert "brand match" in reason

    def test_required_brand_miss(self):
        listing = make_listing(title="Gazelle fiets")
        score, reason = self._call(listing, brands=["Batavus"])
        assert score < 50
        assert "no required brand" in reason

    def test_excluded_brand_zeroes_score(self):
        listing = make_listing(title="Batavus fiets")
        score, reason = self._call(listing, excl_brands=["Batavus"])
        assert score == 0
        assert "excluded" in reason

    def test_over_budget_penalty(self):
        listing = make_listing(price=500.0)
        score, reason = self._call(listing, budget=200.0)
        assert score < 50
        assert "over budget" in reason

    def test_well_under_budget_bonus(self):
        listing = make_listing(price=50.0)
        score, reason = self._call(listing, budget=200.0)
        assert score > 50

    def test_business_penalty_when_excluded(self):
        listing = make_listing(description="Prijs excl. btw")
        score, reason = self._call(listing, excl_biz=True)
        assert score < 50
        assert "business" in reason

    def test_spec_overlap(self):
        listing = make_listing(description="28 inch wielen, 21 versnellingen")
        score, reason = self._call(listing, specs=["28 inch", "21 versnellingen"])
        assert score > 50

    def test_score_clamped_0_100(self):
        listing = make_listing(price=9999.0, description="btw excl.")
        score, _ = self._call(listing, budget=100.0, excl_biz=True)
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# score_deal
# ---------------------------------------------------------------------------

class TestScoreDeal:
    def test_no_price_returns_50(self):
        listing = make_listing(price=None)
        score, reason = score_deal(listing, None, [])
        assert score == 50
        assert "no price" in reason

    def test_far_below_median(self):
        listing = make_listing(price=50.0)
        score, reason = score_deal(listing, None, [200.0, 210.0, 190.0, 205.0])
        assert score >= 75
        assert "median" in reason

    def test_above_median(self):
        listing = make_listing(price=300.0)
        score, reason = score_deal(listing, None, [200.0, 210.0, 190.0, 205.0])
        assert score <= 40

    def test_budget_heuristic_under_40pct(self):
        listing = make_listing(price=39.0)
        score, reason = score_deal(listing, 100.0, [])
        assert score >= 80
        assert "budget" in reason

    def test_budget_heuristic_within_budget(self):
        listing = make_listing(price=90.0)
        score, reason = score_deal(listing, 100.0, [])
        assert score < 50

    def test_no_reference_returns_50(self):
        listing = make_listing(price=100.0)
        score, reason = score_deal(listing, None, [])
        assert score == 50

    def test_score_clamped(self):
        listing = make_listing(price=1.0)
        score, _ = score_deal(listing, 1000.0, [])
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# score_quality
# ---------------------------------------------------------------------------

class TestScoreQuality:
    def test_good_listing(self):
        listing = make_listing(photo_count=5, description="x" * 300, price=100.0)
        score, _ = score_quality(listing)
        assert score >= 70

    def test_no_photos_no_desc(self):
        listing = make_listing(photo_count=0, description="", price=None)
        score, reason = score_quality(listing)
        assert score == 0

    def test_single_photo(self):
        listing = make_listing(photo_count=1, description="", price=None)
        score, _ = score_quality(listing)
        assert score == 15

    def test_three_photos(self):
        listing = make_listing(photo_count=3, description="", price=None)
        score, _ = score_quality(listing)
        assert score == 30

    def test_long_description(self):
        listing = make_listing(photo_count=0, description="x" * 350, price=None)
        score, _ = score_quality(listing)
        assert score == 40

    def test_has_price_bonus(self):
        listing_with = make_listing(photo_count=0, description="", price=50.0)
        listing_without = make_listing(photo_count=0, description="", price=None)
        s_with, _ = score_quality(listing_with)
        s_without, _ = score_quality(listing_without)
        assert s_with > s_without

    def test_score_clamped_100(self):
        listing = make_listing(photo_count=10, description="x" * 500, price=50.0)
        score, _ = score_quality(listing)
        assert score == 100


# ---------------------------------------------------------------------------
# analyse (combined)
# ---------------------------------------------------------------------------

class TestAnalyse:
    def test_combined_output(self):
        listing = make_listing(
            title="Batavus fiets 28 inch",
            description="Goede staat, 3 versnellingen, 28 inch wielen.",
            photo_count=4,
            price=120.0,
        )
        result = analyse(
            listing,
            query_keywords=["fiets", "batavus"],
            required_specs=["28 inch"],
            required_brands=["Batavus"],
            excluded_brands=[],
            max_budget=200.0,
            exclude_business=False,
            price_history=[180.0, 200.0, 190.0],
        )
        assert 0 <= result.relevance_score <= 100
        assert 0 <= result.deal_score <= 100
        assert 0 <= result.quality_score <= 100
        assert result.seller_type in ("private", "business", "unknown")
        assert result.relevance_reason
        assert result.deal_reason
        assert result.quality_reason
