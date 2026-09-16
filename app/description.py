"""Plain-language Dutch business description generation.

Officers need every business to have a short, plausible description of
what it does, even when the only data on file is a KBO/RSZ/BTW register
row. ``generate_description`` builds one deterministically from a
business's own fields (no randomness, no external calls). This is meant
to read like real municipal-register copy, not a hackathon placeholder.

Public API:
    generate_description(business: dict) -> str
    backfill_missing_descriptions(db_path=None) -> int
    set_description(uidn, text, db_path=None) -> None
"""

from app.db import get_connection

GENERIC_FALLBACK = "Onderneming actief op dit adres. Activiteit nog niet nader vastgesteld."


def _business_name(business: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return "Deze onderneming"


def _entity_type_phrase(business: dict) -> str:
    entity_type = business.get("entity_type")
    if entity_type == "enterprise":
        return "een onderneming"
    if entity_type == "establishment":
        return "een vestiging"
    return "een onderneming"


def generate_description(business: dict) -> str:
    """Return a deterministic, plain, one-to-two-sentence Dutch description.

    Built from ``omschrijving_hoofdact_rsz``/``omschrijving_hoofdact_btw``
    (whichever is present, RSZ preferred) plus the business name and
    ``entity_type``. Falls back to a generic sentence when neither NACE
    description is available.
    """
    business = business or {}
    name = _business_name(business)
    activity = business.get("omschrijving_hoofdact_rsz") or business.get("omschrijving_hoofdact_btw")

    if not activity:
        return GENERIC_FALLBACK

    activity = activity.strip().rstrip(".")
    entity_phrase = _entity_type_phrase(business)
    return f"{name} is {entity_phrase} actief in: {activity}."


def backfill_missing_descriptions(db_path: str = None) -> int:
    """Set ``description`` for every business where it is currently NULL.

    Never overwrites a description that is already set (whether set by
    an officer or by a future search-confirmation flow). Returns the
    count of rows updated.
    """
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM businesses WHERE description IS NULL"
        ).fetchall()
        updated = 0
        for row in rows:
            business = dict(row)
            description = generate_description(business)
            conn.execute(
                "UPDATE businesses SET description = ? WHERE uidn = ?",
                (description, business["uidn"]),
            )
            updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def set_description(uidn, text: str, db_path: str = None) -> None:
    """Unconditionally set ``description`` for the business with ``uidn``.

    This is the explicit officer-edit path: unlike
    ``backfill_missing_descriptions``, it always overwrites.
    """
    conn = get_connection(db_path) if db_path else get_connection()
    try:
        conn.execute(
            "UPDATE businesses SET description = ? WHERE uidn = ?",
            (text, uidn),
        )
        conn.commit()
    finally:
        conn.close()
