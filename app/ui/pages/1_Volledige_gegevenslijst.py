"""Volledige gegevenslijst -- full sortable/filterable data table of businesses.

Streamlit multipage-app page (auto-discovered from the ``pages/`` directory
next to ``app/ui/streamlit_app.py``, no wiring needed). Complements the
curated Triage-werklijst view with a raw, comprehensive table: every column
of the ``businesses`` table plus the latest ``scores``/``status`` info,
sortable natively by ``st.dataframe`` and filterable through the widgets
above the table.

All officer-visible text is in Dutch, per agent.md Source 6. Code, comments
and docstrings are in English.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure the repo root is on sys.path so `app.*` imports work regardless of
# the working directory Streamlit was launched from (same pattern as
# app/ui/streamlit_app.py).
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import get_connection  # noqa: E402

DB_PATH = str(REPO_ROOT / "data" / "provai.db")

st.set_page_config(page_title="Volledige gegevenslijst", layout="wide")

ENTITY_TYPE_LABELS_NL = {
    "enterprise": "Onderneming",
    "establishment": "Vestiging",
}

STATUS_LABELS_NL = {
    None: "Nog te controleren",
    "pending": "Nog te controleren",
    "confirmed_active": "Bevestigd: actief",
    "confirmed_inactive": "Bevestigd: inactief",
}

# Column order + Dutch header labels for every ``businesses`` field, plus the
# joined ``scores``/``status`` fields appended at the end. Kept as an
# explicit ordered mapping so the resulting DataFrame has stable, readable
# headers regardless of the SQL SELECT's column order.
COLUMN_LABELS_NL = {
    "uidn": "UIDN",
    "oidn": "OIDN",
    "ondernemingsnr": "Ondernemingsnummer",
    "maatschappelijke_naam": "Officiële naam",
    "commerciele_naam": "Commerciële naam",
    "afgekorte_naam": "Afgekorte naam",
    "zoeknaam": "Zoeknaam",
    "ondernemingsnr_maatsch_zetel": "Ondernemingsnr maatschappelijke zetel",
    "entity_type_label": "Type entiteit",
    "type_onderneming": "Type onderneming",
    "rechtsvorm": "Rechtsvorm",
    "rechtstoestand": "Rechtstoestand",
    "kbo_straat": "KBO-straat",
    "kbo_huisnr": "KBO-huisnummer",
    "kbo_busnr": "KBO-busnummer",
    "kbo_postcode": "KBO-postcode",
    "kbo_gemeente": "KBO-gemeente",
    "ar_straat": "Vestigingsstraat",
    "ar_huisnr": "Vestigingshuisnummer",
    "ar_busnr": "Vestigingsbusnummer",
    "ar_postcode": "Vestigingspostcode",
    "nace_hoofdact_btw": "NACE-code (BTW)",
    "nace_versie_btw": "NACE-versie (BTW)",
    "omschrijving_hoofdact_btw": "NACE-omschrijving (BTW)",
    "aantal_hoofdact_btw": "Aantal hoofdactiviteiten (BTW)",
    "nace_hoofdact_rsz": "NACE-code (RSZ)",
    "nace_versie_rsz": "NACE-versie (RSZ)",
    "omschrijving_hoofdact_rsz": "NACE-omschrijving (RSZ)",
    "aantal_hoofdact_rsz": "Aantal hoofdactiviteiten (RSZ)",
    "personeelsklasse": "Personeelsklasse",
    "datum_inschrijving": "Datum inschrijving",
    "startdatum": "Startdatum",
    "datum_stopzetting": "Datum stopzetting",
    "reden_stopzetting": "Reden stopzetting",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "telefoonnummer": "Telefoonnummer",
    "email": "E-mail",
    "kbo_niscode": "KBO-NIS-code",
    "jaarrek_url_nbb": "Jaarrekening-URL (NBB)",
    "parent_ondernemingsnr": "Ondernemingsnr moederbedrijf",
    "uncertainty_score": "Onzekerheidsscore",
    "impact_score": "Impactscore",
    "priority_score": "Prioriteitsscore",
    "score_updated_at": "Score laatst bijgewerkt",
    "review_status_label": "Beoordelingsstatus",
    "status_updated_at": "Status laatst bijgewerkt",
    "status_note": "Notitie",
}

# Columns that should be treated/sorted as numbers, not text.
NUMERIC_COLUMNS = [
    "uidn",
    "oidn",
    "aantal_hoofdact_btw",
    "aantal_hoofdact_rsz",
    "latitude",
    "longitude",
    "uncertainty_score",
    "impact_score",
    "priority_score",
]

# Name fields searched by the free-text filter.
NAME_SEARCH_COLUMNS = [
    "commerciele_naam",
    "maatschappelijke_naam",
    "afgekorte_naam",
    "zoeknaam",
]


@st.cache_data
def load_full_dataset(db_path: str) -> list:
    """One row per business, joined with its latest score and status.

    Pure query helper (no Streamlit calls besides the cache decorator) so
    the SQL and result shape can be verified directly against a sqlite3
    connection outside of Streamlit.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT b.*,
                   s.uncertainty_score AS uncertainty_score,
                   s.impact_score AS impact_score,
                   s.priority_score AS priority_score,
                   s.updated_at AS score_updated_at,
                   stat.review_status AS review_status,
                   stat.updated_at AS status_updated_at,
                   stat.note AS status_note
            FROM businesses b
            LEFT JOIN scores s ON s.business_uidn = b.uidn
            LEFT JOIN status stat ON stat.business_uidn = b.uidn
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def build_dataframe(rows: list) -> pd.DataFrame:
    """Turn raw joined rows into a display-ready DataFrame with sensible dtypes.

    Defensive throughout: input rows may have ``None`` in almost any field
    (heavy nulls in this dataset), so every derived/translated column falls
    back to a safe default rather than raising.
    """
    if not rows:
        return pd.DataFrame(columns=list(COLUMN_LABELS_NL.values()))

    df = pd.DataFrame.from_records(rows)

    # Derived/translated columns -- computed before dtype coercion so they
    # participate in the same column-rename step below.
    df["entity_type_label"] = df.get("entity_type").map(
        lambda v: ENTITY_TYPE_LABELS_NL.get(v, v if v else "onbekend")
    )
    df["review_status_label"] = df.get("review_status").map(
        lambda v: STATUS_LABELS_NL.get(v, STATUS_LABELS_NL[None])
    )

    # Ensure every expected column exists even if a join produced no rows
    # for it (defensive against future schema drift).
    for col in COLUMN_LABELS_NL:
        if col not in df.columns:
            df[col] = pd.NA

    # Numeric coercion: turn any stray string/None into a real numeric dtype
    # (NaN for missing) so st.dataframe's native click-to-sort orders these
    # columns numerically instead of lexicographically.
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    ordered_cols = list(COLUMN_LABELS_NL.keys())
    df = df[ordered_cols].rename(columns=COLUMN_LABELS_NL)
    return df


def distinct_non_null(rows: list, key: str) -> list:
    """Sorted distinct non-null/non-empty values for ``key`` across ``rows``."""
    values = {r.get(key) for r in rows if r.get(key)}
    return sorted(values)


def apply_filters(
    df: pd.DataFrame,
    search_text: str,
    gemeenten: list,
    entity_types: list,
    rechtstoestanden: list,
    only_known_nace: bool,
) -> pd.DataFrame:
    """Apply all filter widgets to ``df`` via plain pandas boolean masking.

    Kept Streamlit-free so it can be unit-tested directly against a
    DataFrame built by ``build_dataframe``.
    """
    mask = pd.Series(True, index=df.index)

    if search_text:
        needle = search_text.strip().lower()
        if needle:
            name_cols = [
                COLUMN_LABELS_NL[c] for c in NAME_SEARCH_COLUMNS if COLUMN_LABELS_NL[c] in df.columns
            ]
            search_mask = pd.Series(False, index=df.index)
            for col in name_cols:
                search_mask |= df[col].fillna("").astype(str).str.lower().str.contains(
                    needle, regex=False
                )
            mask &= search_mask

    if gemeenten:
        mask &= df[COLUMN_LABELS_NL["kbo_gemeente"]].isin(gemeenten)

    if entity_types:
        mask &= df[COLUMN_LABELS_NL["entity_type_label"]].isin(entity_types)

    if rechtstoestanden:
        mask &= df[COLUMN_LABELS_NL["rechtstoestand"]].isin(rechtstoestanden)

    if only_known_nace:
        nace_btw = df[COLUMN_LABELS_NL["nace_hoofdact_btw"]]
        nace_rsz = df[COLUMN_LABELS_NL["nace_hoofdact_rsz"]]
        mask &= nace_btw.notna() | nace_rsz.notna()

    return df[mask]


def main() -> None:
    st.header("Volledige gegevenslijst")
    st.caption(
        "Alle beschikbare gegevens per bedrijf, sorteerbaar door op een kolomkop te klikken "
        "en filterbaar met de onderstaande filters."
    )

    raw_rows = load_full_dataset(DB_PATH)
    if not raw_rows:
        st.info("Geen bedrijven gevonden in de database.")
        return

    df_all = build_dataframe(raw_rows)

    with st.expander("Filters", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            search_text = st.text_input(
                "Zoek op naam",
                placeholder="Bv. een deel van de commerciële, officiële, afgekorte of zoeknaam",
            )
            gemeente_options = distinct_non_null(raw_rows, "kbo_gemeente")
            gemeenten = st.multiselect("Gemeente", gemeente_options)
        with col2:
            entity_type_options = sorted(
                {
                    ENTITY_TYPE_LABELS_NL.get(v, v)
                    for v in distinct_non_null(raw_rows, "entity_type")
                }
            )
            entity_types = st.multiselect("Type entiteit", entity_type_options)
            rechtstoestand_options = distinct_non_null(raw_rows, "rechtstoestand")
            rechtstoestanden = st.multiselect("Rechtstoestand", rechtstoestand_options)

        only_known_nace = st.checkbox("Alleen bedrijven met bekende NACE-code")

    df_filtered = apply_filters(
        df_all,
        search_text=search_text,
        gemeenten=gemeenten,
        entity_types=entity_types,
        rechtstoestanden=rechtstoestanden,
        only_known_nace=only_known_nace,
    )

    st.write(f"{len(df_filtered)} van de {len(df_all)} bedrijven getoond")

    st.dataframe(df_filtered, use_container_width=True, hide_index=True)


main()
