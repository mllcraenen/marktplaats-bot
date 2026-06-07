"""
Full rule-based feedback parser (task-010).

Parses NL and EN natural language feedback into structured config changes.
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Budget / max price
_BUDGET_RE = re.compile(
    r"(?:budget|max(?:imum)?|niet meer dan|under|onder|less than|goedkoper dan|tot)\s*[€$]?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

# Radius / distance
_RADIUS_RE = re.compile(
    r"(?:within|binnen|radius|afstand|straal|closer|dichterbij)\s*(\d+)\s*km",
    re.IGNORECASE,
)
_RADIUS_INCREASE_RE = re.compile(
    r"(?:vergroot|vergroten|increase|expand|broaden).*?(?:radius|afstand|straal).*?(\d+)\s*km",
    re.IGNORECASE,
)

# Brand patterns: "only <brand>", "alleen <brand>", "no <brand>", "geen <brand>"
_ONLY_BRAND_RE = re.compile(
    r"(?:only|alleen|liefst|prefer(?:ably)?|want)\s+(?:a\s+)?([A-Za-z][\w\s-]{1,30}?)(?:\s+(?:brand|merk|fiets|auto|bike|car)|\b)",
    re.IGNORECASE,
)
_NO_BRAND_RE = re.compile(
    r"(?:no|geen|not|exclude|niet|without|zonder)\s+(?:any\s+)?([A-Za-z][\w\s-]{1,30}?)(?:\s+(?:brand|merk|fiets|auto|bike|car)|\b)",
    re.IGNORECASE,
)

# Age / year
_AGE_RE = re.compile(
    r"(?:not older than|maximaal|max(?:imum)?\s+(\d+)\s+(?:years?|jaar)|no older than\s+(\d+))",
    re.IGNORECASE,
)
_MAX_AGE_RE = re.compile(
    r"(?:max(?:imum)?|niet ouder dan|not older than|younger than)\s+(\d+)\s+(?:years?|jaar old|jaar)",
    re.IGNORECASE,
)

# Spec keywords
_SPEC_RE = re.compile(
    r"(?:must have|needs?|require[sd]?|with|met|inclusief)\s+([A-Za-z0-9][\w\s,]+?)(?:\.|,|$)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


def parse_feedback(text: str) -> dict:
    """
    Parse free-text feedback (NL or EN) into a dict of config changes.

    Supported keys in returned dict:
        max_budget: float
        radius_km: int
        max_age_years: int
        exclude_business: bool
        relevance_threshold: int
        add_required_brands: list[str]
        add_excluded_brands: list[str]
        add_required_specs: list[str]
    """
    changes: dict = {}
    lower = text.lower()

    # --- Budget ---
    m = _BUDGET_RE.search(lower)
    if m:
        changes["max_budget"] = float(m.group(1).replace(",", "."))

    # --- Radius ---
    m = _RADIUS_RE.search(lower)
    if m:
        changes["radius_km"] = int(m.group(1))
    else:
        m = _RADIUS_INCREASE_RE.search(lower)
        if m:
            changes["radius_km"] = int(m.group(1))

    # --- Max age ---
    m = _MAX_AGE_RE.search(lower)
    if m:
        changes["max_age_years"] = int(m.group(1))

    # --- Business exclusion ---
    business_phrases = [
        "te veel bedrijf", "too many business", "exclude business",
        "geen bedrijven", "only private", "alleen particulier",
        "no dealers", "geen dealers", "private only", "particulieren",
        "only private sellers", "no business",
    ]
    if any(p in lower for p in business_phrases):
        changes["exclude_business"] = True

    # --- Relevance threshold adjustment ---
    lower_threshold_phrases = [
        "not relevant", "niet relevant", "lower threshold",
        "lagere drempel", "too strict", "te streng", "fewer results",
        "minder resultaten", "more results", "meer resultaten",
    ]
    if any(p in lower for p in lower_threshold_phrases):
        current = changes.get("relevance_threshold", 60)
        changes["relevance_threshold"] = max(0, current - 10)

    higher_threshold_phrases = [
        "too many results", "te veel resultaten", "irrelevant",
        "raise threshold", "hogere drempel",
    ]
    if any(p in lower for p in higher_threshold_phrases):
        current = changes.get("relevance_threshold", 60)
        changes["relevance_threshold"] = min(100, current + 10)

    # --- Brand includes ---
    only_matches = _ONLY_BRAND_RE.findall(text)
    if only_matches:
        cleaned = [_clean_brand(b) for b in only_matches]
        cleaned = [b for b in cleaned if b]
        if cleaned:
            changes["add_required_brands"] = cleaned

    # --- Brand excludes ---
    no_matches = _NO_BRAND_RE.findall(text)
    if no_matches:
        cleaned = [_clean_brand(b) for b in no_matches]
        cleaned = [b for b in cleaned if b and not _is_stop_word(b)]
        if cleaned:
            changes["add_excluded_brands"] = cleaned

    # --- Required specs ---
    spec_matches = _SPEC_RE.findall(text)
    if spec_matches:
        specs = [s.strip() for s in spec_matches if len(s.strip()) > 2]
        if specs:
            changes["add_required_specs"] = specs

    return changes


def _clean_brand(text: str) -> str:
    """Strip filler words and normalise a brand fragment."""
    text = text.strip()
    stopwords = {
        "a", "an", "the", "de", "het", "een", "any", "all",
        "brand", "merk", "from", "van", "that", "this", "those",
        "bike", "auto", "car", "fiets",
    }
    words = text.split()
    words = [w for w in words if w.lower() not in stopwords]
    result = " ".join(words).strip(" -,.")
    return result if len(result) > 1 else ""


def _is_stop_word(text: str) -> bool:
    generic_words = {
        "dealers", "dealers", "businesses", "sellers", "verkoper",
        "more", "older", "newer", "cheaper", "expensive",
    }
    return text.lower() in generic_words
