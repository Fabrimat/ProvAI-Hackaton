"""Cold-start-friendly seasonal inactivity inference (Priority 3 -- predict).

Implements the 3-layer design from
``docs/plans/gamechanger-triage-and-briefing.md`` Idea 2:

1. Sector-level prior -- a small hardcoded keyword lookup against the NACE
   activity description. Works with zero prior observations of the
   specific business.
2. Review-text mining stub -- scans existing ``evidence.detail`` text for
   explicit Dutch seasonal phrases.
3. Self-accumulating history hook -- honestly reports that the MVP only
   has a single data snapshot rather than fabricating fake history (this
   is a hard requirement from the source plan doc: never invent fake
   historical data to look more impressive than the tool actually is).
"""

# Layer 1: small, hand-curated sector prior. Keys are matched as a
# case-insensitive substring against the NACE activity description
# (omschrijving_hoofdact_rsz / omschrijving_hoofdact_btw). Kept
# deliberately small (~8 entries) but demo-plausible.
SECTOR_PRIORS = {
    "ijssalon": {
        "months_likely_closed": [1, 2, 11, 12],
        "reason": "ice-cream sector (ijssalon) -- typically closed in winter",
    },
    "ijs": {
        "months_likely_closed": [1, 2, 11, 12],
        "reason": "ice-cream/seasonal food sector -- typically closed in winter",
    },
    "camping": {
        "months_likely_closed": [11, 12, 1, 2],
        "reason": "campsite/outdoor-recreation sector -- typically closed outside the camping season",
    },
    "seizoen": {
        "months_likely_closed": [11, 12, 1, 2],
        "reason": "activity description explicitly names a seasonal (seizoensgebonden) operation",
    },
    "strand": {
        "months_likely_closed": [10, 11, 12, 1, 2, 3],
        "reason": "beach-related sector (strandbar/strandcabine) -- typically only open in summer",
    },
    "kerst": {
        "months_likely_closed": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "reason": "Christmas-market/seasonal-stall activity (kerstmarkt) -- only active around December",
    },
    "terras": {
        "months_likely_closed": [11, 12, 1, 2],
        "reason": "terrace-dependent hospitality -- typically quiet or closed outside the warm months",
    },
    "foor": {
        "months_likely_closed": [1, 2, 3, 4, 5, 9, 10, 11],
        "reason": "fairground/kermis stall (foorkraam) -- only active during fair season",
    },
}

# Layer 2: Dutch phrases that, if found verbatim (case-insensitive) in an
# evidence row's free-text detail, indicate the officer/reviewer already
# has direct textual evidence of a seasonal closure pattern.
REVIEW_SEASONAL_PHRASES = [
    "wintersluiting",
    "seizoensgebonden",
    "gesloten in januari",
    "gesloten in de winter",
    "jaarlijks verlof",
    "enkel open in de zomer",
    "gesloten buiten het seizoen",
    "heropent in april",
    "gesloten tijdens winterperiode",
]

DEFAULT_DAMPENER_FACTOR = 0.5
NO_DAMPENER = {"dampener_factor": 1.0, "reason": None}


def _match_sector_prior(business: dict):
    business = business or {}
    text_fields = [
        business.get("omschrijving_hoofdact_rsz"),
        business.get("omschrijving_hoofdact_btw"),
    ]
    combined = " ".join(t for t in text_fields if t).lower()
    if not combined:
        return None
    for keyword, pattern in SECTOR_PRIORS.items():
        if keyword in combined:
            return pattern
    return None


def scan_reviews_for_seasonal_language(evidence_rows: list) -> dict:
    """Scan evidence ``detail`` text for known Dutch seasonal phrases.

    Returns ``{'matched': bool, 'phrase': str or None, 'source': str or None}``.
    """
    for row in evidence_rows or []:
        detail = (row.get("detail") or "") if isinstance(row, dict) else ""
        detail_lower = detail.lower()
        for phrase in REVIEW_SEASONAL_PHRASES:
            if phrase in detail_lower:
                return {"matched": True, "phrase": phrase, "source": row.get("source")}
    return {"matched": False, "phrase": None, "source": None}


def check_snapshot_history(business_uidn, db_path: str = None) -> dict:
    """Stub for layer 3 (self-accumulating multi-snapshot history).

    Honest MVP behaviour: the dataset is a single point-in-time snapshot,
    so there is nothing to compare against yet. This deliberately does
    NOT fabricate fake historical data -- it just says so.
    """
    return {
        "has_history": False,
        "note": (
            "Only one data snapshot available, so historical pattern detection "
            "will activate once repeated snapshots exist."
        ),
    }


def seasonal_dampener(business: dict, evidence_rows: list, current_month: int) -> dict:
    """Combine layers 1 and 2 into a single triage dampener.

    Returns ``{'dampener_factor': float in [0, 1], 'reason': str or None}``.
    A factor of 1.0 means no dampening (full priority stands, i.e. the
    silence looks like it could genuinely mean the business is gone);
    a lower factor tells the UI to visibly lower this row's urgency
    because the evidence looks like a predictable seasonal closure
    rather than abandonment. Never suppresses the row outright -- the
    officer still sees it and can override.
    """
    sector_match = _match_sector_prior(business)
    if sector_match and current_month in sector_match["months_likely_closed"]:
        return {
            "dampener_factor": DEFAULT_DAMPENER_FACTOR,
            "reason": (
                "Priority lowered: likely seasonal closure, not abandonment "
                f"({sector_match['reason']})"
            ),
        }

    review_match = scan_reviews_for_seasonal_language(evidence_rows)
    if review_match["matched"]:
        return {
            "dampener_factor": DEFAULT_DAMPENER_FACTOR,
            "reason": (
                "Priority lowered: existing evidence mentions a seasonal closure "
                f"(matched phrase: '{review_match['phrase']}')"
            ),
        }

    return dict(NO_DAMPENER)
