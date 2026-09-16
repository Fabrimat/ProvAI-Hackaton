"""Pre-run verification for a curated set of real businesses so the officer
dashboard has compelling, story-shaped content the moment a live demo opens
it -- rather than 1000 unscored rows.

Usage (from repo root, either style works and needs no manual PYTHONPATH):
    python -m scripts.seed_demo
    python scripts/seed_demo.py

This script intentionally writes to the REAL demo database
(``data/provai.db``), not a temp copy -- unlike ``tests/test_pipeline.py``,
populating the real DB is the whole point here. Safe to re-run: ``scores``
upserts (``INSERT ... ON CONFLICT ... DO UPDATE``), but ``evidence`` is an
append-only log with no such dedup -- calling ``run_all_sources()`` twice
for the same business would otherwise insert a second set of 6 rows and
double ``compute_score()``'s uncertainty tally each time (verified: without
this, priority scores doubled on a second run). To make re-runs genuinely
idempotent, this script deletes any pre-existing evidence rows for its
curated businesses before re-scoring them, rather than letting evidence
accumulate across runs. The five mock/stub evidence sources (Google Maps,
Trustpilot, Infobel, AI voice, email) are deterministically seeded on each
business's ``uidn``, so their results are stable run to run; the sixth
source, OSM, makes a real network call each time and its result may
legitimately vary (or degrade to 'silent' if the Overpass API is
unreachable -- verified to be the case in some sandboxed environments,
where each OSM lookup burns its ~10s timeout).

Curated selection strategy:
  - "High priority" bucket: businesses predicted (via a local, read-only
    replica of the same seeded-RNG mock logic used by the real evidence
    sources) to produce a disagreement/silent-heavy mix, i.e. high
    uncertainty once actually scored.
  - "Low priority" bucket: businesses predicted to have all five
    deterministic sources agree 'active' -- i.e. the sources that aren't
    a live, unpredictable network call.
  - Actual evidence/scores are always produced for real afterwards by
    ``app.scoring.run_all_sources`` + ``compute_score`` -- the prediction
    above is only used to pick a good demo mix, never to fabricate data.

NOTE ON THE SEASONAL-DAMPENER DEMO PATH: the brief also asked for one
business that hits ``app.seasonal``'s hardcoded seasonal-sector keywords
(e.g. ice cream / camping). A scan of all 1000 real
``omschrijving_hoofdact_rsz`` / ``omschrijving_hoofdact_btw`` values in
this dataset found zero genuine matches. The only keyword hits are false
positives from plain substring matching -- e.g. "motorrijscholen" (driving
schools) and "onderwijs" (education) both contain the literal substring
"ijs" but are obviously not seasonal ice-cream businesses. Rather than
cherry-picking one of those false positives to fake a seasonal story,
this script honestly skips that part of the demo.
"""
import random
import sys
from pathlib import Path

# Make `python scripts/seed_demo.py` work from repo root without manually
# setting PYTHONPATH (it isn't on sys.path by default for a bare script
# invocation), while also being harmless/idempotent for `python -m
# scripts.seed_demo`, where the repo root is already on sys.path.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import DEFAULT_DB_PATH, get_connection  # noqa: E402
from app.ingest import list_businesses  # noqa: E402
from app.scoring import compute_score, run_all_sources  # noqa: E402

# Defensively force UTF-8 output: some evidence detail text (e.g. Google
# Maps star ratings, "*") can include characters Windows' default console
# codepage (cp1252) can't encode, which would otherwise crash printing.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HIGH_PRIORITY_COUNT = 10
LOW_PRIORITY_COUNT = 8


# --- Local, read-only replicas of the deterministic mock/stub RNG logic ---
# These mirror app.sources.{gmaps_mock,trustpilot_mock,directory_mock,
# voice_stub,email_stub} exactly (same thresholds, same `random.Random(uidn)`
# seeding) so we can *predict* what signal each would produce for a given
# business without touching the network or the database. Used only to pick
# a good curated demo mix -- the real evidence is always (re)computed for
# real via app.scoring.run_all_sources() below. OSM is excluded since it's
# a live network call with no offline-predictable outcome.


def _predict_gmaps(uidn):
    roll = random.Random(uidn).random()
    if roll < 0.70:
        return "active"
    if roll < 0.85:
        return "inactive"
    return "silent"


def _predict_trustpilot(uidn):
    roll = random.Random(uidn).random()
    if roll < 0.40:
        return "active"
    if roll < 0.90:
        return "silent"
    return "disagreement"


def _predict_directory(uidn):
    roll = random.Random(uidn).random()
    if roll < 0.55:
        return "active"
    if roll < 0.75:
        return "disagreement"
    return "silent"


def _predict_voice(uidn):
    roll = random.Random(uidn).random()
    if roll < 0.30:
        return "active"
    if roll < 0.50:
        return "inactive"
    return "silent"


def _predict_email(uidn, has_email):
    if not has_email:
        return "silent"
    roll = random.Random(uidn).random()
    if roll < 0.30:
        return "active"
    if roll < 0.45:
        return "inactive"
    return "silent"


def _predicted_signals(business):
    uidn = business.get("uidn")
    return [
        _predict_gmaps(uidn),
        _predict_trustpilot(uidn),
        _predict_directory(uidn),
        _predict_voice(uidn),
        _predict_email(uidn, bool(business.get("email"))),
    ]


def _predicted_uncertainty(business):
    """Return (predicted_uncertainty_contribution, all_five_active)."""
    signals = _predicted_signals(business)
    disagreeing = signals.count("disagreement")
    silent = signals.count("silent")
    return disagreeing * 2 + silent, all(s == "active" for s in signals)


def _business_label(business):
    return (
        business.get("commerciele_naam")
        or business.get("maatschappelijke_naam")
        or business.get("afgekorte_naam")
        or f"UIDN {business.get('uidn')}"
    )


def pick_curated_businesses(db_path=DEFAULT_DB_PATH):
    """Return a curated list of business dicts telling a good demo story."""
    businesses = list_businesses(db_path=db_path)
    scored = [(b, *_predicted_uncertainty(b)) for b in businesses]

    high_pool = sorted(
        (item for item in scored if item[1] > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    high_priority = [item[0] for item in high_pool[:HIGH_PRIORITY_COUNT]]

    low_pool = [item[0] for item in scored if item[2]]  # all five predicted 'active'
    low_priority = low_pool[:LOW_PRIORITY_COUNT]

    seen = set()
    curated = []
    for business in high_priority + low_priority:
        if business["uidn"] not in seen:
            seen.add(business["uidn"])
            curated.append(business)
    return curated


def _clear_existing_evidence(uidns, db_path=DEFAULT_DB_PATH):
    """Delete any prior evidence rows for `uidns` (append-only table, no upsert).

    Run before re-scoring the curated set so re-running this script is
    truly idempotent (stable priority scores) instead of accumulating
    duplicate evidence and inflating uncertainty_score on every run.
    """
    if not uidns:
        return
    conn = get_connection(db_path)
    try:
        placeholders = ", ".join("?" for _ in uidns)
        conn.execute(
            f"DELETE FROM evidence WHERE business_uidn IN ({placeholders})",
            tuple(uidns),
        )
        conn.commit()
    finally:
        conn.close()


def main():
    curated = pick_curated_businesses()
    print(f"Seeding {len(curated)} curated businesses into {DEFAULT_DB_PATH} ...")
    print(
        "(Note: OSM lookups hit the real Overpass network API for each business; "
        "each call may take up to ~10s if that API is unreachable from this network.)"
    )
    print()

    _clear_existing_evidence([b["uidn"] for b in curated])

    results = []
    for business in curated:
        uidn = business["uidn"]
        label = _business_label(business)
        run_all_sources(business, db_path=DEFAULT_DB_PATH)
        score = compute_score(uidn, db_path=DEFAULT_DB_PATH)
        results.append((label, score["priority_score"]))
        print(f"  scored '{label}' (uidn={uidn}) -> priority_score={score['priority_score']}")

    results.sort(key=lambda item: item[1], reverse=True)

    print()
    print("=" * 62)
    print(f"{'Business':<45}{'Priority score':>17}")
    print("-" * 62)
    for label, priority in results:
        print(f"{label[:44]:<45}{priority:>17}")
    print("=" * 62)


if __name__ == "__main__":
    main()
