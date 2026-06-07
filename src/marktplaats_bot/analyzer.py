"""
Rule-based analyzer for marktplaats listings.

No external AI/LLM calls. All scoring is deterministic and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .scraper import ScrapedListing

# ---------------------------------------------------------------------------
# Business / private detection
# ---------------------------------------------------------------------------

_BUSINESS_KEYWORDS = [
    "kvk", "k.v.k.", "btw", "excl. btw", "incl. btw",
    "per maand", "webshop", "leverancier", "dealer", "groothandel",
    "handelaar", "zakelijk", "business",
]
_BUSINESS_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _BUSINESS_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_KVK_PATTERN = re.compile(r"\b\d{8}\b")  # 8-digit KvK number


def detect_seller_type(listing: ScrapedListing) -> str:
    """Return 'business', 'private', or 'unknown'."""
    # Honour explicit scraper-detected seller type when available
    if listing.seller_type in ("business", "private"):
        return listing.seller_type

    combined = f"{listing.title} {listing.description} {listing.seller_name}"
    if _BUSINESS_PATTERN.search(combined) or _KVK_PATTERN.search(combined):
        return "business"
    return "private"


# ---------------------------------------------------------------------------
# Relevance scorer (0–100)
# ---------------------------------------------------------------------------


def score_relevance(
    listing: ScrapedListing,
    query_keywords: list[str],
    required_specs: list[str],
    required_brands: list[str],
    excluded_brands: list[str],
    max_budget: Optional[float],
    exclude_business: bool,
) -> tuple[int, str]:
    """Return (score, reason) for relevance (0–100)."""
    score = 50  # baseline
    reasons: list[str] = []

    combined = f"{listing.title} {listing.description}".lower()

    # --- Keyword overlap ---
    if query_keywords:
        matched = sum(1 for kw in query_keywords if kw.lower() in combined)
        keyword_ratio = matched / len(query_keywords)
        kw_bonus = int(keyword_ratio * 30)
        score += kw_bonus
        if kw_bonus:
            reasons.append(f"+{kw_bonus} keywords({matched}/{len(query_keywords)})")

    # --- Required brands ---
    if required_brands:
        brand_hit = any(b.lower() in combined for b in required_brands)
        if brand_hit:
            score += 15
            reasons.append("+15 brand match")
        else:
            score -= 20
            reasons.append("-20 no required brand")

    # --- Excluded brands ---
    if excluded_brands:
        brand_excluded = any(b.lower() in combined for b in excluded_brands)
        if brand_excluded:
            score = 0
            reasons.append("excluded brand")
            return 0, "; ".join(reasons)

    # --- Required specs ---
    if required_specs:
        matched_specs = sum(1 for s in required_specs if s.lower() in combined)
        spec_ratio = matched_specs / len(required_specs)
        spec_bonus = int(spec_ratio * 20)
        score += spec_bonus
        if spec_bonus:
            reasons.append(f"+{spec_bonus} specs({matched_specs}/{len(required_specs)})")

    # --- Budget check ---
    if max_budget is not None and listing.price is not None:
        if listing.price > max_budget:
            score -= 30
            reasons.append(f"-30 over budget(€{listing.price:.0f}>€{max_budget:.0f})")
        elif listing.price <= max_budget * 0.7:
            score += 5
            reasons.append("+5 well under budget")

    # --- Business seller penalty ---
    if exclude_business and detect_seller_type(listing) == "business":
        score -= 40
        reasons.append("-40 business seller")

    score = max(0, min(100, score))
    return score, "; ".join(reasons) if reasons else "baseline"


# ---------------------------------------------------------------------------
# Deal scorer (0–100)
# ---------------------------------------------------------------------------


def score_deal(
    listing: ScrapedListing,
    max_budget: Optional[float],
    price_history: list[float],
) -> tuple[int, str]:
    """Return (score, reason) for deal quality (0–100).

    Uses price history if available; otherwise falls back to budget heuristic.
    """
    if listing.price is None:
        return 50, "no price"

    price = listing.price

    # --- Against price history (running median) ---
    if price_history and len(price_history) >= 3:
        sorted_prices = sorted(price_history)
        median = sorted_prices[len(sorted_prices) // 2]
        if median > 0:
            ratio = price / median
            if ratio < 0.5:
                return 90, f"far below median(€{median:.0f})"
            elif ratio < 0.75:
                return 75, f"well below median(€{median:.0f})"
            elif ratio < 0.9:
                return 65, f"below median(€{median:.0f})"
            elif ratio < 1.1:
                return 50, f"near median(€{median:.0f})"
            elif ratio < 1.3:
                return 35, f"above median(€{median:.0f})"
            else:
                return 15, f"well above median(€{median:.0f})"

    # --- Budget heuristic ---
    if max_budget and max_budget > 0:
        ratio = price / max_budget
        if ratio < 0.4:
            return 85, f"<40% of budget(€{max_budget:.0f})"
        elif ratio < 0.6:
            return 70, f"<60% of budget"
        elif ratio < 0.8:
            return 55, f"<80% of budget"
        elif ratio <= 1.0:
            return 40, f"within budget"
        else:
            return 10, f"over budget"

    # No reference price — moderate default
    return 50, "no reference price"


# ---------------------------------------------------------------------------
# Listing quality scorer (0–100)
# ---------------------------------------------------------------------------


def score_quality(listing: ScrapedListing) -> tuple[int, str]:
    """Return (score, reason) for listing quality (0–100)."""
    score = 0
    reasons: list[str] = []

    # Photos: ≥3 = good
    if listing.photo_count >= 5:
        score += 40
        reasons.append(f"+40 photos({listing.photo_count})")
    elif listing.photo_count >= 3:
        score += 30
        reasons.append(f"+30 photos({listing.photo_count})")
    elif listing.photo_count >= 1:
        score += 15
        reasons.append(f"+15 photos({listing.photo_count})")
    else:
        reasons.append("no photos")

    # Description length: ≥100 chars = good
    desc_len = len(listing.description or "")
    if desc_len >= 300:
        score += 40
        reasons.append(f"+40 desc({desc_len}ch)")
    elif desc_len >= 100:
        score += 30
        reasons.append(f"+30 desc({desc_len}ch)")
    elif desc_len >= 30:
        score += 15
        reasons.append(f"+15 desc({desc_len}ch)")
    else:
        reasons.append(f"short desc({desc_len}ch)")

    # Has a price listed (not "bieden"/negotiable)
    if listing.price is not None:
        score += 20
        reasons.append("+20 price listed")

    score = max(0, min(100, score))
    return score, "; ".join(reasons) if reasons else "no data"


# ---------------------------------------------------------------------------
# Combined analyse function
# ---------------------------------------------------------------------------


@dataclass
class AnalysisResult:
    seller_type: str
    relevance_score: int
    relevance_reason: str
    deal_score: int
    deal_reason: str
    quality_score: int
    quality_reason: str


def analyse(
    listing: ScrapedListing,
    *,
    query_keywords: list[str],
    required_specs: list[str],
    required_brands: list[str],
    excluded_brands: list[str],
    max_budget: Optional[float],
    exclude_business: bool,
    price_history: list[float],
) -> AnalysisResult:
    """Run all three scorers and return a combined AnalysisResult."""
    seller_type = detect_seller_type(listing)

    # Override listing seller_type for scoring
    listing_with_type = ScrapedListing(
        listing_id=listing.listing_id,
        title=listing.title,
        url=listing.url,
        price=listing.price,
        distance_km=listing.distance_km,
        posted_at=listing.posted_at,
        photo_count=listing.photo_count,
        description=listing.description,
        seller_type=seller_type,
        seller_name=listing.seller_name,
    )

    relevance, relevance_reason = score_relevance(
        listing_with_type,
        query_keywords=query_keywords,
        required_specs=required_specs,
        required_brands=required_brands,
        excluded_brands=excluded_brands,
        max_budget=max_budget,
        exclude_business=exclude_business,
    )
    deal, deal_reason = score_deal(listing_with_type, max_budget, price_history)
    quality, quality_reason = score_quality(listing_with_type)

    return AnalysisResult(
        seller_type=seller_type,
        relevance_score=relevance,
        relevance_reason=relevance_reason,
        deal_score=deal,
        deal_reason=deal_reason,
        quality_score=quality,
        quality_reason=quality_reason,
    )
