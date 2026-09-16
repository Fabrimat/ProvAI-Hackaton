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
from app.sources import (
    address_crosscheck,
    directory_mock,
    email_stub,
    gmaps_mock,
    mailbox_mock,
    neighbor_check,
    osm_source,
    trustpilot_mock,
    voice_stub,
)

# Freshness bucket boundaries (days since the most recent evidence row's
# created_at, i.e. how recently WE last checked -- distinct from the
# Google Maps review-recency signal used in compute_reliability_report).
FRESHNESS_FRESH_MAX_DAYS = 30
FRESHNESS_AGING_MAX_DAYS = 180

# Google Maps review-recency thresholds used by compute_reliability_report's
# trust verdict (review recency is the single most important signal, per
# explicit product direction).
REVIEW_RECENT_MAX_DAYS = 30
REVIEW_STALE_MIN_DAYS = 730

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


def run_all_sources(
    business: dict, db_path: str = None, on_progress=None, include_mailbox: bool = True
) -> list:
    """Run all evidence sources against ``business``, in sequence.

    Order: Google Maps, Trustpilot, Infobel (phone directory), OSM,
    voice call, email, internal mailbox search (only if
    ``include_mailbox`` is True), neighbor check, address cross-check.
    Returns the list of ``{'signal', 'detail', ...}`` results -- each
    source has already logged its own evidence row by the time this
    returns (address_crosscheck logs only when it finds a conflict, see
    its own docstring). This is the function the UI calls for "run
    verification on this business".

    ``on_progress``, if given, is called as
    ``on_progress(source_name, index, total)`` immediately BEFORE running
    each source (``index`` starting at 0, ``total`` the actual number of
    sources run this call -- 8 or 9 depending on ``include_mailbox``).
    """
    steps = [
        ("Google Maps", lambda: gmaps_mock.check(business, db_path)),
        ("Trustpilot", lambda: trustpilot_mock.check(business, db_path)),
        ("Infobel / bedrijvengids", lambda: directory_mock.check(business, db_path)),
        ("OpenStreetMap", lambda: osm_source.check(business, db_path)),
        ("AI voice check", lambda: voice_stub.call(business, db_path)),
        ("E-mail check", lambda: email_stub.check(business, db_path)),
    ]
    if include_mailbox:
        steps.append(("Internal mailbox", lambda: mailbox_mock.check(business, db_path)))
    steps.append(("Neighbor check", lambda: neighbor_check.check(business, db_path)))
    steps.append(("Address cross-check", lambda: address_crosscheck.check(business, db_path)))

    total = len(steps)
    results = []
    for index, (source_name, run_step) in enumerate(steps):
        if on_progress:
            on_progress(source_name, index, total)
        results.append(run_step())
    return results


def dedupe_evidence(db_path: str = None) -> int:
    """Collapse duplicate (business_uidn, source) evidence rows to the latest.

    One-time-safe, idempotent cleanup for a database that already
    accumulated duplicate evidence rows from before the delete-then-insert
    fix existed in every source module. For each (business_uidn, source)
    pair, keeps only the row with the highest ``id`` (the most recent
    insert) and deletes the rest. Safe to call on every app startup: a
    no-op once the database is already deduped. Returns the number of
    rows deleted.
    """
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        cursor = conn.execute(
            """
            DELETE FROM evidence
            WHERE id NOT IN (
                SELECT MAX(id) FROM evidence GROUP BY business_uidn, source
            )
            """
        )
        conn.commit()
        return cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0
    finally:
        conn.close()


def _business_display_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


def _compute_freshness(evidence_rows: list) -> str:
    """'fresh' / 'aging' / 'stale' based on the most recent evidence created_at.

    Distinct from the Google Maps review-recency signal: this is about
    how recently WE last checked this business, not when its last public
    review was posted. 'stale' also covers "no evidence at all yet".
    """
    dates = [_parse_date(e.get("created_at")) for e in evidence_rows]
    dates = [d for d in dates if d is not None]
    if not dates:
        return "stale"
    most_recent = max(dates)
    age_days = (datetime.now(timezone.utc) - most_recent).days
    if age_days <= FRESHNESS_FRESH_MAX_DAYS:
        return "fresh"
    if age_days <= FRESHNESS_AGING_MAX_DAYS:
        return "aging"
    return "stale"


def compute_reliability_report(business_uidn, db_path: str = None) -> dict:
    """Compute the officer-facing trust/reliability verdict for one business.

    Combines the business's evidence rows,
    ``gmaps_mock.get_review_recency_days`` and a live (not stored)
    ``address_crosscheck.check(..., log=False)`` into one clear verdict.
    Google Maps review recency is the single most important signal per
    explicit product direction: it wins over an address conflict, not the
    other way round.

    Returns:
        {
            "status": "active" | "inactive" | "unknown",
            "trust": "trusted" | "needs_verification",
            "freshness": "fresh" | "aging" | "stale",
            "reason": "<one clear, human-readable sentence>",
            "address_note": "<one sentence, or None>",
        }
    """
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        business = _fetch_business(conn, business_uidn)
        business.setdefault("uidn", business_uidn)
        evidence_rows = _fetch_evidence(conn, business_uidn)
    finally:
        conn.close()

    active_count = sum(1 for e in evidence_rows if e.get("signal") == "active")
    inactive_count = sum(1 for e in evidence_rows if e.get("signal") == "inactive")
    disagreement_count = sum(1 for e in evidence_rows if e.get("signal") == "disagreement")
    silent_count = sum(1 for e in evidence_rows if e.get("signal") == "silent")

    days_since_last_review = gmaps_mock.get_review_recency_days(business)

    if days_since_last_review is not None and days_since_last_review <= REVIEW_RECENT_MAX_DAYS:
        trust = "trusted"
        reason = (
            f"A Google Maps review from {days_since_last_review} days ago strongly suggests "
            "this business is active."
        )
    elif days_since_last_review is not None and days_since_last_review > REVIEW_STALE_MIN_DAYS:
        trust = "needs_verification"
        years = days_since_last_review // 365
        reason = f"No Google Maps review in over {years} years."
    elif not evidence_rows:
        trust = "needs_verification"
        reason = "Nothing has been checked yet for this business."
    elif disagreement_count > 0 or silent_count > active_count:
        trust = "needs_verification"
        reason = "Evidence sources disagree or are largely silent; activity is not confirmed."
    else:
        trust = "trusted"
        reason = "A majority of evidence sources confirm this business is active."

    conflict = address_crosscheck.check(business, db_path, log=False)
    address_note = None
    if conflict.get("signal") == "disagreement":
        related_uidn = conflict.get("related_uidn")
        other_name = "een nieuwere onderneming"
        if related_uidn is not None:
            conn2 = get_connection(db_path) if db_path else get_connection()
            try:
                related_business = _fetch_business(conn2, related_uidn)
            finally:
                conn2.close()
            if related_business:
                other_name = _business_display_name(related_business)

        if trust == "needs_verification":
            reason = (
                f"No recent activity confirmed, and a newer business, '{other_name}', is now "
                "registered at this same address. Recommend verifying closure."
            )
        else:  # trust == "trusted": a recent review wins, never downgrade it
            address_note = (
                "Note: a newer business is also registered at this same address; the "
                "registered address on file may be outdated."
            )

    if active_count > inactive_count:
        status = "active"
    elif inactive_count > active_count:
        status = "inactive"
    else:
        status = "unknown"

    freshness = _compute_freshness(evidence_rows)

    return {
        "status": status,
        "trust": trust,
        "freshness": freshness,
        "reason": reason,
        "address_note": address_note,
    }
