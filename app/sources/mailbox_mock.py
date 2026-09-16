"""Internal-mailbox search evidence source (mock only -- no external API).

Simulates searching internal employee mailboxes for a mention of the
business. There is no real external API for "search our own employees'
mailboxes", so unlike ``gmaps_mock.py``/``trustpilot_mock.py`` there is no
real-API adapter path here, only the deterministic mock -- mirrors the
style of ``app.sources.voice_stub``.

Deterministic per ``business['uidn']``: roughly 40% chance of a "hit" (an
email thread mentioning the business, naming a plausible fabricated
contact person and quoting a one-line snippet suggesting recent activity
-- signal 'active'), else a "no mention found" miss (signal 'silent').
"""
import random
from datetime import datetime, timezone

from app.db import get_connection

SOURCE_NAME = "internal_mailbox"

HIT_CUTOFF = 0.40

FIRST_NAMES = ("Els", "Bart", "Karin", "Tom", "Sofie", "Wim", "Nele", "Peter", "An", "Dirk")
LAST_NAMES = ("Peeters", "Janssens", "Maes", "Jacobs", "Willems", "Goossens", "Wouters", "De Smet")

SNIPPETS = (
    "nog even langsgeweest deze week, alles leek gewoon open",
    "hebben gisteren nog telefonisch contact gehad, geen probleem",
    "kwam de zaak vorige week nog tegen, deur stond open",
    "collega zag de zaak nog draaien tijdens een bezoek ter plaatse",
    "hadden vorige maand nog een mailwisseling met hen lopen",
)


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


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
    """Simulate an internal-mailbox search for mentions of ``business``."""
    business = business or {}
    uidn = business.get("uidn")
    name = _business_name(business)
    rng = random.Random(uidn)
    roll = rng.random()

    if roll < HIT_CUTOFF:
        contact = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        snippet = rng.choice(SNIPPETS)
        signal = "active"
        detail = (
            f"Internal mailbox search: found an e-mail thread mentioning '{name}', "
            f"contact person {contact}. Quoted snippet: \"{snippet}\"."
        )
    else:
        signal = "silent"
        detail = f"Internal mailbox search: no mention of '{name}' found in any employee mailbox."

    _log_evidence(uidn, signal, detail, db_path)
    return {"signal": signal, "detail": detail}
