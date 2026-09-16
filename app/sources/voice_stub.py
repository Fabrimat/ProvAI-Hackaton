"""Stub for the AI voice-agent phone reach-out (Priority 2, action plan).

No real call is placed. This simulates what the voice agent would do and
logs the simulated outcome as an evidence row -- including the
wrong-number fallback flow described in
``docs/plans/challenge1-action-plan.md`` Priority 2: when the call
reaches someone who has never heard of the business, the agent asks
whether they know an updated phone/email, and roughly half the time gets
a plausible-looking "lead" that is logged as exactly that -- a lead to
verify, never a confirmed correction.
"""
import random
from datetime import datetime, timezone

from app.db import get_connection

SOURCE_NAME = "voice_agent"

# Cumulative-probability outcome table, deterministic per business uidn.
OUTCOMES = (
    ("answered_confirmed_active", 0.30),
    ("answered_confirmed_closed", 0.20),
    ("no_answer", 0.30),
    ("wrong_number", 0.20),
)


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "deze onderneming"


def _pick_outcome(rng: random.Random) -> str:
    roll = rng.random()
    cumulative = 0.0
    for outcome, weight in OUTCOMES:
        cumulative += weight
        if roll < cumulative:
            return outcome
    return OUTCOMES[-1][0]


def _maybe_fabricated_lead(rng: random.Random):
    """~50% of the time, fabricate a plausible-looking updated contact.

    Explicitly a fake, illustrative lead -- never presented as a
    confirmed correction, only as something the officer could try.
    """
    if rng.random() >= 0.5:
        return None
    if rng.random() < 0.5:
        return f"try 03-555-{rng.randint(0, 9999):04d}"
    return f"probeer {rng.choice(['info', 'contact', 'shop', 'zaak'])}{rng.randint(1, 99)}@gmail.com"


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


def call(business: dict, db_path: str = None) -> dict:
    """Simulate one AI voice-agent reach-out call and log the outcome."""
    business = business or {}
    uidn = business.get("uidn")
    name = _business_name(business)
    rng = random.Random(uidn)
    outcome = _pick_outcome(rng)

    if outcome == "answered_confirmed_active":
        signal = "active"
        detail = f"AI voice check -- call answered, person confirmed '{name}' is still active at this address."
    elif outcome == "answered_confirmed_closed":
        signal = "inactive"
        detail = f"AI voice check -- call answered, person confirmed '{name}' has closed."
    elif outcome == "no_answer":
        signal = "silent"
        detail = f"AI voice check -- no answer after the planned call attempts for '{name}'."
    else:  # wrong_number
        lead = _maybe_fabricated_lead(rng)
        signal = "silent"  # a lead is not a confirmation
        if lead:
            detail = (
                f"AI voice check -- wrong number. Person who answered said they've never "
                f"heard of '{name}'. Follow-up asked: do you know an updated phone/email? "
                f"They provided: '{lead}' (lead to verify, not a confirmed correction)."
            )
        else:
            detail = (
                f"AI voice check -- wrong number. Person who answered said they've never "
                f"heard of '{name}'. Follow-up asked: do you know an updated phone/email? "
                "No lead was provided."
            )

    _log_evidence(uidn, signal, detail, db_path)
    return {"signal": signal, "detail": detail}
