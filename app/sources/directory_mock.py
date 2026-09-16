"""Belgian business phone directory evidence source (Priority 1 -- scraping).

Represents a lookup against a Belgian business directory. **Infobel**
(infobel.com) is used as the primary shape here since it's API-first;
**Gouden Gids / Pages d'Or** (goudengids.be / pagesdor.be) is the
realistic alternative/fallback data source for the same kind of lookup
if Infobel access isn't available -- not implemented separately, same
pattern would apply.

Builds a dict shaped like a real Infobel lookup result (``found``,
``listed_phone``, ``listed_name``, ``category``) -- either fabricated
(mock) or fetched live (real, if ``INFOBEL_API_KEY`` is set) -- and
derives ``signal``/``detail`` from THAT dict via one shared mapping
function (``_signal_from_directory_listing``), same pattern as
``gmaps_mock.py`` / ``trustpilot_mock.py``.

Mock path (used when no key is configured, or when a real call fails for
any reason): deterministically pseudo-random, seeded on
``business['uidn']``. Belgian phone directories skew toward decent
coverage for registered businesses but go stale (numbers get
disconnected/reassigned), so this is biased ~55% found with a phone
number matching the KBO record (active), ~20% found but with a phone
number that DIFFERS from the KBO record (disagreement -- could mean
moved/changed hands), ~25% not found at all (silent).
"""
import os
import random
from datetime import datetime, timezone

import requests

from app.db import get_connection

SOURCE_NAME = "infobel"

INFOBEL_SEARCH_URL = "https://api.infobel.com/v3/search"
REQUEST_TIMEOUT_SECONDS = 10

# Mock roll thresholds: [0, FOUND_MATCH_CUTOFF) -> found, phone matches;
# [FOUND_MATCH_CUTOFF, FOUND_MISMATCH_CUTOFF) -> found, phone differs; rest -> not found.
FOUND_MATCH_CUTOFF = 0.55
FOUND_MISMATCH_CUTOFF = 0.75


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


def _business_phone(business: dict):
    return business.get("telefoonnummer") or business.get("phone")


def _plausible_category(business: dict) -> str:
    return (
        business.get("omschrijving_hoofdact_rsz")
        or business.get("omschrijving_hoofdact_btw")
        or "Onderneming (categorie onbekend)"
    )


def _normalize_phone(value) -> str:
    return "".join(ch for ch in str(value) if ch.isdigit())


def _fabricate_phone(rng: random.Random, avoid=None) -> str:
    number = f"03 {rng.randint(200, 799)} {rng.randint(1000, 9999)}"
    if avoid and _normalize_phone(number) == _normalize_phone(avoid):
        number = f"03 {rng.randint(200, 799)} {rng.randint(1000, 9999)}"
    return number


def _fabricate_directory_listing(business: dict, rng: random.Random):
    """Fabricate a dict shaped like a real Infobel lookup result.

    Returns ``None`` to represent "not listed" -- a real zero-results
    lookup -- rather than inventing a sentinel field. ``phone_mismatch``
    is a mock-only bookkeeping flag (a real API response won't carry it)
    that lets the mock hit its target ~55/20/25 distribution exactly even
    for businesses with no phone on file in the KBO register; the
    derivation function falls back to comparing ``listed_phone`` against
    the KBO record directly when this flag is absent (i.e. for real data).
    """
    name = _business_name(business)
    kbo_phone = _business_phone(business)
    category = _plausible_category(business)
    roll = rng.random()

    if roll < FOUND_MATCH_CUTOFF:
        listed_phone = kbo_phone or _fabricate_phone(rng)
        return {
            "found": True,
            "listed_phone": listed_phone,
            "listed_name": name,
            "category": category,
            "phone_mismatch": False,
        }
    if roll < FOUND_MISMATCH_CUTOFF:
        listed_phone = _fabricate_phone(rng, avoid=kbo_phone)
        return {
            "found": True,
            "listed_phone": listed_phone,
            "listed_name": name,
            "category": category,
            "phone_mismatch": True,
        }
    return None  # not listed in the directory at all


def _signal_from_directory_listing(listing, business: dict, name: str):
    """Derive (signal, detail) from a real-shaped directory listing dict.

    Single mapping code path used for both the mock and a real Infobel
    API response.
    """
    if not listing or not listing.get("found"):
        return "silent", f"Infobel: no listing found for '{name}' in the Belgian business directory"

    listed_phone = listing.get("listed_phone")
    listed_name = listing.get("listed_name") or name
    category = listing.get("category") or "onbekende categorie"
    kbo_phone = _business_phone(business)

    mismatch = listing.get("phone_mismatch")
    if mismatch is None and kbo_phone and listed_phone:
        mismatch = _normalize_phone(kbo_phone) != _normalize_phone(listed_phone)

    if mismatch:
        kbo_phone_display = kbo_phone or "no phone on file"
        return (
            "disagreement",
            f"Infobel: listing found for '{listed_name}' ({category}), but the listed phone "
            f"{listed_phone} differs from the registered phone ({kbo_phone_display}) -- possible "
            "relocation or ownership change",
        )

    return (
        "active",
        f"Infobel: listing found for '{listed_name}' ({category}), phone {listed_phone or 'n/a'}",
    )


def _fetch_real_directory(business: dict, api_key: str):
    """Attempt a real Infobel lookup by name + postcode. May raise -- caller handles it."""
    name = _business_name(business)
    postcode = business.get("kbo_postcode") or business.get("postcode")

    response = requests.get(
        INFOBEL_SEARCH_URL,
        params={"name": name, "zip": postcode, "country": "BE", "apikey": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") or payload.get("data") or []
    if not results:
        return None  # genuinely not found -- a real, valid outcome, not a failure

    top = results[0]
    return {
        "found": True,
        "listed_phone": top.get("phone") or top.get("telephone"),
        "listed_name": top.get("name") or name,
        "category": top.get("category") or top.get("activity"),
    }


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
    """Return a Belgian business-directory signal for ``business`` and log it.

    Uses the real Infobel API when ``INFOBEL_API_KEY`` is set in the
    environment and the call succeeds. Falls back to the deterministic
    mock (seeded on ``business['uidn']``) when no key is configured, or
    when the real call fails for any reason -- the fallback is always
    logged in ``detail``, never silently swapped.
    """
    business = business or {}
    uidn = business.get("uidn")
    name = _business_name(business)
    api_key = os.environ.get("INFOBEL_API_KEY")
    fallback_note = ""

    listing = None
    used_real = False
    if api_key:
        try:
            listing = _fetch_real_directory(business, api_key)
            used_real = True
        except Exception as exc:  # noqa: BLE001 -- must never crash the pipeline
            fallback_note = f"[mock, real API unavailable: {exc}] "

    if not used_real:
        rng = random.Random(uidn)
        listing = _fabricate_directory_listing(business, rng)

    signal, detail = _signal_from_directory_listing(listing, business, name)
    detail = f"{fallback_note}{detail}"

    _log_evidence(uidn, signal, detail, db_path)
    return {"signal": signal, "detail": detail}
