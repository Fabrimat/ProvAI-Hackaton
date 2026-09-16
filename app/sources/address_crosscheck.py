"""Real address cross-check: "a different, newer business is now registered
at this same address" -- a strong closure signal.

Unlike every other source module in ``app.sources``, this is not mocked
at all: it is a genuine query over the real ``businesses`` table. It also
deliberately does NOT log a "nothing found" evidence row for the (large)
majority of businesses with no conflict -- see ``check()``'s docstring.
"""
from datetime import datetime, timezone

from app.db import get_connection

SOURCE_NAME = "address_crosscheck"

NO_CONFLICT_DETAIL = "No conflicting registration found at this address."

# The real source data does not use SQL NULL to mean "not stopped": every
# row in the live dataset carries this exact literal sentinel string in
# datum_stopzetting instead (confirmed against the real
# schoten-kbo-1000-2026-09-07.geojson / data/provai.db). Both a genuine
# NULL and this sentinel must be treated as "not stopped" -- comparing
# only against NULL made this whole module inert against real data.
STOPZETTING_NOT_STOPPED_SENTINEL = "1900-01-01T00:00:00Z"


def _is_stopped(value) -> bool:
    """True if ``value`` (a business's ``datum_stopzetting``) means "stopped".

    Both ``None`` and the dataset's own "not stopped" sentinel literal
    (``1900-01-01T00:00:00Z``) mean "not stopped". Anything else (a real
    date string) means the business is recorded as stopped.
    """
    if value is None:
        return False
    if value == STOPZETTING_NOT_STOPPED_SENTINEL:
        return False
    return True


def _parse_date(value):
    """Best-effort parse of the ISO-ish date strings app.db stores as TEXT.

    Mirrors ``app.scoring._parse_date`` exactly (kept local to avoid a
    cross-module dependency for one small helper; behavior must stay
    identical).
    """
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


def _registration_date(business: dict):
    return _parse_date(business.get("datum_inschrijving")) or _parse_date(business.get("startdatum"))


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


def _is_same_enterprise_pair(business: dict, other: dict) -> bool:
    """True if ``other`` is the same enterprise/establishment as ``business``.

    An enterprise and its own establishment(s) legitimately share one
    address by design (see ``app.db`` module docstring) and must never be
    flagged as a conflict.
    """
    b_ond = business.get("ondernemingsnr")
    b_parent = business.get("parent_ondernemingsnr")
    o_ond = other.get("ondernemingsnr")
    o_parent = other.get("parent_ondernemingsnr")
    if b_ond is not None and o_ond == b_ond:
        return True
    if b_ond is not None and o_parent == b_ond:
        return True
    if b_parent is not None and o_ond == b_parent:
        return True
    return False


def _same_address(business: dict, other: dict) -> bool:
    return (
        other.get("kbo_straat") == business.get("kbo_straat")
        and other.get("kbo_huisnr") == business.get("kbo_huisnr")
        and other.get("kbo_busnr") == business.get("kbo_busnr")
        and other.get("kbo_postcode") == business.get("kbo_postcode")
    )


def _find_conflicting_business(conn, business: dict):
    """Return the best-qualifying newer-business-at-same-address dict, or None.

    See ``check()``'s docstring for the full qualification rules.
    """
    if _is_stopped(business.get("datum_stopzetting")):
        return None  # this business is already known/recorded as stopped

    own_registration = _registration_date(business)
    if own_registration is None:
        return None

    straat = business.get("kbo_straat")
    postcode = business.get("kbo_postcode")
    uidn = business.get("uidn")
    if not straat or not postcode:
        return None

    rows = conn.execute(
        "SELECT * FROM businesses WHERE kbo_straat = ? AND kbo_postcode = ? AND uidn != ?",
        (straat, postcode, uidn),
    ).fetchall()

    best = None
    best_date = None
    for row in rows:
        other = dict(row)
        if _is_stopped(other.get("datum_stopzetting")):
            continue
        if not _same_address(business, other):
            continue
        if _is_same_enterprise_pair(business, other):
            continue
        other_registration = _registration_date(other)
        if other_registration is None:
            continue
        if other_registration <= own_registration:
            continue
        if best_date is None or other_registration > best_date:
            best = other
            best_date = other_registration

    return best


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


def check(business: dict, db_path: str = None, log: bool = True) -> dict:
    """Look for another real business that may have replaced ``business``
    at the same address.

    A candidate ``other`` qualifies only if ALL of the following hold:
    - ``other.uidn != business.uidn``
    - Same normalized address (kbo_straat, kbo_huisnr, kbo_busnr,
      kbo_postcode all equal, including NULL == NULL).
    - Not the same enterprise/establishment pair as ``business``.
    - ``other`` is not itself stopped, per ``_is_stopped`` (the candidate
      successor is itself still active). Note: the real dataset does not
      use SQL NULL for "not stopped" -- it uses a fixed sentinel literal
      (see ``STOPZETTING_NOT_STOPPED_SENTINEL``); ``_is_stopped`` treats
      both NULL and that sentinel as "not stopped".
    - ``other``'s registration date (datum_inschrijving, falling back to
      startdatum) is LATER than ``business``'s own registration date.
    - ``business`` is not itself stopped, per ``_is_stopped`` (nothing new
      to flag if this business is already recorded as stopped).

    If multiple candidates qualify, the one with the latest registration
    date wins.

    Returns ``{"signal": "disagreement" | None, "detail": str,
    "related_uidn": int | None}``.

    If ``log`` is True (the default) and a conflict IS found, logs it as
    an evidence row via the same delete-then-insert pattern used by every
    other source. Deliberately does NOT log anything when no conflict is
    found, regardless of ``log`` -- this source is a targeted red-flag
    check, not a general "did we get data back" check, and logging a
    neutral row for the large majority of businesses with no conflict
    would inflate their uncertainty_score with noise.

    ``log=False`` lets a UI layer re-run this same deterministic,
    real-data check purely for display without writing a duplicate
    evidence row on every page render.
    """
    business = business or {}
    uidn = business.get("uidn")

    conn = get_connection(db_path) if db_path else get_connection()
    try:
        conflict = _find_conflicting_business(conn, business)
    finally:
        conn.close()

    if conflict is None:
        return {"signal": None, "detail": NO_CONFLICT_DETAIL, "related_uidn": None}

    other_name = _business_name(conflict)
    other_registration = conflict.get("datum_inschrijving") or conflict.get("startdatum")
    detail = (
        f"A newer business, '{other_name}', has been registered at this same address "
        f"since {other_registration}."
    )
    related_uidn = conflict.get("uidn")

    if log:
        _log_evidence(uidn, "disagreement", detail, db_path)

    return {"signal": "disagreement", "detail": detail, "related_uidn": related_uidn}
