"""
Playwright scraper for marktplaats.nl.

Rate-limited with 1–3 s random delays. Bilingual wrapper deduplicates by listing_id.
No external AI/LLM calls — rule-based only.
"""

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

BASE_URL = "https://www.marktplaats.nl"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Marktplaats listing IDs are 6+ digits, optionally preceded by a single letter (a/m/etc.)
_LISTING_ID_RE = re.compile(r"/[a-z]?(\d{6,})(?:[/-]|$)")
_PRICE_RE = re.compile(r"(\d[\d.,]*)")
_DISTANCE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*km", re.IGNORECASE)


@dataclass
class ScrapedListing:
    listing_id: str
    title: str
    url: str
    price: Optional[float] = None
    distance_km: Optional[float] = None
    posted_at: Optional[datetime] = None
    photo_count: int = 0
    description: str = ""
    seller_type: str = "unknown"
    seller_name: str = ""
    is_bidding: bool = False
    image_urls: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_search_url(
    query: str,
    postcode: str,
    radius_km: int,
    max_price: Optional[float],
) -> str:
    encoded = quote_plus(query)
    radius_m = radius_km * 1000
    url = f"{BASE_URL}/q/{encoded}/#postcode:{postcode}|distanceMeters:{radius_m}"
    if max_price is not None:
        url += f"|priceTo:{int(max_price)}"
    return url


def _is_bidding_price(text: str) -> bool:
    if not text:
        return False
    lower = text.lower().strip()
    return "bieden" in lower or "bod" in lower


def _parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    lower = text.lower().strip()
    if any(k in lower for k in ["te ruil", "vraagprijs", "n.o.t.k.", "gratis", "free", "swap", "bieden"]):
        return None
    # Strip currency symbols and whitespace
    clean = re.sub(r"[€$£\s]", "", lower)
    match = _PRICE_RE.search(clean)
    if not match:
        return None
    raw = match.group(1)
    # Full European format: "1.234,56" (dot=thousands, comma=decimal)
    if re.match(r"^\d{1,3}(\.\d{3})+,\d{1,2}$", raw):
        return float(raw.replace(".", "").replace(",", "."))
    # Pure European thousands: "1.234" or "1.234.567"
    if re.match(r"^\d{1,3}(\.\d{3})+$", raw):
        return float(raw.replace(".", ""))
    # Decimal comma only: "199,99"
    if "," in raw and "." not in raw:
        return float(raw.replace(",", "."))
    # Plain integer or dot-decimal: "150" or "1.5"
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_distance(text: str) -> Optional[float]:
    if not text:
        return None
    match = _DISTANCE_RE.search(text)
    if match:
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def _extract_listing_id(url: str) -> Optional[str]:
    match = _LISTING_ID_RE.search(url)
    return match.group(1) if match else None


async def _random_delay(low: float = 1.0, high: float = 3.0) -> None:
    await asyncio.sleep(random.uniform(low, high))


# ---------------------------------------------------------------------------
# Playwright scrape
# ---------------------------------------------------------------------------


async def scrape_search(
    query: str,
    postcode: str = "3027CM",
    radius_km: int = 25,
    max_price: Optional[float] = None,
    max_results: int = 30,
    retries: int = 2,
) -> list[ScrapedListing]:
    """Fetch marktplaats.nl results for *query* and return scraped listings."""
    url = _build_search_url(query, postcode, radius_km, max_price)
    for attempt in range(retries + 1):
        try:
            return await _do_scrape(url, max_results)
        except Exception as exc:
            logger.warning("Scrape attempt %d/%d failed for '%s': %s", attempt + 1, retries + 1, query, exc)
            if attempt < retries:
                await _random_delay()
    logger.error("All %d scrape attempts failed for query: %s", retries + 1, query)
    return []


async def _do_scrape(url: str, max_results: int) -> list[ScrapedListing]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-zygote",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="nl-NL",
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await _random_delay(0.5, 1.5)

            # Dismiss cookie consent if present
            for btn_sel in [
                "button[id*='accept']",
                "button[data-testid*='accept-all']",
                "button[class*='accept']",
                "#didomi-notice-agree-button",
            ]:
                try:
                    await page.click(btn_sel, timeout=2000)
                    break
                except Exception:
                    pass

            await _random_delay(0.5, 1.5)
            return await _extract_listings(page, max_results)
        finally:
            await context.close()
            await browser.close()


async def _extract_listings(page, max_results: int) -> list[ScrapedListing]:
    results: list[ScrapedListing] = []

    # Try selectors from most specific to most generic
    for selector in [
        "article[data-collectable-id]",
        "article.hz-Listing",
        "li[class*='Listing']",
        "article",
    ]:
        elements = await page.query_selector_all(selector)
        if elements:
            logger.debug("Using selector '%s', found %d elements", selector, len(elements))
            for el in elements[:max_results]:
                try:
                    listing = await _extract_single_listing(el)
                    if listing:
                        results.append(listing)
                except Exception as exc:
                    logger.debug("Skipping element: %s", exc)
            break

    if not results:
        logger.warning("No listings extracted from page: %s", page.url)
    return results


async def _extract_single_listing(el) -> Optional[ScrapedListing]:
    # --- URL & ID ---
    link = None
    for link_sel in ["a[href*='/a/']", "a[href*='/v/']", "a[href]"]:
        link = await el.query_selector(link_sel)
        if link:
            break
    if not link:
        return None

    href = await link.get_attribute("href") or ""
    if not href:
        return None

    url = href if href.startswith("http") else f"{BASE_URL}{href}"
    listing_id = _extract_listing_id(url)
    if not listing_id:
        listing_id = (
            await el.get_attribute("data-collectable-id")
            or await el.get_attribute("data-item-id")
        )
    if not listing_id:
        return None

    # --- Title ---
    # inner_text() on card elements returns full card text; take first non-empty line only
    title = ""
    for title_sel in ["h3", "h2", "[class*='title']", "[class*='Title']"]:
        title_el = await el.query_selector(title_sel)
        if title_el:
            raw = (await title_el.inner_text()).strip()
            title = next((ln.strip() for ln in raw.splitlines() if ln.strip()), "")
            if title:
                break
    if not title:
        return None

    # --- Price ---
    price: Optional[float] = None
    is_bidding = False
    for price_sel in ["[class*='price']", "[class*='Price']", "[data-testid*='price']"]:
        price_el = await el.query_selector(price_sel)
        if price_el:
            raw_price_text = await price_el.inner_text()
            is_bidding = _is_bidding_price(raw_price_text)
            price = _parse_price(raw_price_text)
            break

    # --- Distance ---
    distance_km: Optional[float] = None
    for dist_sel in ["[class*='distance']", "[class*='Distance']", "[class*='location']", "[class*='Location']"]:
        dist_el = await el.query_selector(dist_sel)
        if dist_el:
            distance_km = _parse_distance(await dist_el.inner_text())
            if distance_km is not None:
                break

    # --- Photos ---
    imgs = await el.query_selector_all("img")
    photo_count = 0
    image_urls: list[str] = []
    for img in imgs:
        src = await img.get_attribute("src") or await img.get_attribute("data-src") or ""
        src = src.strip()
        if src and src.startswith("http") and not src.endswith(".svg"):
            image_urls.append(src)
    # Deduplicate while preserving order
    seen_srcs: set[str] = set()
    unique_images: list[str] = []
    for src in image_urls:
        if src not in seen_srcs:
            seen_srcs.add(src)
            unique_images.append(src)
    image_urls = unique_images[:5]
    photo_count = len(image_urls)

    # --- Seller type (coarse; detailed analysis in task-009) ---
    seller_type = "unknown"
    seller_name = ""
    for seller_sel in ["[class*='seller']", "[class*='Seller']", "[class*='merchant']"]:
        seller_el = await el.query_selector(seller_sel)
        if seller_el:
            seller_text = (await seller_el.inner_text()).strip()
            lower = seller_text.lower()
            if any(k in lower for k in ["particulier", "private"]):
                seller_type = "private"
            elif any(k in lower for k in ["zakelijk", "business", "dealer", "handelaar"]):
                seller_type = "business"
            seller_name = seller_text
            break

    # --- Description snippet ---
    description = ""
    for desc_sel in ["[class*='description']", "[class*='Description']", "p"]:
        desc_el = await el.query_selector(desc_sel)
        if desc_el:
            desc_raw = (await desc_el.inner_text()).strip()
            # Strip repeated title prefix (inner_text often includes title in description element)
            if desc_raw.startswith(title):
                desc_raw = desc_raw[len(title):].strip()
            description = desc_raw
            if description:
                break

    return ScrapedListing(
        listing_id=listing_id,
        title=title,
        url=url,
        price=price,
        distance_km=distance_km,
        posted_at=None,
        photo_count=photo_count,
        description=description,
        seller_type=seller_type,
        seller_name=seller_name,
        is_bidding=is_bidding,
        image_urls=image_urls,
    )


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------


def translate_query(query: str, target_lang: str) -> str:
    """
    Translate *query* to *target_lang* using deep-translator (GoogleTranslator).
    Falls back to the original query on any error.
    """
    try:
        from deep_translator import GoogleTranslator

        result = GoogleTranslator(source="auto", target=target_lang).translate(query)
        return result if result else query
    except Exception as exc:
        logger.warning("Translation failed ('%s' → %s): %s", query, target_lang, exc)
        return query


# ---------------------------------------------------------------------------
# Bilingual wrapper
# ---------------------------------------------------------------------------


async def scrape_bilingual(
    query: str,
    postcode: str = "3027CM",
    radius_km: int = 25,
    max_price: Optional[float] = None,
    en_query_override: Optional[str] = None,
) -> tuple[list[ScrapedListing], str, str]:
    """
    Translate *query* to both NL and EN, scrape both, deduplicate by listing_id.

    When en_query_override is provided (AI-enhanced), use it directly instead of
    auto-translating. Returns ``(unique_listings, nl_query, en_query)``.
    """
    nl_query = translate_query(query, "nl")
    en_query = en_query_override if en_query_override else translate_query(query, "en")

    logger.info("Bilingual scrape — NL: '%s'  EN: '%s'", nl_query, en_query)

    nl_results = await scrape_search(nl_query, postcode, radius_km, max_price)
    await _random_delay()

    en_results: list[ScrapedListing] = []
    if en_query.lower().strip() != nl_query.lower().strip():
        en_results = await scrape_search(en_query, postcode, radius_km, max_price)

    seen: set[str] = set()
    combined: list[ScrapedListing] = []
    for listing in nl_results + en_results:
        if listing.listing_id not in seen:
            seen.add(listing.listing_id)
            combined.append(listing)

    logger.info(
        "Bilingual scrape done: %d NL + %d EN → %d unique",
        len(nl_results),
        len(en_results),
        len(combined),
    )
    return combined, nl_query, en_query
