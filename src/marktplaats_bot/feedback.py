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
_MAX_AGE_RE = re.compile(
    r"(?:max(?:imum)?|niet ouder dan|not older than|younger than)\s+(\d+)\s+(?:years?|jaar old|jaar)",
    re.IGNORECASE,
)

# Spec keywords
_SPEC_RE = re.compile(
    r"(?:must have|needs?|require[sd]?|with|met|inclusief)\s+([A-Za-z0-9][\w\s,]+?)(?:\.|,|$)",
    re.IGNORECASE,
)

# "fixer-upper is fine" / "opknapper mag" → add_keywords
_FIXER_UPPER_RE = re.compile(
    r"\b(?:fixer[\s-]upper|opknapper|project\s+car|doe[\s-]het[\s-]zelf)\b",
    re.IGNORECASE,
)

# "looking for the car" / "hele auto" → add_keywords for complete unit
_WHOLE_UNIT_RE = re.compile(
    r"\b(?:looking\s+for\s+the\s+(?:car|bike|fiets|auto|item)|hele\s+auto|hele\s+fiets|complete\s+(?:car|bike|unit)|compleet\s+exemplaar)\b",
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
        remove_keywords: list[str]
        add_keywords: list[str]
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

    # --- Brand excludes and keyword removals ---
    # "no X" / "not X" / "geen X": if X is a generic topic noun → remove from
    # keyword strings; if X looks like a brand name → add to excluded_brands.
    remove_kws: list[str] = []
    add_kws: list[str] = []

    no_matches = _NO_BRAND_RE.findall(text)
    if no_matches:
        exclude_brands: list[str] = []
        for match in no_matches:
            cleaned = _clean_brand(match)
            if not cleaned:
                continue
            if _is_stop_word(cleaned):
                # Generic topic noun — strip from keyword strings
                remove_kws.append(cleaned.lower())
            else:
                exclude_brands.append(cleaned)
        if exclude_brands:
            changes["add_excluded_brands"] = exclude_brands

    # --- Query direction additions ---
    if _FIXER_UPPER_RE.search(lower):
        add_kws.extend(["opknapper", "fixer-upper"])

    if _WHOLE_UNIT_RE.search(lower):
        add_kws.extend(["heel", "compleet"])

    if remove_kws:
        changes["remove_keywords"] = list(dict.fromkeys(remove_kws))
    if add_kws:
        changes["add_keywords"] = list(dict.fromkeys(add_kws))

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
    """Return True for generic topic nouns that should never be added to excluded_brands."""
    generic_words = {
        # English generic topic nouns
        "parts", "items", "stuff", "things", "listings",
        "dealers", "businesses", "sellers",
        # Dutch equivalents
        "onderdelen", "spullen", "dingen", "artikelen",
        "verkoper", "verkopers", "bedrijven",
        # Adjective-like
        "more", "older", "newer", "cheaper", "expensive",
    }
    return text.lower().strip() in generic_words
