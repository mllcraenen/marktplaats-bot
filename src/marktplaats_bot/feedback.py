"""
Feedback parser — converts free-text NL/EN feedback to structured search changes.

Design principles:
- Every match is checked for negation context before routing positive vs negative.
- "don't want X", "no X", "geen X", "without X" all route to exclusions.
- "want X" / "only X" / "prefer X" only route to inclusions when NOT negated.
- "with X" as a spec indicator is rejected inside a negative clause.
- Trailing filler ("at all", "anymore", "ever", "please") is stripped.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FILLER_SUFFIX_RE = re.compile(
    r"\s*\b(?:at\s+all|anymore|ever|really|please|right\s*now|too|though|tbh)\b.*$",
    re.IGNORECASE,
)

_NEGATION_WORDS = (
    "don't", "dont", "do not", "can't", "cant", "cannot",
    "not ", "never ", "geen ", "niet ", "no ", "without ", "zonder ",
)


def _strip_filler(text: str) -> str:
    return _FILLER_SUFFIX_RE.sub("", text).strip(" -,.")


def _has_negation_before(text: str, match_start: int, window: int = 40) -> bool:
    """True if a negation word appears within `window` chars before match_start."""
    prefix = text[max(0, match_start - window):match_start].lower()
    return any(neg in prefix for neg in _NEGATION_WORDS)


def _in_negative_clause(text: str, match_start: int) -> bool:
    """
    True if match_start sits inside a negative clause.
    A negative clause begins at the start of the sentence (or after [,;.]) and
    contains a negation word before the current position.
    """
    # Find the start of the current clause (after last sentence/clause boundary)
    clause_start = max(
        text.rfind(".", 0, match_start),
        text.rfind(",", 0, match_start),
        text.rfind(";", 0, match_start),
        0,
    )
    clause = text[clause_start:match_start].lower()
    return any(neg.strip() in clause for neg in _NEGATION_WORDS)


def _clean_subject(text: str) -> str:
    """Strip stop words and trailing filler from an extracted subject."""
    text = _strip_filler(text)
    stop = {
        "a", "an", "the", "de", "het", "een", "any", "all", "more",
        "brand", "merk", "from", "van", "that", "this", "those",
        "bike", "auto", "car", "fiets",
    }
    words = [w for w in text.split() if w.lower() not in stop]
    result = " ".join(words).strip(" -,.")
    return result if len(result) > 1 else ""


# Keep _clean_brand as an alias — existing callers in tests use it via _is_stop_word
_clean_brand = _clean_subject


def _is_stop_word(text: str) -> bool:
    """True for generic topic nouns that should go to remove_keywords, not excluded_brands."""
    generic = {
        # English
        "parts", "items", "stuff", "things", "listings", "results",
        "dealers", "businesses", "sellers", "motors", "motor",
        # Dutch
        "onderdelen", "spullen", "dingen", "artikelen",
        "verkoper", "verkopers", "bedrijven",
        # Adjective-like / qualifiers
        "more", "older", "newer", "cheaper", "expensive",
        "electric", "elektrisch",
        # Common tech-feature words that should filter from keywords, not brand
        "rgb", "led", "wireless", "bluetooth", "wifi",
    }
    return text.lower().strip() in generic


# ---------------------------------------------------------------------------
# Numeric / structural patterns (negation-safe — context is unambiguous)
# ---------------------------------------------------------------------------

_BUDGET_RE = re.compile(
    r"(?:budget|max(?:imum)?|niet meer dan|under|onder|less than|goedkoper dan|tot)\s*[€$]?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_RADIUS_RE = re.compile(
    r"(?:within|binnen|radius|afstand|straal|closer|dichterbij)\s*(\d+)\s*km",
    re.IGNORECASE,
)
_RADIUS_INCREASE_RE = re.compile(
    r"(?:vergroot|vergroten|increase|expand|broaden).*?(?:radius|afstand|straal).*?(\d+)\s*km",
    re.IGNORECASE,
)
_MAX_AGE_RE = re.compile(
    r"(?:max(?:imum)?|niet ouder dan|not older than|younger than)\s+(\d+)\s+(?:years?|jaar old|jaar)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Negation-aware subject patterns
# ---------------------------------------------------------------------------

# Explicit negative intents — these are always negative regardless of context
_EXPLICIT_NEG_RE = re.compile(
    r"(?:"
    r"don'?t\s+(?:want|like|need|have)\s+"
    r"|do\s+not\s+(?:want|like|need)\s+"
    r"|wil\s+(?:geen|niet)\s+"
    r"|liever\s+geen\s+"
    r"|not\s+looking\s+for\s+"
    r"|avoid\s+"
    r")"
    r"(?:any\s+|more\s+)?([A-Za-z0-9][\w\s-]{1,40})",
    re.IGNORECASE,
)

# "no X" / "geen X" / "without X" / "zonder X" / "not X" — check clause-level negation
_NO_SUBJ_RE = re.compile(
    r"(?:no|geen|without|zonder|not)\s+(?:any\s+|more\s+)?([A-Za-z0-9][\w\s-]{1,40})",
    re.IGNORECASE,
)

# Positive: "only X" / "alleen X" / "prefer X" / "liefst X"
# (These rarely appear negated; guard anyway)
_ONLY_RE = re.compile(
    r"(?:only|alleen|liefst|preferably)\s+(?:a\s+)?([A-Za-z][\w\s-]{1,30})",
    re.IGNORECASE,
)

# "want X" / "need X" — positive ONLY when not negated
_WANT_RE = re.compile(
    r"\b(?:want|need|zoek|looking\s+for)\s+(?:a\s+|an\s+)?([A-Za-z][\w\s-]{1,30})",
    re.IGNORECASE,
)

# Required specs — only "must have", "requires", "needs" (not bare "with")
# "with" is too ambiguous; "met" only when clearly used as "with [feature]"
_SPEC_STRONG_RE = re.compile(
    r"(?:must\s+have|needs?\s+to\s+have|requires?|inclusief)\s+([A-Za-z0-9][\w\s,]{2,40}?)(?:\.|,|$)",
    re.IGNORECASE,
)

# Fixer-upper / whole-unit shortcuts
_FIXER_UPPER_RE = re.compile(
    r"\b(?:fixer[\s-]upper|opknapper|project\s+car|doe[\s-]het[\s-]zelf)\b",
    re.IGNORECASE,
)
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

    Returned keys:
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
    if not text:
        return {}

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

    # --- Relevance threshold ---
    lower_threshold_phrases = [
        "not relevant", "niet relevant", "lower threshold",
        "lagere drempel", "too strict", "te streng",
        "fewer results", "minder resultaten", "more results", "meer resultaten",
    ]
    if any(p in lower for p in lower_threshold_phrases):
        changes["relevance_threshold"] = max(0, changes.get("relevance_threshold", 60) - 10)

    higher_threshold_phrases = [
        "too many results", "te veel resultaten", "irrelevant",
        "raise threshold", "hogere drempel",
    ]
    if any(p in lower for p in higher_threshold_phrases):
        changes["relevance_threshold"] = min(100, changes.get("relevance_threshold", 60) + 10)

    # --- Explicit negative subjects ("don't want X", "wil geen X", "avoid X") ---
    # These always produce exclusions, never inclusions.
    remove_kws: list[str] = []
    exclude_brands: list[str] = []

    for m in _EXPLICIT_NEG_RE.finditer(text):
        subj = _clean_subject(m.group(1))
        if not subj:
            continue
        if _is_stop_word(subj):
            remove_kws.append(subj.lower())
        else:
            # Treat as a remove-keyword (conservative: many user-reported "don't want X"
            # are features/specs, not brand names)
            remove_kws.append(subj.lower())

    # --- "no X" / "geen X" / "without X" / "not X" ---
    for m in _NO_SUBJ_RE.finditer(text):
        subj = _clean_subject(m.group(1))
        if not subj:
            continue
        if _is_stop_word(subj):
            remove_kws.append(subj.lower())
        else:
            # Only treat as a brand exclusion if it looks like a proper name
            # (starts with uppercase or is a well-known category like "Chinese")
            # Otherwise route to remove_keywords to strip from search terms
            first_word = m.group(1).split()[0]
            if first_word[0].isupper():
                exclude_brands.append(subj)
            else:
                remove_kws.append(subj.lower())

    # --- Positive: "only X" / "prefer X" (not negated) ---
    positive_brands: list[str] = []

    for m in _ONLY_RE.finditer(text):
        if _in_negative_clause(text, m.start()):
            continue
        b = _clean_subject(m.group(1))
        if b and not _is_stop_word(b):
            positive_brands.append(b)

    # --- Positive: "want X" / "need X" (only if no negation precedes) ---
    for m in _WANT_RE.finditer(text):
        if _has_negation_before(text, m.start()):
            # Negated "want" → treat as negative subject instead
            subj = _clean_subject(m.group(1))
            if subj:
                remove_kws.append(subj.lower())
            continue
        b = _clean_subject(m.group(1))
        if b and not _is_stop_word(b):
            positive_brands.append(b)

    # --- Required specs (strong triggers only) ---
    spec_matches = _SPEC_STRONG_RE.findall(text)
    specs = [s.strip() for s in spec_matches if len(s.strip()) > 2]
    if specs:
        # Only add if not in a negative clause
        valid_specs = []
        for m in _SPEC_STRONG_RE.finditer(text):
            if not _in_negative_clause(text, m.start()):
                s = m.group(1).strip()
                if len(s) > 2:
                    valid_specs.append(s)
        if valid_specs:
            changes["add_required_specs"] = valid_specs

    # --- Keyword shortcuts ---
    add_kws: list[str] = []
    if _FIXER_UPPER_RE.search(lower):
        add_kws.extend(["opknapper", "fixer-upper"])
    if _WHOLE_UNIT_RE.search(lower):
        add_kws.extend(["heel", "compleet"])

    # --- Commit ---
    if positive_brands:
        changes["add_required_brands"] = list(dict.fromkeys(positive_brands))
    if exclude_brands:
        changes["add_excluded_brands"] = list(dict.fromkeys(exclude_brands))
    if remove_kws:
        changes["remove_keywords"] = list(dict.fromkeys(remove_kws))
    if add_kws:
        changes["add_keywords"] = list(dict.fromkeys(add_kws))

    return changes
