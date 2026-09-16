"""Triage scoring engine.

Implements, exactly, the formula from
``docs/plans/gamechanger-triage-and-briefing.md`` (Idea 1):

    uncertainty_score = (# disagreeing sources) * 2 + (# silent sources) * 1
    impact_score      = commercial_nace_signal (0 or 1) * 2
                       + street_density_bucket (0, 1, or 2)
                       + staleness_bucket (0, 1, or 2)
    priority_score    = uncertainty_score * impact_score

The weights and bucket boundaries are the plan's own placeholder values,
not a validated model -- see the source doc for the reasoning.
"""
from datetime import datetime, timezone

from app.db import get_connection
from app.sources import directory_mock, email_stub, gmaps_mock, osm_source, trustpilot_mock, voice_stub

# Staleness bucket boundaries (registration age, in years).
STALENESS_RECENT_YEARS = 2
STALENESS_OLD_YEARS = 10

# Street-density bucket boundaries (count of OTHER businesses on the same street).
DENSITY_LOW_MAX = 2   # <3 others -> bucket 0
DENSITY_MED_MAX = 8   # 3-8 others -> bucket 1, >8 -> bucket 2


def _parse_date(value):
    """Best-effort parse of the ISO-ish date strings app.db stores as TEXT."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _fetch_business(conn, business_uidn) -> dict:
    row = conn.execute("SELECT * FROM businesses WHERE uidn = ?", (business_uidn,)).fetchone()
    return dict(row) if row else {}


def _fetch_evidence(conn, business_uidn) -> list:
    rows = conn.execute(
        "SELECT * FROM evidence WHERE business_uidn = ?", (business_uidn,)
    ).fetchall()
    return [dict(row) for row in rows]


def _uncertainty_score(evidence_rows: list) -> float:
    disagreeing = sum(1 for e in evidence_rows if e.get("signal") == "disagreement")
    silent = sum(1 for e in evidence_rows if e.get("signal") == "silent")
    return disagreeing * 2 + silent * 1


def _commercial_nace_signal(business: dict) -> int:
    """1 if a known commercial NACE activity code is present, else 0."""
    has_code = business.get("nace_hoofdact_rsz") or business.get("nace_hoofdact_btw")
    return 1 if has_code else 0


def _street_density_bucket(conn, business: dict) -> int:
    """Bucket the count of OTHER businesses sharing straat+gemeente.

    Assumption: app.db's real schema uses kbo_straat/kbo_gemeente; the
    brief-suggested 'straat'/'gemeente' keys are tried as a fallback in
    case the business dict comes from a differently-shaped source.
    """
    straat = business.get("kbo_straat") or business.get("straat")
    gemeente = business.get("kbo_gemeente") or business.get("gemeente")
    uidn = business.get("uidn")
    if not straat or not gemeente:
        return 0
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM businesses "
        "WHERE kbo_straat = ? AND kbo_gemeente = ? AND uidn != ?",
        (straat, gemeente, uidn),
    ).fetchone()
    count = row["cnt"] if row else 0
    if count <= DENSITY_LOW_MAX:
        return 0
    if count <= DENSITY_MED_MAX:
        return 1
    return 2


def _staleness_bucket(business: dict) -> int:
    """Bucket registration age: <2y -> 0, 2-10y -> 1, >10y -> 2."""
    reg_date = _parse_date(business.get("datum_inschrijving")) or _parse_date(
        business.get("startdatum")
    )
    if reg_date is None:
        return 0
    age_years = (datetime.now(timezone.utc) - reg_date).days / 365.25
    if age_years < STALENESS_RECENT_YEARS:
        return 0
    if age_years <= STALENESS_OLD_YEARS:
        return 1
    return 2


def compute_score(business_uidn, db_path: str = None) -> dict:
    """Compute and persist the triage score for one business.

    Reads that business's evidence rows and business record, computes
    ``uncertainty_score``, ``impact_score`` and ``priority_score`` per the
    formula above, UPSERTs the result into the ``scores`` table, and
    returns it as a dict.
    """
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        business = _fetch_business(conn, business_uidn)
        business.setdefault("uidn", business_uidn)
        evidence_rows = _fetch_evidence(conn, business_uidn)

        uncertainty_score = _uncertainty_score(evidence_rows)
        impact_score = (
            _commercial_nace_signal(business) * 2
            + _street_density_bucket(conn, business)
            + _staleness_bucket(business)
        )
        priority_score = uncertainty_score * impact_score
        updated_at = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            INSERT INTO scores (business_uidn, uncertainty_score, impact_score, priority_score, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(business_uidn) DO UPDATE SET
                uncertainty_score = excluded.uncertainty_score,
                impact_score = excluded.impact_score,
                priority_score = excluded.priority_score,
                updated_at = excluded.updated_at
            """,
            (business_uidn, uncertainty_score, impact_score, priority_score, updated_at),
        )
        conn.commit()

        return {
            "business_uidn": business_uidn,
            "uncertainty_score": uncertainty_score,
            "impact_score": impact_score,
            "priority_score": priority_score,
            "updated_at": updated_at,
        }
    finally:
        conn.close()


def run_all_sources(business: dict, db_path: str = None) -> list:
    """Run all six evidence sources against ``business``, in sequence.

    Order: Google Maps, Trustpilot, Infobel (phone directory), OSM,
    voice call, email. Returns the list of ``{'signal', 'detail'}``
    results -- each source has already logged its own evidence row by
    the time this returns. This is the function the UI calls for "run
    verification on this business".
    """
    return [
        gmaps_mock.check(business, db_path),
        trustpilot_mock.check(business, db_path),
        directory_mock.check(business, db_path),
        osm_source.check(business, db_path),
        voice_stub.call(business, db_path),
        email_stub.check(business, db_path),
    ]
