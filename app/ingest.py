"""CSV/GeoJSON ingestion for the Schoten KBO business register.

Reads the register CSV and the companion GeoJSON (matched on ``UIDN``),
normalizes blank-looking values (``""`` / ``" "``) to ``None``, classifies
each row as an ``'enterprise'`` (legal entity: ``Type_onderneming``,
``Rechtsvorm`` and ``Rechtstoestand`` all non-blank) or an
``'establishment'`` (vestigingseenheid: those three fields blank), and
upserts the merged result into the ``businesses`` table defined in
``app.db``.

Dates are stored verbatim as the original ISO-8601 strings (see
``app.db`` module docstring for the full set of conventions used here).

Stdlib only: no pandas, no third-party dependencies.
"""

import csv
import json

from app.db import DEFAULT_DB_PATH, get_connection, init_db

DEFAULT_CSV_PATH = "schoten-kbo-1000-2026-09-07.csv"
DEFAULT_GEOJSON_PATH = "schoten-kbo-1000-2026-09-07.geojson"

# Columns of app.db's `businesses` table, in insert order.
COLUMNS = [
    "uidn",
    "oidn",
    "ondernemingsnr",
    "maatschappelijke_naam",
    "commerciele_naam",
    "afgekorte_naam",
    "ondernemingsnr_maatsch_zetel",
    "type_onderneming",
    "rechtsvorm",
    "rechtstoestand",
    "kbo_straat",
    "kbo_huisnr",
    "kbo_busnr",
    "kbo_postcode",
    "kbo_gemeente",
    "ar_straat",
    "ar_huisnr",
    "ar_busnr",
    "ar_postcode",
    "nace_hoofdact_btw",
    "nace_versie_btw",
    "omschrijving_hoofdact_btw",
    "aantal_hoofdact_btw",
    "nace_hoofdact_rsz",
    "nace_versie_rsz",
    "omschrijving_hoofdact_rsz",
    "aantal_hoofdact_rsz",
    "personeelsklasse",
    "datum_inschrijving",
    "startdatum",
    "longitude",
    "latitude",
    "telefoonnummer",
    "email",
    "datum_stopzetting",
    "reden_stopzetting",
    "zoeknaam",
    "kbo_niscode",
    "jaarrek_url_nbb",
    "entity_type",
    "parent_ondernemingsnr",
]

# GeoJSON-only properties merged in on top of the CSV row, keyed by UIDN.
GEOJSON_EXTRA_FIELDS = {
    "Telefoonnummer": "telefoonnummer",
    "Email": "email",
    "Datum_stopzetting": "datum_stopzetting",
    "Reden_stopzetting": "reden_stopzetting",
    "Zoeknaam": "zoeknaam",
    "KBO_NISCODE": "kbo_niscode",
    "JAARREK_URL_NBB": "jaarrek_url_nbb",
}


def _blank_to_none(value):
    """Normalize blank-looking values (None, "", " ") to None; strip others."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value


def _to_int(value):
    value = _blank_to_none(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value):
    value = _blank_to_none(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_geojson_properties(geojson_path):
    """Return a dict mapping UIDN (int) -> feature properties dict."""
    with open(geojson_path, encoding="utf-8") as f:
        data = json.load(f)
    by_uidn = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        uidn = _to_int(props.get("UIDN"))
        if uidn is not None:
            by_uidn[uidn] = props
    return by_uidn


def _build_row(csv_row, geojson_props):
    """Merge one CSV row + its matching GeoJSON properties into an insert tuple."""
    type_onderneming = _blank_to_none(csv_row.get("Type_onderneming"))
    rechtsvorm = _blank_to_none(csv_row.get("Rechtsvorm"))
    rechtstoestand = _blank_to_none(csv_row.get("Rechtstoestand"))

    is_enterprise = bool(type_onderneming and rechtsvorm and rechtstoestand)
    entity_type = "enterprise" if is_enterprise else "establishment"

    ondernemingsnr_maatsch_zetel = _blank_to_none(csv_row.get("Ondernemingsnr_maatsch_zetel"))
    parent_ondernemingsnr = None if is_enterprise else ondernemingsnr_maatsch_zetel

    values = {
        "uidn": _to_int(csv_row.get("UIDN")),
        "oidn": _to_int(csv_row.get("OIDN")),
        "ondernemingsnr": _blank_to_none(csv_row.get("Ondernemingsnr")),
        "maatschappelijke_naam": _blank_to_none(csv_row.get("Maatschappelijke_naam")),
        "commerciele_naam": _blank_to_none(csv_row.get("Commerciele_naam")),
        "afgekorte_naam": _blank_to_none(csv_row.get("Afgekorte_naam")),
        "ondernemingsnr_maatsch_zetel": ondernemingsnr_maatsch_zetel,
        "type_onderneming": type_onderneming,
        "rechtsvorm": rechtsvorm,
        "rechtstoestand": rechtstoestand,
        "kbo_straat": _blank_to_none(csv_row.get("KBO_Straat")),
        "kbo_huisnr": _blank_to_none(csv_row.get("KBO_Huisnr")),
        "kbo_busnr": _blank_to_none(csv_row.get("KBO_Busnr")),
        "kbo_postcode": _blank_to_none(csv_row.get("KBO_Postcode")),
        "kbo_gemeente": _blank_to_none(csv_row.get("KBO_Gemeente")),
        "ar_straat": _blank_to_none(csv_row.get("AR_straat")),
        "ar_huisnr": _blank_to_none(csv_row.get("AR_huisnr")),
        "ar_busnr": _blank_to_none(csv_row.get("AR_busnr")),
        "ar_postcode": _blank_to_none(csv_row.get("AR_postcode")),
        "nace_hoofdact_btw": _blank_to_none(csv_row.get("NACE_hoofdact_BTW")),
        "nace_versie_btw": _blank_to_none(csv_row.get("NACE_versie_BTW")),
        "omschrijving_hoofdact_btw": _blank_to_none(csv_row.get("Omschrijving_hoofdact_BTW")),
        "aantal_hoofdact_btw": _to_int(csv_row.get("Aantal_hoofdact_BTW")),
        "nace_hoofdact_rsz": _blank_to_none(csv_row.get("NACE_hoofdact_RSZ")),
        "nace_versie_rsz": _blank_to_none(csv_row.get("NACE_Versie_RSZ")),
        "omschrijving_hoofdact_rsz": _blank_to_none(csv_row.get("Omschrijving_hoofdact_RSZ")),
        "aantal_hoofdact_rsz": _to_int(csv_row.get("Aantal_Hoofdact_RSZ")),
        "personeelsklasse": _blank_to_none(csv_row.get("Personeelsklasse")),
        "datum_inschrijving": _blank_to_none(csv_row.get("Datum_inschrijving")),
        "startdatum": _blank_to_none(csv_row.get("Startdatum")),
        "longitude": _to_float(csv_row.get("longitude")),
        "latitude": _to_float(csv_row.get("latitude")),
        "telefoonnummer": None,
        "email": None,
        "datum_stopzetting": None,
        "reden_stopzetting": None,
        "zoeknaam": None,
        "kbo_niscode": None,
        "jaarrek_url_nbb": None,
        "entity_type": entity_type,
        "parent_ondernemingsnr": parent_ondernemingsnr,
    }

    for geojson_key, column in GEOJSON_EXTRA_FIELDS.items():
        if geojson_props is not None and geojson_key in geojson_props:
            values[column] = _blank_to_none(geojson_props.get(geojson_key))

    return tuple(values[col] for col in COLUMNS)


def ingest_csv_and_geojson(
    csv_path: str = DEFAULT_CSV_PATH,
    geojson_path: str = DEFAULT_GEOJSON_PATH,
    db_path: str = DEFAULT_DB_PATH,
) -> int:
    """Read the CSV + GeoJSON, merge on UIDN, upsert into `businesses`.

    Safe to re-run: uses INSERT OR REPLACE keyed on UIDN, so re-running
    against the same source files does not create duplicate rows.

    Returns the number of rows upserted.
    """
    geojson_by_uidn = _load_geojson_properties(geojson_path)

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)

    rows_to_insert = []
    for csv_row in csv_rows:
        uidn = _to_int(csv_row.get("UIDN"))
        geojson_props = geojson_by_uidn.get(uidn)
        rows_to_insert.append(_build_row(csv_row, geojson_props))

    placeholders = ", ".join("?" for _ in COLUMNS)
    columns_sql = ", ".join(COLUMNS)
    sql = f"INSERT OR REPLACE INTO businesses ({columns_sql}) VALUES ({placeholders})"

    conn = get_connection(db_path)
    try:
        conn.executemany(sql, rows_to_insert)
        conn.commit()
    finally:
        conn.close()

    return len(rows_to_insert)


def list_businesses(db_path: str = DEFAULT_DB_PATH) -> list:
    """Return all rows of `businesses` as a list of dicts."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM businesses")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_business(uidn: int, db_path: str = DEFAULT_DB_PATH):
    """Return one business as a dict, or None if not found."""
    conn = get_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM businesses WHERE uidn = ?", (uidn,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


if __name__ == "__main__":
    init_db(DEFAULT_DB_PATH)
    count = ingest_csv_and_geojson(DEFAULT_CSV_PATH, DEFAULT_GEOJSON_PATH, DEFAULT_DB_PATH)

    conn = get_connection(DEFAULT_DB_PATH)
    try:
        total = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
        enterprises = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE entity_type = 'enterprise'"
        ).fetchone()[0]
        establishments = conn.execute(
            "SELECT COUNT(*) FROM businesses WHERE entity_type = 'establishment'"
        ).fetchone()[0]
    finally:
        conn.close()

    print(f"Ingested/upserted {count} rows from source files.")
    print(f"businesses table now has {total} rows total: "
          f"{enterprises} enterprises, {establishments} establishments.")
