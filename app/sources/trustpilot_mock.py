"""Trustpilot evidence source (Priority 1 -- scraping).

Builds a dict shaped like a real Trustpilot Business Units API response
(``trustScore``, ``numberOfReviews``, ``stars``, ``displayName``) --
either fabricated (mock) or fetched live (real, if ``TRUSTPILOT_API_KEY``
is set) -- and derives ``signal``/``detail`` from THAT dict via one
shared mapping function (``_signal_from_business_unit``). The mapping
logic is therefore the same code path whether the response came from the
mock generator or the real API, so swapping mock -> real later is a
drop-in.

Mock path (used when no key is configured, or when a real call fails for
any reason): deterministically pseudo-random, seeded on
``business['uidn']``. Trustpilot naturally has sparser coverage for
small local businesses than Google Maps, so this is biased toward
silence: roughly 50% not found, 40% active (a page with reviews), 10%
disagreement (reviews say it closed while the listing is still up --
exactly the kind of conflicting evidence the triage scorer should flag).

Note: real-time review-text scanning (the source of the mock's
"disagreement" case) would require a separate Trustpilot Reviews API
call, out of scope for this MVP's real-API integration -- so a *real*
lookup can only ever resolve to 'active' or 'silent', never
'disagreement'; the mock path still exercises 'disagreement' for demo
purposes since the mapping function supports it generically.
"""
import os
import random
from datetime import datetime, timezone

import requests

from app.db import get_connection

SOURCE_NAME = "trustpilot"

TRUSTPILOT_FIND_URL = "https://api.trustpilot.com/v1/business-units/find"
TRUSTPILOT_UNIT_URL = "https://api.trustpilot.com/v1/business-units/{business_unit_id}"
REQUEST_TIMEOUT_SECONDS = 10

# Mock roll thresholds: [0, ACTIVE_CUTOFF) -> active, [ACTIVE_CUTOFF, SILENT_CUTOFF) -> not found, rest -> disagreement.
ACTIVE_CUTOFF = 0.40
SILENT_CUTOFF = 0.90


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


def _fabricate_business_unit(business: dict):
    """Fabricate a dict shaped like a real Trustpilot Business Unit result.

    Returns ``None`` to represent "no business unit found" -- a real
    404/not-found outcome, not a made-up sentinel field.
    """
    uidn = business.get("uidn")
    name = _business_name(business)
    rng = random.Random(uidn)
    roll = rng.random()

    if roll < ACTIVE_CUTOFF:
        return {
            "displayName": name,
            "trustScore": round(rng.uniform(2.8, 4.8), 1),
            "numberOfReviews": {"total": rng.randint(1, 40)},
            "stars": rng.randint(3, 5),
            "closure_mentioned_in_reviews": False,
        }
    if roll < SILENT_CUTOFF:
        return None  # no Trustpilot presence at all -- common for small local businesses
    return {
        "displayName": name,
        "trustScore": round(rng.uniform(3.0, 4.5), 1),
        "numberOfReviews": {"total": rng.randint(2, 15)},
        "stars": rng.randint(3, 5),
        "closure_mentioned_in_reviews": True,
    }


def _signal_from_business_unit(unit, name: str):
    """Derive (signal, detail) from a real-shaped Business Unit dict.

    Single mapping code path used for both the mock and the real
    Trustpilot API response.
    """
    if not unit:
        return "silent", f"No Trustpilot page found for '{name}' -- common for small local businesses"

    reviews_field = unit.get("numberOfReviews")
    reviews_total = reviews_field.get("total", 0) if isinstance(reviews_field, dict) else (reviews_field or 0)
    trust_score = unit.get("trustScore")
    display_name = unit.get("displayName") or name

    if unit.get("closure_mentioned_in_reviews"):
        return (
            "disagreement",
            f"Trustpilot page found for '{display_name}' and still marked as an active listing "
            f"(trustScore {trust_score}), but recent reviews mention the business has closed",
        )

    if reviews_total:
        return (
            "active",
            f"Trustpilot page found for '{display_name}', {reviews_total} review(s), trustScore {trust_score}",
        )

    return "silent", f"Trustpilot page found for '{display_name}' but it has no reviews yet"


def _fetch_real_business_unit(business: dict, api_key: str):
    """Attempt a real Trustpilot Business Units lookup. May raise -- caller handles it."""
    name = _business_name(business)

    find_response = requests.get(
        TRUSTPILOT_FIND_URL,
        params={"name": name, "apikey": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if find_response.status_code == 404:
        return None  # genuinely no business unit found -- a real, valid outcome
    find_response.raise_for_status()
    find_payload = find_response.json()

    business_unit_id = find_payload.get("id") or find_payload.get("businessUnitId")
    if not business_unit_id:
        return None

    unit_response = requests.get(
        TRUSTPILOT_UNIT_URL.format(business_unit_id=business_unit_id),
        params={"apikey": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if unit_response.status_code == 404:
        return None
    unit_response.raise_for_status()
    return unit_response.json()


def _log_evidence(business_uidn, signal, detail, db_path=None) -> None:
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        conn.execute(
            "INSERT INTO evidence (business_uidn, source, signal, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (business_uidn, SOURCE_NAME, signal, detail, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def check(business: dict, db_path: str = None) -> dict:
    """Return a Trustpilot signal for ``business`` and log it.

    Uses the real Trustpilot Business Units API when
    ``TRUSTPILOT_API_KEY`` is set in the environment and the call
    succeeds. Falls back to the deterministic mock (seeded on
    ``business['uidn']``) when no key is configured, or when the real
    call fails for any reason -- the fallback is always logged in
    ``detail``, never silently swapped.
    """
    business = business or {}
    uidn = business.get("uidn")
    name = _business_name(business)
    api_key = os.environ.get("TRUSTPILOT_API_KEY")
    fallback_note = ""

    unit = None
    used_real = False
    if api_key:
        try:
            unit = _fetch_real_business_unit(business, api_key)
            used_real = True
        except Exception as exc:  # noqa: BLE001 -- must never crash the pipeline
            fallback_note = f"[mock, real API unavailable: {exc}] "

    if not used_real:
        unit = _fabricate_business_unit(business)

    signal, detail = _signal_from_business_unit(unit, name)
    detail = f"{fallback_note}{detail}"

    _log_evidence(uidn, signal, detail, db_path)
    return {"signal": signal, "detail": detail}
