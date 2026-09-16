"""Ask-the-neighbors phone canvas evidence source.

The neighbor-finding step is grounded in REAL data: it queries the real
``businesses`` table for other real businesses sharing the same
``kbo_straat``/``kbo_gemeente`` (excluding the target itself and its own
enterprise/establishment pair, same exclusion rule as
``app.sources.address_crosscheck``). Up to 3 of them are picked
deterministically, seeded on the target's ``uidn``. The "contacted them,
they said X" outcome per picked neighbor is a mock (there is no real API
for phoning neighboring businesses), drawn from that same seeded RNG so
the whole check is reproducible.

No real-API adapter path exists here, unlike ``gmaps_mock.py`` -- like
``mailbox_mock.py``, this is pure mock (for the contact outcome) grounded
in real data (for who gets "contacted").
"""
import random
from datetime import datetime, timezone

from app.db import get_connection

SOURCE_NAME = "neighbor_check"

MAX_NEIGHBORS = 3

# Cumulative-probability outcome table for one simulated neighbor contact.
OUTCOMES = (
    ("confirms_active", 0.55),
    ("doesnt_recognize", 0.35),
    ("suggests_closed", 0.10),
)


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
    treated as neighbors/conflicts.
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


def _find_real_neighbors(conn, business: dict) -> list:
    straat = business.get("kbo_straat")
    gemeente = business.get("kbo_gemeente")
    uidn = business.get("uidn")
    if not straat or not gemeente:
        return []
    rows = conn.execute(
        "SELECT * FROM businesses WHERE kbo_straat = ? AND kbo_gemeente = ? AND uidn != ?",
        (straat, gemeente, uidn),
    ).fetchall()
    return [dict(row) for row in rows if not _is_same_enterprise_pair(business, dict(row))]


def _pick_outcome(rng: random.Random) -> str:
    roll = rng.random()
    cumulative = 0.0
    for outcome, weight in OUTCOMES:
        cumulative += weight
        if roll < cumulative:
            return outcome
    return OUTCOMES[-1][0]


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
    """Simulate an "ask the neighbors" canvas for ``business`` and log it.

    Finds up to 3 real neighboring businesses (same street + municipality,
    excluding the target's own enterprise/establishment pair), picks them
    deterministically seeded on ``business['uidn']``, and simulates one
    contact outcome per pick using that same seeded RNG. Combines the
    outcomes into one overall signal: 'active' if a majority confirm
    activity, 'disagreement' if a majority suggest closure, 'silent'
    otherwise (including "no real neighbors to check").
    """
    business = business or {}
    uidn = business.get("uidn")

    conn = get_connection(db_path) if db_path else get_connection()
    try:
        neighbors = _find_real_neighbors(conn, business)
    finally:
        conn.close()

    rng = random.Random(uidn)

    if not neighbors:
        signal = "silent"
        detail = "Neighbor check: no other real businesses on record at this address to contact."
        _log_evidence(uidn, signal, detail, db_path)
        return {"signal": signal, "detail": detail}

    sample_size = min(MAX_NEIGHBORS, len(neighbors))
    picked = rng.sample(neighbors, sample_size)

    results = [(neighbor, _pick_outcome(rng)) for neighbor in picked]

    total = len(results)
    confirms = sum(1 for _, outcome in results if outcome == "confirms_active")
    closures = sum(1 for _, outcome in results if outcome == "suggests_closed")

    if confirms > total / 2:
        signal = "active"
    elif closures > total / 2:
        signal = "disagreement"
    else:
        signal = "silent"

    lines = []
    for neighbor, outcome in results:
        neighbor_name = _business_name(neighbor)
        if outcome == "confirms_active":
            lines.append(f"'{neighbor_name}' confirmed the business is still active there")
        elif outcome == "suggests_closed":
            lines.append(f"'{neighbor_name}' suggested the business may have closed")
        else:
            lines.append(f"'{neighbor_name}' did not recognize the business name")

    detail = "Neighbor check: contacted " + "; ".join(lines) + "."

    _log_evidence(uidn, signal, detail, db_path)
    return {"signal": signal, "detail": detail}
