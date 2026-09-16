"""Real evidence source: OpenStreetMap Overpass API (free, keyless).

Queries a small radius around the business's latitude/longitude for POI
nodes (shop/office/amenity tags) and fuzzy-matches their ``name`` tag
against the business name. The whole network call is wrapped in
try/except: a missing location, a network failure, a timeout, or a
malformed response must never crash the pipeline -- they all degrade to
a 'silent' signal with an explanatory detail instead.
"""
import difflib
from datetime import datetime, timezone

import requests

from app.db import get_connection

SOURCE_NAME = "osm"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RADIUS_METERS = 50
TIMEOUT_SECONDS = 10
NAME_MATCH_RATIO = 0.6


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


def _coords(business: dict):
    lat = business.get("latitude")
    lon = business.get("longitude")
    return lat, lon


def _name_similarity(a: str, b: str) -> float:
    a_l, b_l = (a or "").strip().lower(), (b or "").strip().lower()
    if not a_l or not b_l:
        return 0.0
    if a_l in b_l or b_l in a_l:
        return 1.0
    return difflib.SequenceMatcher(None, a_l, b_l).ratio()


def _log_evidence(business_uidn, signal, detail, db_path=None) -> None:
    """Replace any existing evidence row for (business_uidn, SOURCE_NAME).

    Re-running verification must not accumulate an ever-growing history
    of rows for the same source -- at most one row per (business,
    source) pair exists at any time, representing the latest reading.
    """
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        conn.execute(
            "DELETE FROM evidence WHERE business_uidn = ? AND source = ?",
            (business_uidn, SOURCE_NAME),
        )
        conn.execute(
            "INSERT INTO evidence (business_uidn, source, signal, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (business_uidn, SOURCE_NAME, signal, detail, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def check(business: dict, db_path: str = None) -> dict:
    """Return a real OSM/Overpass signal for ``business`` and log it.

    Never raises -- any failure (missing coordinates, network error,
    timeout, bad JSON) results in a returned 'silent' signal instead.
    """
    business = business or {}
    uidn = business.get("uidn")
    name = _business_name(business)
    lat, lon = _coords(business)

    if lat is None or lon is None:
        signal = "silent"
        detail = "OSM: no query possible (missing coordinates)"
        _log_evidence(uidn, signal, detail, db_path)
        return {"signal": signal, "detail": detail}

    query = (
        f"[out:json][timeout:{TIMEOUT_SECONDS}];"
        f'(node["shop"](around:{RADIUS_METERS},{lat},{lon});'
        f'node["office"](around:{RADIUS_METERS},{lat},{lon});'
        f'node["amenity"](around:{RADIUS_METERS},{lat},{lon});'
        f");out body;"
    )

    try:
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": "ProvAI-Schoten-Verification/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        elements = payload.get("elements", []) or []
    except Exception as exc:  # noqa: BLE001 -- must never crash the pipeline
        signal = "silent"
        detail = f"OSM: query failed ({exc})"
        _log_evidence(uidn, signal, detail, db_path)
        return {"signal": signal, "detail": detail}

    if not elements:
        signal = "silent"
        detail = f"OSM: no POI found within {RADIUS_METERS}m of the registered coordinates"
        _log_evidence(uidn, signal, detail, db_path)
        return {"signal": signal, "detail": detail}

    best_ratio = 0.0
    best_name = None
    for element in elements:
        tags = element.get("tags") or {}
        poi_name = tags.get("name")
        if not poi_name:
            continue
        ratio = _name_similarity(name, poi_name)
        if ratio > best_ratio:
            best_ratio = ratio
            best_name = poi_name

    if best_name is None:
        signal = "silent"
        detail = (
            f"OSM: {len(elements)} POI(s) found within {RADIUS_METERS}m, but none carry a "
            f"'name' tag to compare against '{name}'"
        )
    elif best_ratio > NAME_MATCH_RATIO:
        signal = "active"
        detail = f"OSM: POI '{best_name}' found within {RADIUS_METERS}m, name matches '{name}'"
    else:
        signal = "disagreement"
        detail = (
            f"OSM: POI '{best_name}' found within {RADIUS_METERS}m, but its name does not "
            f"match the registered business '{name}' -- a different business may occupy this location"
        )

    _log_evidence(uidn, signal, detail, db_path)
    return {"signal": signal, "detail": detail}
