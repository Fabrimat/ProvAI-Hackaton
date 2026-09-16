"""Stub for the automated email reach-out channel (Priority 2, action plan).

No real email is sent. Logs whether an email address is even on file
for the business and, if so, deterministically simulates a reply
outcome (or lack of one) so the demo can show the full send/log
mechanism described in ``docs/plans/challenge1-action-plan.md``.
"""
import random
from datetime import datetime, timezone

from app.db import get_connection

SOURCE_NAME = "email"

OUTCOMES = (
    ("replied_active", 0.30),
    ("replied_closed", 0.15),
    ("no_reply", 0.55),
)


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


def _business_email(business: dict):
    return business.get("email") or business.get("Email")


def _pick_outcome(rng: random.Random) -> str:
    roll = rng.random()
    cumulative = 0.0
    for outcome, weight in OUTCOMES:
        cumulative += weight
        if roll < cumulative:
            return outcome
    return OUTCOMES[-1][0]


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
    """Simulate one email reach-out attempt and log the outcome."""
    business = business or {}
    uidn = business.get("uidn")
    name = _business_name(business)
    email = _business_email(business)

    if not email:
        signal = "silent"
        detail = "No email on file -- reach-out not possible via this channel"
        _log_evidence(uidn, signal, detail, db_path)
        return {"signal": signal, "detail": detail}

    rng = random.Random(uidn)
    outcome = _pick_outcome(rng)

    if outcome == "replied_active":
        signal = "active"
        detail = f"Reach-out email sent to {email} regarding '{name}'; reply received confirming the business is still active."
    elif outcome == "replied_closed":
        signal = "inactive"
        detail = f"Reach-out email sent to {email} regarding '{name}'; reply received confirming the business has closed."
    else:
        signal = "silent"
        detail = f"Reach-out email sent to {email} regarding '{name}'; no reply received within the observation window."

    _log_evidence(uidn, signal, detail, db_path)
    return {"signal": signal, "detail": detail}
