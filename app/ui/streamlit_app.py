"""Officer-facing Streamlit dashboard for the PROV-AI Schoten verification tool.

Entrypoint (see repo root ``docs/plans`` for design intent):

    streamlit run app/ui/streamlit_app.py --server.port=8501 --server.address=0.0.0.0

All officer-visible text (labels, buttons, headers, messages) is in Dutch,
per agent.md Source 6 ("Keep officer-facing answers and interface text in
Dutch"). Code, comments and docstrings are in English.

Three views, navigable from the sidebar:
    1. Triage-werklijst -- ranked worklist of businesses by priority_score.
    2. Dossier           -- full case file for one selected business.
    3. Ontdekkingslijst  -- minimal placeholder + best-effort OSM demo.
"""
import difflib
import html
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# Ensure the repo root is on sys.path so `app.*` imports work regardless of
# the working directory Streamlit was launched from.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import scoring, seasonal  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.ingest import get_business, list_businesses  # noqa: E402
from app.ui import freshness_view  # noqa: E402

DB_PATH = str(REPO_ROOT / "data" / "provai.db")

NAV_OPTIONS = ["Triage-werklijst", "Dossier", "Ontdekkingslijst", "Wat is er veranderd?"]

STATUS_LABELS = {
    None: "Nog te controleren",
    "pending": "Nog te controleren",
    "confirmed_active": "Bevestigd: actief",
    "confirmed_inactive": "Bevestigd: inactief",
}

SIGNAL_COLORS = {
    "active": "#2e7d32",       # green
    "inactive": "#c62828",     # red
    "disagreement": "#ef6c00",  # orange
    "silent": "#757575",       # grey
}

SIGNAL_LABELS_NL = {
    "active": "actief",
    "inactive": "inactief",
    "disagreement": "tegenstrijdig",
    "silent": "geen resultaat",
}

# Best-effort OSM discovery demo settings (view 3).
DISCOVERY_RADIUS_METERS = 300
DISCOVERY_MAX_RESULTS = 15
DISCOVERY_NAME_MATCH_RATIO = 0.6
DISCOVERY_TIMEOUT_SECONDS = 12
SCHOTEN_FALLBACK_CENTER = (51.2503, 4.5008)

# "Hoge prioriteit" cutoff for the stats banner. Chosen by inspecting the
# real priority_score distribution on the 20 businesses already verified in
# this dataset (scores: 1,1,1,2,3,4,4,6,7,10,14,14,14,14,14,21,21,28,28,48)
# -- 15 sits just above the ~75th percentile (Q3 interpolates to ~15.8), so
# ">15" tracks "top quartile" without being a knife-edge on a common value
# (14 is very common; 15 avoids splitting that cluster).
HIGH_PRIORITY_THRESHOLD = 15

# Safety cap for the map layer; 1000 points is fine for st.map/pydeck but a
# cap keeps this robust if the dataset grows well beyond that.
MAP_MAX_POINTS = 1000

# Map marker colors, reusing the same palette as SIGNAL_COLORS below so the
# map and the evidence rows read consistently across the app.
MAP_COLOR_HIGH = "#c62828"       # red   -- top tercile of priority_score
MAP_COLOR_MEDIUM = "#ef6c00"     # orange -- middle tercile
MAP_COLOR_LOW = "#2e7d32"        # green -- bottom tercile
MAP_COLOR_UNCHECKED = "#757575"  # grey  -- no score yet

MAP_LEGEND_LABELS = {
    "high": "Hoge prioriteit",
    "medium": "Gemiddelde prioriteit",
    "low": "Lage prioriteit",
    "unchecked": "Nog niet gecontroleerd",
}

# Curated demo scenario: ~18 real UIDNs from this dataset, picked for a good
# demo story rather than at random:
#   - 12 businesses with NULL omschrijving_hoofdact_rsz/btw (sparse NACE
#     data). These are the businesses most likely to produce a noisy mix of
#     "active"/"silent"/"disagreement" signals across the 6 mock sources,
#     because several sources (directory, trustpilot) key part of their mock
#     roll off business fields that are also sparse for this group -- good
#     material for showing the triage scorer's uncertainty component.
#   - 6 "ordinary" businesses that DO have a populated NACE description
#     (voetzorg, eetgelegenheid, reiniging, detailhandel, onderwijs,
#     autoherstel), for contrast against the sparse-data group.
#   Note on the seasonal dampener (app/seasonal.py SECTOR_PRIORS keywords
#   ijssalon/ijs/camping/seizoen/strand/kerst/terras/foor): grepping this
#   dataset's 60 distinct NACE descriptions found no genuine match. The one
#   substring hit ("ijs" inside "rijscholen" -- driving schools) is a false
#   positive of seasonal.py's naive substring match, not a real seasonal
#   business, so it is deliberately NOT included here -- it would make the
#   demo show a nonsensical "ice-cream sector" dampener reason attached to a
#   driving school. Per the brief, picking normally is the right call when
#   no genuine match exists in the data.
CURATED_DEMO_UIDNS = [
    10075242,  # CONSTRUCTIEWERKHUIS J. CLAESSENS -- sparse NACE
    9995062,   # R. Fiscalini / Ron Fiscalini -- sparse NACE
    10092383,  # Roel Brand -- sparse NACE
    10166529,  # DOKTER MICHEL BOEVE -- sparse NACE
    5787694,   # HUIDEVETTER -- sparse NACE
    10132210,  # ROOFER -- sparse NACE
    7023207,   # Dennenweelde -- sparse NACE
    10085521,  # BRECHTSEBAAN -- sparse NACE
    6649409,   # Ski High -- sparse NACE
    5744553,   # IMMOZET -- sparse NACE
    10057966,  # BM Polish -- sparse NACE
    10159176,  # Petra Cosemans fotografie -- sparse NACE
    10270991,  # Het Voetenhuys -- voetzorg (populated NACE)
    10525199,  # Mario & Cindy -- eetgelegenheid (populated NACE)
    10441648,  # LDM Cleaning -- reiniging (populated NACE)
    10478068,  # 't Kroontje -- detailhandel kranten (populated NACE)
    10052022,  # Sint-Michielscollege-Schoten -- onderwijs (populated NACE)
    10073061,  # Dnoub, Ibrahim -- autoherstel (populated NACE)
]


# --------------------------------------------------------------------------
# Small formatting helpers (defensive: everything is .get()'d, dataset has
# many null fields).
# --------------------------------------------------------------------------

def business_name(b: dict) -> str:
    b = b or {}
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "zoeknaam"):
        value = b.get(key)
        if value:
            return value
    uidn = b.get("uidn")
    return f"Onderneming {uidn}" if uidn is not None else "Onbekend bedrijf"


def format_address(b: dict) -> str:
    b = b or {}
    straat = b.get("kbo_straat") or ""
    huisnr = b.get("kbo_huisnr") or ""
    postcode = b.get("kbo_postcode") or ""
    gemeente = b.get("kbo_gemeente") or ""
    straat_huisnr = f"{straat} {huisnr}".strip()
    rest = " ".join(p for p in (postcode, gemeente) if p)
    parts = [p for p in (straat_huisnr, rest) if p]
    return ", ".join(parts) if parts else "Adres onbekend"


def format_date(value) -> str:
    if not value:
        return "onbekend"
    text = str(value)[:10]
    return text if text else "onbekend"


# --------------------------------------------------------------------------
# Data access (thin wrappers around app.db / app.ingest / app.scoring so the
# UI never writes raw SQL for things it doesn't own, except `status` writes,
# per the brief -- app.db has no helper for that table).
# --------------------------------------------------------------------------

@st.cache_data
def cached_list_businesses(db_path: str) -> list:
    return list_businesses(db_path)


@st.cache_data
def load_worklist(db_path: str) -> list:
    """One row per business, joined with its latest score and status."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT b.uidn, b.maatschappelijke_naam, b.commerciele_naam, b.afgekorte_naam,
                   b.zoeknaam, b.kbo_straat, b.kbo_huisnr, b.kbo_postcode, b.kbo_gemeente,
                   b.omschrijving_hoofdact_rsz, b.omschrijving_hoofdact_btw,
                   s.priority_score, s.uncertainty_score, s.impact_score, s.updated_at,
                   stat.review_status
            FROM businesses b
            LEFT JOIN scores s ON s.business_uidn = b.uidn
            LEFT JOIN status stat ON stat.business_uidn = b.uidn
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_evidence(business_uidn, db_path: str) -> list:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM evidence WHERE business_uidn = ? ORDER BY created_at DESC",
            (business_uidn,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_score(business_uidn, db_path: str):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM scores WHERE business_uidn = ?", (business_uidn,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_status_row(business_uidn, db_path: str):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM status WHERE business_uidn = ?", (business_uidn,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_status(business_uidn, review_status: str, note, db_path: str) -> None:
    """Write a confirm/reject decision directly to the `status` table.

    app.db has no helper for this table (by design, per the brief), so the
    UI writes the SQL itself. Column order matches app.db's schema:
    (business_uidn, review_status, updated_at, note).
    """
    conn = get_connection(db_path)
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO status (business_uidn, review_status, updated_at, note) "
            "VALUES (?, ?, ?, ?)",
            (business_uidn, review_status, now, note),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Stats header banner (shown at the top of every view).
# --------------------------------------------------------------------------

def get_stats(db_path: str) -> dict:
    """Pure query helper: counts backing the stats banner.

    Kept side-effect-free and Streamlit-free so it can be unit-tested
    directly against a sqlite3 connection.
    """
    conn = get_connection(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM businesses").fetchone()[0]
        checked = conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        high_priority = conn.execute(
            "SELECT COUNT(*) FROM scores WHERE priority_score > ?",
            (HIGH_PRIORITY_THRESHOLD,),
        ).fetchone()[0]
        confirmed = conn.execute("SELECT COUNT(*) FROM status").fetchone()[0]
        return {
            "total": total,
            "checked": checked,
            "high_priority": high_priority,
            "confirmed": confirmed,
        }
    finally:
        conn.close()


def render_stats_header(db_path: str) -> None:
    stats = get_stats(db_path)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totaal aantal bedrijven", stats["total"])
    c2.metric("Aantal gecontroleerd", stats["checked"])
    c3.metric("Hoge prioriteit", stats["high_priority"])
    c4.metric("Bevestigd door ambtenaar", stats["confirmed"])


# --------------------------------------------------------------------------
# Map view (businesses with known coordinates, color-coded by priority).
# --------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> list:
    hex_color = hex_color.lstrip("#")
    return [int(hex_color[i : i + 2], 16) for i in (0, 2, 4)]


def load_map_rows(db_path: str) -> list:
    """One row per business with non-null coordinates, joined with its score.

    Pure query helper (no Streamlit) so it can be unit-tested directly.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT b.uidn, b.maatschappelijke_naam, b.commerciele_naam, b.afgekorte_naam,
                   b.zoeknaam, b.latitude, b.longitude, s.priority_score
            FROM businesses b
            LEFT JOIN scores s ON s.business_uidn = b.uidn
            WHERE b.latitude IS NOT NULL AND b.longitude IS NOT NULL
            """
        ).fetchall()
        return [dict(r) for r in rows][:MAP_MAX_POINTS]
    finally:
        conn.close()


def compute_priority_terciles(priority_scores: list):
    """Return (low_cutoff, high_cutoff) splitting ``priority_scores`` into
    thirds, or ``None`` if there are fewer than 3 distinct scored values
    (too little variation to usefully split into terciles).
    """
    distinct = sorted(set(priority_scores))
    if len(distinct) < 3:
        return None
    series = pd.Series(sorted(priority_scores))
    low_cutoff = series.quantile(1 / 3)
    high_cutoff = series.quantile(2 / 3)
    return low_cutoff, high_cutoff


def classify_priority(priority_score, terciles) -> str:
    """Return one of 'unchecked' / 'low' / 'medium' / 'high'."""
    if priority_score is None:
        return "unchecked"
    if terciles is None:
        # Not enough variation to split into terciles yet -- treat any
        # scored business as "medium" rather than guessing a split.
        return "medium"
    low_cutoff, high_cutoff = terciles
    if priority_score <= low_cutoff:
        return "low"
    if priority_score <= high_cutoff:
        return "medium"
    return "high"


MAP_CATEGORY_COLORS = {
    "unchecked": MAP_COLOR_UNCHECKED,
    "low": MAP_COLOR_LOW,
    "medium": MAP_COLOR_MEDIUM,
    "high": MAP_COLOR_HIGH,
}


def build_map_dataframe(rows: list) -> pd.DataFrame:
    """Turn ``load_map_rows`` output into a DataFrame ready for st.map/pydeck."""
    scored = [r["priority_score"] for r in rows if r.get("priority_score") is not None]
    terciles = compute_priority_terciles(scored)

    records = []
    for r in rows:
        category = classify_priority(r.get("priority_score"), terciles)
        records.append(
            {
                "uidn": r["uidn"],
                "lat": r["latitude"],
                "lon": r["longitude"],
                "naam": business_name(r),
                "prioriteit_label": MAP_LEGEND_LABELS[category],
                "color": _hex_to_rgb(MAP_CATEGORY_COLORS[category]),
            }
        )
    return pd.DataFrame(records)


def render_map(db_path: str) -> None:
    st.subheader("Kaart van bedrijven")
    rows = load_map_rows(db_path)
    if not rows:
        st.info("Geen locatiegegevens beschikbaar om op de kaart te tonen.")
        return

    df = build_map_dataframe(rows)
    try:
        import pydeck as pdk

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_radius=35,
            pickable=True,
        )
        view_state = pdk.ViewState(
            latitude=float(df["lat"].mean()),
            longitude=float(df["lon"].mean()),
            zoom=13,
        )
        tooltip = {"text": "{naam}\n{prioriteit_label}"}
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip))
    except Exception:  # noqa: BLE001 -- map must degrade, never crash the dashboard
        st.map(df[["lat", "lon"]])
    st.caption(
        "Rood = hoge prioriteit, oranje = gemiddelde prioriteit, groen = lage prioriteit, "
        "grijs = nog niet gecontroleerd."
    )


# --------------------------------------------------------------------------
# One-click demo scenario (curated set of real businesses).
# --------------------------------------------------------------------------

def run_demo_scenario(db_path: str, on_progress=None) -> int:
    """Run the scoring pipeline for CURATED_DEMO_UIDNS.

    Safe to call repeatedly: run_all_sources/compute_score already
    upsert/accumulate, so re-running never duplicates scores and only
    adds (harmless) extra evidence rows. Returns the number of curated
    businesses actually found and processed. ``on_progress``, if given,
    is called with a float in [0, 1] after each business (matching the
    ``st.progress(...)`` calling convention already used elsewhere in
    this file).
    """
    total = len(CURATED_DEMO_UIDNS)
    processed = 0
    for i, uidn in enumerate(CURATED_DEMO_UIDNS):
        business = get_business(uidn, db_path)
        if business:
            scoring.run_all_sources(business, db_path)
            scoring.compute_score(uidn, db_path)
            processed += 1
        if on_progress:
            on_progress((i + 1) / total)
    return processed


def render_demo_scenario_control(db_path: str) -> None:
    st.sidebar.divider()
    st.sidebar.caption("Snel een gevulde demo-omgeving tonen:")
    if st.sidebar.button("Laad demo-scenario"):
        with st.sidebar:
            with st.spinner("Demo-scenario wordt geladen..."):
                progress = st.progress(0.0)
                processed = run_demo_scenario(db_path, progress.progress)
        st.cache_data.clear()
        st.sidebar.success(f"Demo-scenario geladen — {processed} bedrijven gecontroleerd.")
        st.rerun()


# --------------------------------------------------------------------------
# Case-file paragraph (template-based, no LLM call -- see brief).
# --------------------------------------------------------------------------

def generate_case_file_text(business: dict, evidence_rows: list, dampener: dict) -> str:
    name = business_name(business)
    n = len(evidence_rows or [])
    if n == 0:
        return (
            f"Nog geen verificatie uitgevoerd voor {name}. "
            "Klik op 'Voer verificatie uit' om de bronnen te raadplegen."
        )

    active = sum(1 for e in evidence_rows if e.get("signal") == "active")
    inactive = sum(1 for e in evidence_rows if e.get("signal") == "inactive")
    disagreement = sum(1 for e in evidence_rows if e.get("signal") == "disagreement")
    silent = sum(1 for e in evidence_rows if e.get("signal") == "silent")
    last_checked = max(
        (e.get("created_at") for e in evidence_rows if e.get("created_at")), default=None
    )

    clauses = []
    if active:
        clauses.append(f"{active} van de {n} bronnen bevestigen activiteit")
    if inactive:
        clauses.append(f"{inactive} bron(nen) wijzen op sluiting")
    if silent:
        clauses.append(f"{silent} bron(nen) gaven geen resultaat")
    if disagreement:
        clauses.append(f"{disagreement} bron(nen) geven tegenstrijdige informatie")

    summary = ", ".join(clauses) if clauses else "geen van de bronnen leverde een duidelijk signaal op"
    summary = summary[0].upper() + summary[1:]
    text = f"{summary}. Laatst gecontroleerd: {format_date(last_checked)}."

    if dampener and dampener.get("dampener_factor", 1.0) < 1.0:
        # Note: app.seasonal returns `reason` in English (frozen module, not
        # ours to change) -- never interpolate it into officer-facing Dutch
        # text. Show a generic Dutch sentence here; the raw English reason is
        # surfaced separately as a labeled debug caption in the Dossier view.
        text += (
            " Prioriteit verlaagd — vermoedelijk seizoensgebonden sluiting op basis van "
            "sector of eerdere meldingen."
        )

    return text


def render_evidence_row(e: dict) -> None:
    signal = e.get("signal") or "silent"
    color = SIGNAL_COLORS.get(signal, "#757575")
    label = SIGNAL_LABELS_NL.get(signal, "onbekend")
    # source/detail/created are untrusted free text (mock data today, real
    # scraped/API text once the live adapters are enabled) interpolated into
    # unsafe_allow_html=True markdown -- escape to prevent HTML/script
    # injection. color/label come from fixed whitelists above, safe as-is.
    source = html.escape(str(e.get("source") or "onbekend"))
    detail = html.escape(str(e.get("detail") or ""))
    created = html.escape(format_date(e.get("created_at")))
    st.markdown(
        f"""
        <div style="border-left: 4px solid {color}; padding: 6px 10px; margin-bottom: 6px;
                    background-color: rgba(127,127,127,0.08); border-radius: 4px;">
            <b>{source}</b> &mdash;
            <span style="color:{color}; font-weight:600;">{label}</span>
            <span style="float:right; color:#888; font-size:0.85em;">{created}</span><br/>
            <span style="font-size:0.9em;">{detail}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# View 1 -- Triage-werklijst
# --------------------------------------------------------------------------

def view_triage_worklist(db_path: str) -> None:
    st.header("Triage-werklijst")
    st.caption(
        "Bedrijven gesorteerd op prioriteit — hoe hoger de score, hoe dringender een "
        "controle nodig is."
    )

    render_stats_header(db_path)
    st.divider()
    render_map(db_path)
    st.divider()

    rows = load_worklist(db_path)
    if not rows:
        st.info("Geen bedrijven gevonden in de database.")
        return

    table_rows = []
    for r in rows:
        table_rows.append(
            {
                "UIDN": r["uidn"],
                "Naam": business_name(r),
                "Straat": r.get("kbo_straat") or "",
                "Adres": format_address(r),
                "NACE-omschrijving": r.get("omschrijving_hoofdact_rsz")
                or r.get("omschrijving_hoofdact_btw")
                or "",
                "Prioriteit": r.get("priority_score"),
                "Status": STATUS_LABELS.get(r.get("review_status"), STATUS_LABELS[None]),
            }
        )
    df = pd.DataFrame(table_rows)

    checked = df[df["Prioriteit"].notna()].sort_values("Prioriteit", ascending=False)
    unchecked = df[df["Prioriteit"].isna()]

    st.subheader(f"Gecontroleerd, op prioriteit ({len(checked)})")
    if checked.empty:
        st.info("Nog geen enkel bedrijf verificeerd. Zie hieronder om te starten.")
    else:
        st.dataframe(
            checked.drop(columns=["UIDN"]),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander(f"Nog te controleren ({len(unchecked)})"):
        st.dataframe(
            unchecked.drop(columns=["UIDN", "Prioriteit"]),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("Dossier openen")
    options = {
        f"{business_name(r)} — {format_address(r)} (UIDN {r['uidn']})": r["uidn"] for r in rows
    }
    sorted_labels = sorted(options.keys())
    label = st.selectbox("Kies een bedrijf om het dossier te openen", sorted_labels)
    if st.button("Open dossier"):
        st.session_state["selected_uidn"] = options[label]
        # Cannot write "nav" directly here: the sidebar radio widget bound to
        # key="nav" has already been instantiated earlier in this script run
        # (main() creates it before dispatching to this view), and Streamlit
        # raises StreamlitAPIException if a widget-bound session_state key is
        # reassigned after that widget already exists in the current run.
        # Stash the target view and let main() apply it BEFORE the radio
        # widget is (re-)created on the next run.
        st.session_state["pending_nav"] = "Dossier"
        st.rerun()

    st.divider()
    st.subheader("Verificatie uitvoeren")
    st.caption(
        "Om de demo snel te houden wordt verificatie niet automatisch voor alle "
        f"{len(unchecked)} nog te controleren bedrijven uitgevoerd. Kies hieronder hoeveel "
        "bedrijven nu geverifieerd worden, of open een dossier hierboven om één bedrijf "
        "tegelijk te verifiëren."
    )
    max_batch = max(1, min(50, len(unchecked)))
    batch_size = st.number_input(
        "Aantal te verifiëren bedrijven",
        min_value=1,
        max_value=max_batch,
        value=min(5, max_batch),
        step=1,
        disabled=unchecked.empty,
    )
    if st.button("Verificatie uitvoeren", disabled=unchecked.empty):
        candidate_uidns = unchecked["UIDN"].tolist()[: int(batch_size)]
        progress = st.progress(0.0)
        for i, uidn in enumerate(candidate_uidns):
            business = get_business(uidn, db_path)
            if business:
                scoring.run_all_sources(business, db_path)
                scoring.compute_score(uidn, db_path)
            progress.progress((i + 1) / len(candidate_uidns))
        st.cache_data.clear()
        st.success(f"Verificatie uitgevoerd voor {len(candidate_uidns)} bedrijven.")
        st.rerun()


# --------------------------------------------------------------------------
# View 2 -- Dossier (Case File)
# --------------------------------------------------------------------------

def view_dossier(db_path: str) -> None:
    st.header("Dossier")
    render_stats_header(db_path)
    st.divider()

    businesses = cached_list_businesses(db_path)
    if not businesses:
        st.info("Geen bedrijven gevonden in de database.")
        return

    options = {f"{business_name(b)} (UIDN {b['uidn']})": b["uidn"] for b in businesses}
    sorted_labels = sorted(options.keys())

    default_uidn = st.session_state.get("selected_uidn")
    default_label = next(
        (label for label, uidn in options.items() if uidn == default_uidn), None
    )
    default_index = sorted_labels.index(default_label) if default_label in sorted_labels else 0

    label = st.selectbox("Kies een bedrijf", sorted_labels, index=default_index)
    uidn = options[label]
    st.session_state["selected_uidn"] = uidn

    business = get_business(uidn, db_path)
    if not business:
        st.error("Bedrijf niet gevonden.")
        return

    st.subheader(business_name(business))
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Naam:** {business_name(business)}")
        st.markdown(f"**Adres:** {format_address(business)}")
        st.markdown(f"**Ondernemingsnummer:** {business.get('ondernemingsnr') or 'onbekend'}")
    with col2:
        entity_type = business.get("entity_type")
        type_label = {
            "enterprise": "Onderneming",
            "establishment": "Vestiging",
        }.get(entity_type, "onbekend")
        st.markdown(f"**Type:** {type_label}")
        nace = (
            business.get("omschrijving_hoofdact_rsz")
            or business.get("omschrijving_hoofdact_btw")
            or "onbekend"
        )
        st.markdown(f"**NACE-activiteit:** {nace}")
        st.markdown(f"**Ingeschreven sinds:** {format_date(business.get('datum_inschrijving'))}")

    st.divider()
    status_row = get_status_row(uidn, db_path)
    current_status = status_row.get("review_status") if status_row else None
    st.markdown(f"### Huidige status: {STATUS_LABELS.get(current_status, STATUS_LABELS[None])}")
    if status_row and status_row.get("note"):
        st.caption(f"Notitie: {status_row['note']}")
    if status_row and status_row.get("updated_at"):
        st.caption(f"Laatst bijgewerkt: {format_date(status_row['updated_at'])}")

    st.divider()
    st.subheader("Verificatie")
    if st.button("Voer verificatie uit"):
        with st.spinner("Bronnen worden geraadpleegd..."):
            scoring.run_all_sources(business, db_path)
            scoring.compute_score(uidn, db_path)
        st.cache_data.clear()
        st.success("Verificatie voltooid.")
        st.rerun()

    evidence_rows = get_evidence(uidn, db_path)
    score = get_score(uidn, db_path)
    dampener = seasonal.seasonal_dampener(business, evidence_rows, date.today().month)

    st.divider()
    st.subheader("Case-dossier")
    st.write(generate_case_file_text(business, evidence_rows, dampener))
    if dampener and dampener.get("dampener_factor", 1.0) < 1.0 and dampener.get("reason"):
        # app.seasonal's `reason` field is English (module is frozen, not ours
        # to change) -- shown only as clearly-labeled internal/debug detail,
        # never as officer-facing Dutch text.
        st.caption(f"(interne detail, EN: {dampener['reason']})")

    st.divider()
    st.subheader("Prioriteitsscore")
    if score:
        c1, c2, c3 = st.columns(3)
        c1.metric("Onzekerheid", score.get("uncertainty_score"))
        c2.metric("Impact", score.get("impact_score"))
        c3.metric("Prioriteit (totaal)", score.get("priority_score"))
        st.caption(f"Laatst berekend: {format_date(score.get('updated_at'))}")
    else:
        st.info("Nog geen score berekend. Voer eerst een verificatie uit.")

    st.divider()
    st.subheader("Bewijs per bron")
    if not evidence_rows:
        st.info("Nog geen bewijs verzameld voor dit bedrijf.")
    else:
        for e in evidence_rows:
            render_evidence_row(e)

    st.divider()
    st.subheader("Beoordeling")
    note = st.text_input("Notitie (optioneel)")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Bevestigen: actief"):
            set_status(uidn, "confirmed_active", note or None, db_path)
            st.cache_data.clear()
            st.success("Status bijgewerkt: Bevestigd: actief")
            st.rerun()
    with col_b:
        if st.button("Bevestigen: inactief"):
            set_status(uidn, "confirmed_inactive", note or None, db_path)
            st.cache_data.clear()
            st.success("Status bijgewerkt: Bevestigd: inactief")
            st.rerun()


# --------------------------------------------------------------------------
# View 3 -- Ontdekkingslijst (Discovery Queue) -- minimal placeholder + demo
# --------------------------------------------------------------------------

def _schoten_center(db_path: str):
    """Best-effort centroid of the register's own coordinates, else a fallback."""
    try:
        conn = get_connection(db_path)
        try:
            row = conn.execute(
                "SELECT AVG(latitude) AS lat, AVG(longitude) AS lon FROM businesses "
                "WHERE latitude BETWEEN 51.0 AND 51.5 AND longitude BETWEEN 4.0 AND 5.0"
            ).fetchone()
            if row and row["lat"] and row["lon"]:
                return row["lat"], row["lon"]
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 -- discovery demo must never crash the app
        pass
    return SCHOTEN_FALLBACK_CENTER


def run_discovery_sample(db_path: str) -> list:
    """Fetch a few real OSM POIs near Schoten's center; return unmatched ones.

    Best-effort: capped result count, short timeout, name fuzzy-match
    against every known business name. Not a full discovery pipeline --
    see the honest placeholder text in ``view_discovery_queue``.
    """
    lat, lon = _schoten_center(db_path)
    query = (
        f"[out:json][timeout:{DISCOVERY_TIMEOUT_SECONDS}];"
        f'(node["shop"](around:{DISCOVERY_RADIUS_METERS},{lat},{lon});'
        f'node["office"](around:{DISCOVERY_RADIUS_METERS},{lat},{lon});'
        f'node["amenity"~"restaurant|cafe|bar|fast_food|pharmacy|bank"]'
        f"(around:{DISCOVERY_RADIUS_METERS},{lat},{lon});"
        f");out body;"
    )
    response = requests.post(
        "https://overpass-api.de/api/interpreter",
        data={"data": query},
        timeout=DISCOVERY_TIMEOUT_SECONDS,
        headers={"User-Agent": "ProvAI-Schoten-Verification/1.0"},
    )
    response.raise_for_status()
    elements = response.json().get("elements", []) or []

    known_names = [business_name(b) for b in cached_list_businesses(db_path)]

    unmatched = []
    for element in elements:
        tags = element.get("tags") or {}
        name = tags.get("name")
        if not name:
            continue
        best_ratio = 0.0
        name_lower = name.lower()
        for known in known_names:
            known_lower = (known or "").lower()
            if not known_lower:
                continue
            ratio = difflib.SequenceMatcher(None, name_lower, known_lower).ratio()
            if name_lower in known_lower or known_lower in name_lower:
                ratio = max(ratio, 0.9)
            if ratio > best_ratio:
                best_ratio = ratio
        if best_ratio < DISCOVERY_NAME_MATCH_RATIO:
            category = tags.get("shop") or tags.get("office") or tags.get("amenity") or "onbekend"
            unmatched.append({"name": name, "category": category, "best_ratio": best_ratio})
        if len(unmatched) >= DISCOVERY_MAX_RESULTS:
            break
    return unmatched


def view_discovery_queue(db_path: str) -> None:
    st.header("Ontdekkingslijst")
    render_stats_header(db_path)
    st.divider()
    st.write(
        "Deze functie toont bedrijven die via OpenStreetMap gevonden zijn maar niet in het "
        "KBO-register staan — nog in ontwikkeling."
    )
    st.caption(
        "Onderstaande demonstratie haalt een beperkt aantal echte OSM-punten op rond het "
        "centrum van Schoten en toont welke namen niet overeenkomen met een bedrijf in het "
        "register. Dit is een best-effort demonstratie, geen volledige implementatie."
    )

    if st.button("Voer OSM-steekproef uit rond centrum Schoten"):
        with st.spinner("OpenStreetMap wordt geraadpleegd..."):
            try:
                results = run_discovery_sample(db_path)
            except Exception as exc:  # noqa: BLE001 -- demo must degrade, not crash
                st.error(f"De steekproef kon niet worden uitgevoerd: {exc}")
                results = None

        if results is not None:
            if not results:
                st.info("Geen mogelijk onbekende locaties gevonden in deze steekproef.")
            else:
                st.write(f"{len(results)} mogelijk onbekende locatie(s) gevonden:")
                for r in results:
                    st.markdown(
                        f"- **{r['name']}** ({r['category']}) — geen duidelijk overeenkomstig "
                        f"bedrijf in het register (beste gelijkenis: {r['best_ratio']:.0%})"
                    )


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="PROV-AI — Lokale economie Schoten", layout="wide")
    st.sidebar.title("PROV-AI")
    st.sidebar.caption("Verificatietool lokale economie — gemeente Schoten")

    if "pending_nav" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("pending_nav")
    if "nav" not in st.session_state:
        st.session_state["nav"] = NAV_OPTIONS[0]
    nav = st.sidebar.radio("Navigatie", NAV_OPTIONS, key="nav")
    render_demo_scenario_control(DB_PATH)

    if nav == "Triage-werklijst":
        view_triage_worklist(DB_PATH)
    elif nav == "Dossier":
        view_dossier(DB_PATH)
    elif nav == "Ontdekkingslijst":
        view_discovery_queue(DB_PATH)
    else:
        freshness_view.render(DB_PATH)


if __name__ == "__main__":
    main()
