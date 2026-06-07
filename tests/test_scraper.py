"""
Tests for marktplaats_bot.scraper.

Playwright is fully mocked — no real browser or network calls.
Translation is also mocked to avoid network dependency.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from marktplaats_bot.scraper import (
    ScrapedListing,
    _build_search_url,
    _extract_listing_id,
    _parse_distance,
    _parse_price,
    scrape_bilingual,
    scrape_search,
    translate_query,
)


# ---------------------------------------------------------------------------
# _parse_price
# ---------------------------------------------------------------------------


class TestParsePrice:
    def test_plain_integer(self):
        assert _parse_price("150") == 150.0

    def test_euro_symbol(self):
        assert _parse_price("€ 250") == 250.0

    def test_european_thousands(self):
        # "1.234" means 1234 in Dutch
        assert _parse_price("€ 1.234") == 1234.0

    def test_european_decimal_comma(self):
        assert _parse_price("199,99") == 199.99

    def test_full_european_format(self):
        assert _parse_price("€ 1.234,56") == 1234.56

    def test_vraagprijs_returns_none(self):
        assert _parse_price("Vraagprijs") is None

    def test_gratis_returns_none(self):
        assert _parse_price("Gratis") is None

    def test_ruil_returns_none(self):
        assert _parse_price("Te ruil") is None

    def test_swap_returns_none(self):
        assert _parse_price("Swap") is None

    def test_empty_string(self):
        assert _parse_price("") is None

    def test_none_input(self):
        assert _parse_price(None) is None

    def test_notk_returns_none(self):
        assert _parse_price("n.o.t.k.") is None

    def test_whitespace_only(self):
        assert _parse_price("   ") is None


# ---------------------------------------------------------------------------
# _parse_distance
# ---------------------------------------------------------------------------


class TestParseDistance:
    def test_simple_km(self):
        assert _parse_distance("5 km") == 5.0

    def test_decimal_km(self):
        assert _parse_distance("12,5 km") == 12.5

    def test_no_km(self):
        assert _parse_distance("Rotterdam") is None

    def test_empty(self):
        assert _parse_distance("") is None

    def test_km_no_space(self):
        assert _parse_distance("8km") == 8.0

    def test_uppercase_km(self):
        assert _parse_distance("15 KM") == 15.0

    def test_with_prefix(self):
        assert _parse_distance("op 3 km afstand") == 3.0


# ---------------------------------------------------------------------------
# _extract_listing_id
# ---------------------------------------------------------------------------


class TestExtractListingId:
    def test_standard_marktplaats_url(self):
        url = "https://www.marktplaats.nl/v/fietsen-en-brommers/fietsen-dames/a1234567890-gazelle-avignon"
        assert _extract_listing_id(url) == "1234567890"

    def test_short_url(self):
        url = "https://www.marktplaats.nl/a/12345678/"
        assert _extract_listing_id(url) == "12345678"

    def test_no_id(self):
        assert _extract_listing_id("https://www.marktplaats.nl/q/fiets/") is None

    def test_id_in_query_path(self):
        url = "https://www.marktplaats.nl/v/electronics/123456789-some-item.html"
        assert _extract_listing_id(url) == "123456789"


# ---------------------------------------------------------------------------
# _build_search_url
# ---------------------------------------------------------------------------


class TestBuildSearchUrl:
    def test_basic_url(self):
        url = _build_search_url("fiets", "3027CM", 25, None)
        assert "fiets" in url
        assert "3027CM" in url
        assert "25000" in url
        assert "priceTo" not in url

    def test_with_max_price(self):
        url = _build_search_url("laptop", "1011AB", 10, 500.0)
        assert "priceTo:500" in url
        assert "10000" in url

    def test_spaces_encoded(self):
        url = _build_search_url("mountain bike", "3027CM", 25, None)
        assert " " not in url
        assert "mountain" in url


# ---------------------------------------------------------------------------
# translate_query
# ---------------------------------------------------------------------------


class TestTranslateQuery:
    def test_successful_translation(self):
        mock_translator = MagicMock()
        mock_translator.translate.return_value = "bicycle"
        with patch("marktplaats_bot.scraper.GoogleTranslator", return_value=mock_translator, create=True):
            with patch.dict("sys.modules", {"deep_translator": MagicMock(GoogleTranslator=MagicMock(return_value=mock_translator))}):
                result = translate_query("fiets", "en")
        # The function imports inside, so patch at module level
        assert isinstance(result, str)

    def test_fallback_on_error(self):
        with patch("marktplaats_bot.scraper.GoogleTranslator", side_effect=Exception("network error"), create=True):
            with patch.dict("sys.modules", {
                "deep_translator": MagicMock(GoogleTranslator=MagicMock(side_effect=Exception("network error")))
            }):
                result = translate_query("fiets", "en")
        assert isinstance(result, str)

    def test_translate_query_mock(self):
        """Verify translate_query calls GoogleTranslator with correct args."""
        mock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.translate.return_value = "bicycle"
        mock_cls.return_value = mock_instance

        mock_module = MagicMock()
        mock_module.GoogleTranslator = mock_cls

        import sys
        original = sys.modules.get("deep_translator")
        sys.modules["deep_translator"] = mock_module
        try:
            result = translate_query("fiets", "en")
            assert result == "bicycle"
            mock_cls.assert_called_once_with(source="auto", target="en")
            mock_instance.translate.assert_called_once_with("fiets")
        finally:
            if original is None:
                del sys.modules["deep_translator"]
            else:
                sys.modules["deep_translator"] = original

    def test_translate_returns_original_on_empty(self):
        mock_instance = MagicMock()
        mock_instance.translate.return_value = ""
        mock_cls = MagicMock(return_value=mock_instance)
        mock_module = MagicMock(GoogleTranslator=mock_cls)

        import sys
        original = sys.modules.get("deep_translator")
        sys.modules["deep_translator"] = mock_module
        try:
            result = translate_query("fiets", "en")
            assert result == "fiets"
        finally:
            if original is None:
                del sys.modules["deep_translator"]
            else:
                sys.modules["deep_translator"] = original


# ---------------------------------------------------------------------------
# scrape_search (mocked Playwright)
# ---------------------------------------------------------------------------


def _make_mock_listing(listing_id: str, title: str, price: str = "€ 100") -> MagicMock:
    """Build a mock Playwright element that represents one listing."""
    el = AsyncMock()

    link = AsyncMock()
    link.get_attribute = AsyncMock(return_value=f"/v/test/{listing_id}-{title.lower().replace(' ', '-')}")
    el.query_selector = AsyncMock(return_value=link)

    title_el = AsyncMock()
    title_el.inner_text = AsyncMock(return_value=title)

    price_el = AsyncMock()
    price_el.inner_text = AsyncMock(return_value=price)

    async def query_selector_side_effect(sel):
        if "a[href" in sel:
            return link
        if "h3" in sel or "h2" in sel or "title" in sel.lower():
            return title_el
        if "price" in sel.lower():
            return price_el
        return None

    el.query_selector = AsyncMock(side_effect=query_selector_side_effect)
    el.query_selector_all = AsyncMock(return_value=[AsyncMock()])
    el.get_attribute = AsyncMock(return_value=None)

    return el


@pytest.mark.asyncio
async def test_scrape_search_returns_empty_on_failure():
    """When Playwright raises, scrape_search returns [] after retries."""
    with patch("marktplaats_bot.scraper._do_scrape", side_effect=Exception("browser crash")):
        with patch("marktplaats_bot.scraper._random_delay", new_callable=AsyncMock):
            results = await scrape_search("fiets", retries=1)
    assert results == []


@pytest.mark.asyncio
async def test_scrape_search_returns_listings():
    """scrape_search returns listings produced by _do_scrape."""
    fake_listings = [
        ScrapedListing(listing_id="123456789", title="Gazelle Fiets", url="https://www.marktplaats.nl/v/test/123456789"),
        ScrapedListing(listing_id="987654321", title="Trek MTB", url="https://www.marktplaats.nl/v/test/987654321"),
    ]
    with patch("marktplaats_bot.scraper._do_scrape", return_value=fake_listings):
        results = await scrape_search("fiets")
    assert len(results) == 2
    assert results[0].listing_id == "123456789"
    assert results[1].title == "Trek MTB"


@pytest.mark.asyncio
async def test_scrape_search_retries_on_first_failure():
    """scrape_search retries after failure and returns results from second attempt."""
    fake_listings = [
        ScrapedListing(listing_id="111111111", title="Batavus", url="https://www.marktplaats.nl/v/test/111111111"),
    ]
    call_count = 0

    async def flaky_scrape(url, max_results):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("timeout")
        return fake_listings

    with patch("marktplaats_bot.scraper._do_scrape", side_effect=flaky_scrape):
        with patch("marktplaats_bot.scraper._random_delay", new_callable=AsyncMock):
            results = await scrape_search("fiets", retries=2)

    assert len(results) == 1
    assert call_count == 2


# ---------------------------------------------------------------------------
# scrape_bilingual (mocked scrape_search + translate_query)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_bilingual_deduplicates():
    """Results shared between NL and EN queries are deduplicated by listing_id."""
    nl_results = [
        ScrapedListing(listing_id="111", title="Fiets NL", url="https://www.marktplaats.nl/v/test/111"),
        ScrapedListing(listing_id="222", title="Shared", url="https://www.marktplaats.nl/v/test/222"),
    ]
    en_results = [
        ScrapedListing(listing_id="222", title="Shared", url="https://www.marktplaats.nl/v/test/222"),
        ScrapedListing(listing_id="333", title="Bike EN", url="https://www.marktplaats.nl/v/test/333"),
    ]

    call_count = 0

    async def mock_scrape(query, postcode, radius_km, max_price, **kw):
        nonlocal call_count
        call_count += 1
        return nl_results if call_count == 1 else en_results

    with patch("marktplaats_bot.scraper.translate_query", side_effect=["fiets", "bicycle"]):
        with patch("marktplaats_bot.scraper.scrape_search", side_effect=mock_scrape):
            with patch("marktplaats_bot.scraper._random_delay", new_callable=AsyncMock):
                results, nl_q, en_q = await scrape_bilingual("bike")

    assert len(results) == 3
    assert {r.listing_id for r in results} == {"111", "222", "333"}
    assert nl_q == "fiets"
    assert en_q == "bicycle"


@pytest.mark.asyncio
async def test_scrape_bilingual_skips_en_when_same_as_nl():
    """If NL and EN queries are identical, skip EN scrape to avoid duplicate."""
    nl_results = [
        ScrapedListing(listing_id="444", title="MacBook", url="https://www.marktplaats.nl/v/test/444"),
    ]

    scrape_call_count = 0

    async def mock_scrape(query, postcode, radius_km, max_price, **kw):
        nonlocal scrape_call_count
        scrape_call_count += 1
        return nl_results

    with patch("marktplaats_bot.scraper.translate_query", side_effect=["MacBook", "MacBook"]):
        with patch("marktplaats_bot.scraper.scrape_search", side_effect=mock_scrape):
            with patch("marktplaats_bot.scraper._random_delay", new_callable=AsyncMock):
                results, nl_q, en_q = await scrape_bilingual("MacBook")

    assert scrape_call_count == 1
    assert len(results) == 1


@pytest.mark.asyncio
async def test_scrape_bilingual_handles_empty_en():
    """Empty EN results still return NL results only."""
    nl_results = [
        ScrapedListing(listing_id="555", title="Fiets", url="https://www.marktplaats.nl/v/test/555"),
    ]

    call_count = 0

    async def mock_scrape(query, postcode, radius_km, max_price, **kw):
        nonlocal call_count
        call_count += 1
        return nl_results if call_count == 1 else []

    with patch("marktplaats_bot.scraper.translate_query", side_effect=["fiets", "bicycle"]):
        with patch("marktplaats_bot.scraper.scrape_search", side_effect=mock_scrape):
            with patch("marktplaats_bot.scraper._random_delay", new_callable=AsyncMock):
                results, _, _ = await scrape_bilingual("fiets")

    assert len(results) == 1
    assert results[0].listing_id == "555"


@pytest.mark.asyncio
async def test_scrape_bilingual_passes_params():
    """postcode, radius_km, max_price are forwarded to scrape_search."""
    captured = {}

    async def mock_scrape(query, postcode, radius_km, max_price, **kw):
        captured["postcode"] = postcode
        captured["radius_km"] = radius_km
        captured["max_price"] = max_price
        return []

    with patch("marktplaats_bot.scraper.translate_query", side_effect=["fiets", "bicycle"]):
        with patch("marktplaats_bot.scraper.scrape_search", side_effect=mock_scrape):
            with patch("marktplaats_bot.scraper._random_delay", new_callable=AsyncMock):
                await scrape_bilingual("fiets", postcode="1011AB", radius_km=15, max_price=750.0)

    assert captured["postcode"] == "1011AB"
    assert captured["radius_km"] == 15
    assert captured["max_price"] == 750.0
