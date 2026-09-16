"""Google Maps evidence source (Priority 1 -- scraping).

Builds a dict shaped exactly like a real Google Places "Place Details"
response (``business_status``, ``rating``, ``user_ratings_total``,
``name``, ``formatted_address``) -- either fabricated (mock) or fetched
live (real, if ``GOOGLE_MAPS_API_KEY`` is set) -- and derives
``signal``/``detail`` from THAT dict via one shared mapping function
(``_signal_from_place_details``). The mapping logic is therefore the
exact same code path whether the response came from the mock generator
or the real API, so swapping mock -> real later is a drop-in.

Mock path (used when no key is configured, or when a real call fails for
any reason): deterministically pseudo-random, seeded on
``business['uidn']`` so demo runs are reproducible. Biased ~70%
``OPERATIONAL`` / ~15% ``CLOSED_PERMANENTLY`` / ~15% not found -- a
plausible-looking mix for a demo, not a claim about real coverage.
"""
import os
import random
from datetime import datetime, timezone

import requests

from app.db import get_connection

SOURCE_NAME = "google_maps"

FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
PLACE_DETAILS_FIELDS = "business_status,rating,user_ratings_total,name,formatted_address"
REQUEST_TIMEOUT_SECONDS = 10

# Mock roll thresholds: [0, ACTIVE_CUTOFF) -> OPERATIONAL, [ACTIVE_CUTOFF, INACTIVE_CUTOFF) -> CLOSED_PERMANENTLY, rest -> not found.
ACTIVE_CUTOFF = 0.70
INACTIVE_CUTOFF = 0.85


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


def _business_address(business: dict) -> str:
    straat = business.get("kbo_straat") or business.get("straat") or ""
    huisnr = business.get("kbo_huisnr") or business.get("huisnr") or ""
    postcode = business.get("kbo_postcode") or business.get("postcode") or ""
    gemeente = business.get("kbo_gemeente") or business.get("gemeente") or ""
    parts = [p for p in (f"{straat} {huisnr}".strip(), postcode, gemeente) if p]
    return ", ".join(parts)


def _fabricate_place_details(business: dict):
    """Fabricate a dict shaped like a real Places "Place Details" result.

    Returns ``None`` to represent "no place found" -- a real Find Place
    From Text call returning zero candidates -- rather than inventing a
    sentinel field that wouldn't exist in a real response.
    """
    uidn = business.get("uidn")
    name = _business_name(business)
    rng = random.Random(uidn)
    roll = rng.random()

    if roll < ACTIVE_CUTOFF:
        return {
            "name": name,
            "business_status": "OPERATIONAL",
            "rating": round(rng.uniform(3.2, 4.9), 1),
            "user_ratings_total": rng.randint(2, 180),
            "formatted_address": _business_address(business),
        }
    if roll < INACTIVE_CUTOFF:
        has_reviews = rng.random() < 0.6
        return {
            "name": name,
            "business_status": "CLOSED_PERMANENTLY",
            "rating": round(rng.uniform(2.5, 4.5), 1) if has_reviews else None,
            "user_ratings_total": rng.randint(1, 60) if has_reviews else None,
            "formatted_address": _business_address(business),
        }
    return None  # no candidates -- not listed on Google Maps at all


def _signal_from_place_details(place, name: str):
    """Derive (signal, detail) from a real-shaped Place Details dict.

    This is the single mapping code path used for both the mock and the
    real Google Places API response -- only the *source* of ``place``
    differs, not how it's interpreted.
    """
    if not place:
        return "silent", f"No Google Maps listing found matching '{name}' at this address"

    status = place.get("business_status")
    rating = place.get("rating")
    review_count = place.get("user_ratings_total")
    listed_name = place.get("name") or name
    rating_bit = (
        f", {rating}★ ({review_count} reviews)"
        if rating is not None and review_count is not None
        else ""
    )

    if status == "OPERATIONAL":
        return "active", f"Google Maps listing found for '{listed_name}', marked 'Open'{rating_bit}"
    if status == "CLOSED_TEMPORARILY":
        return (
            "inactive",
            f"Google Maps listing found for '{listed_name}', marked 'Temporarily closed'{rating_bit}",
        )
    if status == "CLOSED_PERMANENTLY":
        return (
            "inactive",
            f"Google Maps listing found for '{listed_name}', marked 'Permanently closed'{rating_bit}",
        )
    # Unexpected/unknown status from a real response -- inconclusive, not a guess.
    return "silent", f"Google Maps listing found for '{listed_name}' but status is unclear ({status!r})"


def _fetch_real_place_details(business: dict, api_key: str):
    """Attempt a real Google Places lookup. May raise -- caller handles it."""
    name = _business_name(business)
    address = _business_address(business)

    find_params = {
        "input": f"{name} {address}".strip(),
        "inputtype": "textquery",
        "fields": "place_id",
        "key": api_key,
    }
    find_response = requests.get(FIND_PLACE_URL, params=find_params, timeout=REQUEST_TIMEOUT_SECONDS)
    find_response.raise_for_status()
    find_payload = find_response.json()

    status = find_payload.get("status")
    if status == "ZERO_RESULTS":
        return None  # genuinely not found -- a real, valid outcome, not a failure
    if status != "OK":
        raise RuntimeError(f"Find Place API status: {status}")

    candidates = find_payload.get("candidates") or []
    if not candidates or not candidates[0].get("place_id"):
        return None
    place_id = candidates[0]["place_id"]

    details_params = {"place_id": place_id, "fields": PLACE_DETAILS_FIELDS, "key": api_key}
    details_response = requests.get(PLACE_DETAILS_URL, params=details_params, timeout=REQUEST_TIMEOUT_SECONDS)
    details_response.raise_for_status()
    details_payload = details_response.json()

    if details_payload.get("status") != "OK":
        raise RuntimeError(f"Place Details API status: {details_payload.get('status')}")

    return details_payload.get("result") or {}


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
    """Return a Google Maps signal for ``business`` and log it.

    Uses the real Google Places API when ``GOOGLE_MAPS_API_KEY`` is set
    in the environment and the call succeeds. Falls back to the
    deterministic mock (seeded on ``business['uidn']``) when no key is
    configured, or when the real call fails for any reason (network
    error, timeout, quota, malformed response) -- the fallback is always
    logged in ``detail``, never silently swapped.
    """
    business = business or {}
    uidn = business.get("uidn")
    name = _business_name(business)
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    fallback_note = ""

    place_details = None
    used_real = False
    if api_key:
        try:
            place_details = _fetch_real_place_details(business, api_key)
            used_real = True
        except Exception as exc:  # noqa: BLE001 -- must never crash the pipeline
            fallback_note = f"[mock, real API unavailable: {exc}] "

    if not used_real:
        place_details = _fabricate_place_details(business)

    signal, detail = _signal_from_place_details(place_details, name)
    detail = f"{fallback_note}{detail}"

    _log_evidence(uidn, signal, detail, db_path)
    return {"signal": signal, "detail": detail}
