"""SQLite data layer for the PROV-AI Schoten business-register verification tool.

Conventions used throughout this module (and by ``app.ingest``):

- Primary key: ``UIDN`` (integer) is used as the primary key of the
  ``businesses`` table. It is unique per CSV/GeoJSON row (both an
  "enterprise" row and an "establishment" row get their own UIDN), unlike
  ``Ondernemingsnr`` which can repeat across an enterprise and its
  establishments in some registers. All other tables reference
  ``business_uidn`` as a foreign key back to ``businesses.uidn``.
- Dates: all date/datetime fields from the source data (e.g.
  ``Datum_inschrijving``, ``Startdatum``, ``Datum_stopzetting``) are stored
  verbatim as their original ISO-8601 string (e.g.
  ``"2003-01-18T00:00:00Z"``), i.e. as TEXT, not parsed into Python
  ``date``/``datetime`` objects. They still sort and compare correctly as
  strings because ISO-8601 is lexicographically ordered. ``updated_at`` /
  ``created_at`` columns written by this codebase use
  ``datetime.now(timezone.utc).isoformat()``.
- Blanks: source CSV/GeoJSON fields that are empty or a single space
  (``""`` or ``" "``) are normalized to SQL ``NULL`` (Python ``None``) at
  ingestion time, never stored as literal whitespace strings.
- ``row_factory`` is set to ``sqlite3.Row`` so callers get dict-like access
  (``row["column"]``) as well as ``dict(row)`` conversion.
"""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = "data/provai.db"


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Return a sqlite3 connection to ``db_path`` with dict-like row access.

    Ensures the parent directory of ``db_path`` exists before connecting.
    """
    path = Path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS businesses (
        uidn INTEGER PRIMARY KEY,
        oidn INTEGER,
        ondernemingsnr TEXT,
        maatschappelijke_naam TEXT,
        commerciele_naam TEXT,
        afgekorte_naam TEXT,
        ondernemingsnr_maatsch_zetel TEXT,
        type_onderneming TEXT,
        rechtsvorm TEXT,
        rechtstoestand TEXT,
        kbo_straat TEXT,
        kbo_huisnr TEXT,
        kbo_busnr TEXT,
        kbo_postcode TEXT,
        kbo_gemeente TEXT,
        ar_straat TEXT,
        ar_huisnr TEXT,
        ar_busnr TEXT,
        ar_postcode TEXT,
        nace_hoofdact_btw TEXT,
        nace_versie_btw TEXT,
        omschrijving_hoofdact_btw TEXT,
        aantal_hoofdact_btw INTEGER,
        nace_hoofdact_rsz TEXT,
        nace_versie_rsz TEXT,
        omschrijving_hoofdact_rsz TEXT,
        aantal_hoofdact_rsz INTEGER,
        personeelsklasse TEXT,
        datum_inschrijving TEXT,
        startdatum TEXT,
        longitude REAL,
        latitude REAL,
        telefoonnummer TEXT,
        email TEXT,
        datum_stopzetting TEXT,
        reden_stopzetting TEXT,
        zoeknaam TEXT,
        kbo_niscode TEXT,
        jaarrek_url_nbb TEXT,
        entity_type TEXT NOT NULL,
        parent_ondernemingsnr TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_uidn INTEGER NOT NULL,
        source TEXT NOT NULL,
        signal TEXT,
        detail TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (business_uidn) REFERENCES businesses (uidn)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scores (
        business_uidn INTEGER PRIMARY KEY,
        uncertainty_score REAL,
        impact_score REAL,
        priority_score REAL,
        updated_at TEXT,
        FOREIGN KEY (business_uidn) REFERENCES businesses (uidn)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS status (
        business_uidn INTEGER PRIMARY KEY,
        review_status TEXT NOT NULL DEFAULT 'pending',
        updated_at TEXT,
        note TEXT,
        FOREIGN KEY (business_uidn) REFERENCES businesses (uidn)
    )
    """,
]


def _ensure_description_column(conn: sqlite3.Connection) -> None:
    """Idempotent migration: add ``businesses.description`` if missing.

    Safe to call on every startup, including against an already-populated,
    already-deployed database: checks ``PRAGMA table_info(businesses)``
    first and only runs ``ALTER TABLE`` when the column is genuinely
    absent.
    """
    columns = conn.execute("PRAGMA table_info(businesses)").fetchall()
    column_names = {row["name"] for row in columns}
    if "description" not in column_names:
        conn.execute("ALTER TABLE businesses ADD COLUMN description TEXT")


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create all tables (if missing) in the database at ``db_path``.

    Also runs idempotent schema migrations (currently: adding
    ``businesses.description`` if it doesn't already exist) so this is
    safe to call on every app startup, including against an already
    populated, already deployed database.
    """
    conn = get_connection(db_path)
    try:
        for statement in SCHEMA_STATEMENTS:
            conn.execute(statement)
        _ensure_description_column(conn)
        conn.commit()
    finally:
        conn.close()
