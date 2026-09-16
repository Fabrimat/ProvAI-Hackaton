"""Simulated "what changed since the last check" freshness/snapshot-diff demo.

Honesty note (read this before trusting any number this module prints):
this repo only has **one** real data pull (`data/provai.db`, itself loaded
from the single CSV/GeoJSON snapshot `schoten-kbo-1000-2026-09-07.*`).
There is no second, genuinely-older snapshot to diff against. To make the
"freshness" concept demoable today, ``generate_baseline_snapshot`` takes the
real current data and, with a seeded RNG, deterministically *pretends* a
small, plausible subset of it looked different a couple of weeks ago
(a handful of simulated closures, simulated officer confirmations, and a
"new since baseline" flag on a few already-registered businesses). None of
this is written back to the database; it only exists in-memory for this
diff. It must never be presented to an end user as real historical data.
Once the tool has actually run against the same municipality on two real
dates, this module should be replaced by a genuine two-snapshot diff.

Public API:
    generate_baseline_snapshot(db_path=None, seed=42) -> dict
    compute_diff(db_path=None, seed=42) -> dict
"""

import random
from datetime import date, timedelta

from app.db import DEFAULT_DB_PATH
from app.ingest import list_businesses

# A fixed, plausible "how long ago was the baseline" window for the demo.
BASELINE_DAYS_AGO = 14

# The rechtstoestand value that means "active/normal" in the real data.
ACTIVE_RECHTSTOESTAND = "Normale toestand"

# Roughly how much of the register we perturb for the demo (kept within the
# 3-5% range requested so the diff stays small and readable, not noisy).
PERTURBATION_FRACTION = 0.04

# How the total perturbation budget is split across the three simulated
# change types.
NEW_BUSINESS_SHARE = 0.25
STATUS_CHANGE_SHARE = 0.35
# (closures gets the remainder)

# How many of the most-recently-registered businesses are considered
# plausible candidates for "new since baseline".
RECENT_CANDIDATE_POOL_SIZE = 30

SIMULATED_REVIEW_STATUSES = ["confirmed_active", "confirmed_inactive"]


def _business_name(b: dict) -> str:
    """Mirror of the UI's business_name() helper, kept local (no cross-import)."""
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "zoeknaam"):
        value = b.get(key)
        if value:
            return value
    uidn = b.get("uidn")
    return f"Onderneming {uidn}" if uidn is not None else "Onbekend bedrijf"


def _format_address(b: dict) -> str:
    """Mirror of the UI's format_address() helper, kept local (no cross-import)."""
    straat = b.get("kbo_straat") or ""
    huisnr = b.get("kbo_huisnr") or ""
    postcode = b.get("kbo_postcode") or ""
    gemeente = b.get("kbo_gemeente") or ""
    straat_huisnr = f"{straat} {huisnr}".strip()
    rest = " ".join(p for p in (postcode, gemeente) if p)
    parts = [p for p in (straat_huisnr, rest) if p]
    return ", ".join(parts) if parts else "Adres onbekend"


def _registration_date(b: dict):
    """Best available registration-ish date for a business, or None."""
    return b.get("datum_inschrijving") or b.get("startdatum")


def generate_baseline_snapshot(db_path: str = None, seed: int = 42) -> dict:
    """Deterministically synthesize a simulated "baseline" (past) snapshot.

    Reads the real current `businesses` data via ``list_businesses`` and,
    using a ``random.Random(seed)`` instance, picks a small subset (~3-5% of
    the register) to describe as having looked different at
    ``baseline_date``. Three kinds of simulated change are produced:

    - ``closures``: businesses whose CURRENT ``rechtstoestand`` already
      indicates a closure/dissolution/bankruptcy in the real data are
      picked, and the baseline is described as having shown them as
      ``"Normale toestand"`` (i.e. we simulate that the closure happened
      *since* the baseline: the current value is real, only the baseline
      value is invented).
    - ``status_changes``: a few businesses are picked and given a simulated
      baseline ``review_status`` of ``"pending"`` vs. a simulated current
      ``review_status`` of ``"confirmed_active"``/``"confirmed_inactive"``,
      standing in for an officer confirmation that happened since the
      baseline. (The real ``status`` table is essentially empty in this
      demo dataset, so this whole axis is simulated, not just the baseline
      half of it.)
    - ``new_businesses``: a few of the real, more-recently-registered
      businesses (by ``datum_inschrijving``/``startdatum``) are picked and
      marked as not having existed in the baseline at all.

    Nothing is written to the database. Returns a dict:
        {
            "baseline_date": "YYYY-MM-DD",
            "seed": seed,
            "total_businesses_now": int,
            "perturbations": {
                "closures": [ {uidn, name, field, baseline_value, current_value}, ... ],
                "status_changes": [ {uidn, name, field, baseline_value, current_value}, ... ],
                "new_businesses": [ {uidn, name, field, baseline_value, current_value, datum_inschrijving}, ... ],
            },
        }

    Deterministic: the same ``seed`` (with the same underlying database
    contents) always selects the same records and produces the same
    simulated values.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    businesses = list_businesses(db_path)
    businesses.sort(key=lambda b: b["uidn"])  # stable order regardless of SQL row order
    total = len(businesses)

    rng = random.Random(seed)

    baseline_date = (date.today() - timedelta(days=BASELINE_DAYS_AGO)).isoformat()

    target_total = max(6, round(total * PERTURBATION_FRACTION)) if total else 0
    n_new = max(1, round(target_total * NEW_BUSINESS_SHARE)) if target_total else 0
    n_status = max(1, round(target_total * STATUS_CHANGE_SHARE)) if target_total else 0
    n_closure = max(0, target_total - n_new - n_status)

    # --- Closures: real businesses whose current rechtstoestand already
    # shows a closure/dissolution state; baseline is simulated as "normal".
    closure_candidates = [
        b
        for b in businesses
        if b.get("rechtstoestand") and b.get("rechtstoestand") != ACTIVE_RECHTSTOESTAND
    ]
    n_closure = min(n_closure, len(closure_candidates))
    selected_closures = (
        rng.sample(closure_candidates, n_closure) if n_closure > 0 else []
    )
    closure_uidns = {b["uidn"] for b in selected_closures}

    remaining_after_closures = [b for b in businesses if b["uidn"] not in closure_uidns]

    # --- New businesses: real, recently-registered businesses picked from
    # the pool of the most-recently-registered candidates.
    dated = [b for b in remaining_after_closures if _registration_date(b)]
    dated.sort(key=lambda b: (_registration_date(b), b["uidn"]), reverse=True)
    recent_pool = dated[:RECENT_CANDIDATE_POOL_SIZE]
    n_new = min(n_new, len(recent_pool))
    selected_new = rng.sample(recent_pool, n_new) if n_new > 0 else []
    new_uidns = {b["uidn"] for b in selected_new}

    remaining_after_new = [
        b for b in remaining_after_closures if b["uidn"] not in new_uidns
    ]

    # --- Status changes: simulated officer confirmations since baseline.
    n_status = min(n_status, len(remaining_after_new))
    selected_status = (
        rng.sample(remaining_after_new, n_status) if n_status > 0 else []
    )

    closures = [
        {
            "uidn": b["uidn"],
            "name": _business_name(b),
            "field": "rechtstoestand",
            "baseline_value": ACTIVE_RECHTSTOESTAND,
            "current_value": b.get("rechtstoestand"),
        }
        for b in selected_closures
    ]

    status_changes = [
        {
            "uidn": b["uidn"],
            "name": _business_name(b),
            "field": "review_status",
            "baseline_value": "pending",
            "current_value": rng.choice(SIMULATED_REVIEW_STATUSES),
        }
        for b in selected_status
    ]

    new_businesses = [
        {
            "uidn": b["uidn"],
            "name": _business_name(b),
            "field": "existence",
            "baseline_value": None,
            "current_value": "bestaat",
            "datum_inschrijving": _registration_date(b),
        }
        for b in selected_new
    ]

    return {
        "baseline_date": baseline_date,
        "seed": seed,
        "total_businesses_now": total,
        "perturbations": {
            "closures": closures,
            "status_changes": status_changes,
            "new_businesses": new_businesses,
        },
    }


def compute_diff(db_path: str = None, seed: int = 42) -> dict:
    """Compare the simulated baseline against the real current data.

    Calls ``generate_baseline_snapshot`` and joins its picks back against
    the real, current ``businesses`` rows (for address/name enrichment),
    returning a UI-ready diff structure:

        {
            "baseline_date": "YYYY-MM-DD",
            "new_businesses": [ {uidn, name, address, datum_inschrijving}, ... ],
            "status_changes": [ {uidn, name, address, old_status, new_status}, ... ],
            "closures_detected": [ {uidn, name, address, old_rechtstoestand, new_rechtstoestand}, ... ],
            "total_businesses_then": int,
            "total_businesses_now": int,
        }

    Deterministic for a given ``seed`` (see ``generate_baseline_snapshot``).
    See the module docstring: this is a simulated demo diff, not a real
    two-snapshot comparison.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    baseline = generate_baseline_snapshot(db_path=db_path, seed=seed)
    businesses_by_uidn = {b["uidn"]: b for b in list_businesses(db_path)}

    perturbations = baseline["perturbations"]

    new_businesses = []
    for entry in perturbations["new_businesses"]:
        b = businesses_by_uidn.get(entry["uidn"], {})
        new_businesses.append(
            {
                "uidn": entry["uidn"],
                "name": entry["name"],
                "address": _format_address(b),
                "datum_inschrijving": entry.get("datum_inschrijving"),
            }
        )

    status_changes = []
    for entry in perturbations["status_changes"]:
        b = businesses_by_uidn.get(entry["uidn"], {})
        status_changes.append(
            {
                "uidn": entry["uidn"],
                "name": entry["name"],
                "address": _format_address(b),
                "old_status": entry["baseline_value"],
                "new_status": entry["current_value"],
            }
        )

    closures_detected = []
    for entry in perturbations["closures"]:
        b = businesses_by_uidn.get(entry["uidn"], {})
        closures_detected.append(
            {
                "uidn": entry["uidn"],
                "name": entry["name"],
                "address": _format_address(b),
                "old_rechtstoestand": entry["baseline_value"],
                "new_rechtstoestand": entry["current_value"],
            }
        )

    total_now = baseline["total_businesses_now"]
    total_then = total_now - len(new_businesses)

    return {
        "baseline_date": baseline["baseline_date"],
        "new_businesses": new_businesses,
        "status_changes": status_changes,
        "closures_detected": closures_detected,
        "total_businesses_then": total_then,
        "total_businesses_now": total_now,
    }
