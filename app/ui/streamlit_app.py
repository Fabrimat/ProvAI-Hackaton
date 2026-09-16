"""Officer-facing Streamlit dashboard for the PROV-AI Schoten verification tool.

Entrypoint (see repo root ``docs/plans`` for design intent):

    streamlit run app/ui/streamlit_app.py --server.port=8501 --server.address=0.0.0.0

All officer-visible text (labels, buttons, headers, messages) is in Dutch,
per agent.md Source 6 ("Keep officer-facing answers and interface text in
Dutch"). Code, comments and docstrings are in English.

A sidebar language toggle (Dutch/English) is available for demo purposes on
top of the compliant Dutch interface -- Dutch remains the default on every
fresh load; English is convenience-only, not a replacement.

Views, navigable from the sidebar (Dashboard and Te verifiëren first, as the
two primary screens -- monitoring vs. acting -- the rest are secondary):
    1. Dashboard          -- read-only monitoring: stats banner, map, and a
                             pointer to the freshness view. No actions here.
    2. Te verifiëren      -- the actionable queue: ranked worklist by
                             priority_score, open-dossier control, and the
                             batch verification-run control.
    3. Dossier            -- full case file for one selected business.
    4. Ontdekkingslijst   -- minimal placeholder + best-effort OSM demo.
    5. Wat is er veranderd? -- freshness / change-detection overview.
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
from app.ui.call_animation import render_call_simulation  # noqa: E402
from app.ui.history_view import render_history  # noqa: E402

DB_PATH = str(REPO_ROOT / "data" / "provai.db")

# Primary screens (Dashboard = monitoring, Te verifiëren = acting) come
# first, per the product owner's split between "automatic-system monitoring"
# and "manual verification queue"; the rest are secondary and listed after.
NAV_OPTIONS = [
    "Dashboard",
    "Te verifiëren",
    "Dossier",
    "Ontdekkingslijst",
    "Wat is er veranderd?",
]

# Maps each canonical (untranslated) NAV_OPTIONS value to its translation key,
# used only to render a translated label in the sidebar radio's format_func --
# the underlying value stays fixed so session_state / nav comparisons
# elsewhere in this file are unaffected by the language toggle.
NAV_LABEL_KEYS = {
    "Dashboard": "nav_dashboard",
    "Te verifiëren": "nav_to_verify",
    "Dossier": "nav_dossier",
    "Ontdekkingslijst": "nav_discovery",
    "Wat is er veranderd?": "nav_freshness",
}

# Language toggle: Dutch is the compliant default (per agent.md Source 6),
# English is added on top for demo convenience. Dutch must stay index=0 so a
# fresh page load always defaults to Dutch.
LANGUAGES = {"Nederlands": "nl", "English": "en"}


# --------------------------------------------------------------------------
# Static UI string translations (NOT for dynamic/data-derived values, e.g.
# business names/addresses -- those always come from the database as-is).
# Every key must exist under both "nl" and "en"; see `t()` below.
# --------------------------------------------------------------------------

TRANSLATIONS = {
    "nl": {
        "page_title": "PROV-AI: Lokale economie Schoten",
        "sidebar_caption": "Verificatietool lokale economie, gemeente Schoten",
        "nav_label": "Navigatie",
        "nav_primary_label": "Belangrijkste taken",
        "nav_dashboard": "Dashboard",
        "nav_to_verify": "Te verifiëren",
        "nav_dossier": "Dossier",
        "nav_discovery": "Ontdekkingslijst",
        "nav_freshness": "Wat is er veranderd?",
        "status_pending": "Nog te controleren",
        "status_confirmed_active": "Bevestigd: actief",
        "status_confirmed_inactive": "Bevestigd: inactief",
        "unknown": "onbekend",
        "map_legend_high": "Hoge prioriteit",
        "map_legend_medium": "Gemiddelde prioriteit",
        "map_legend_low": "Lage prioriteit",
        "map_legend_unchecked": "Nog niet gecontroleerd",
        "entity_type_enterprise": "Onderneming",
        "entity_type_establishment": "Vestiging",
        "business_name_prefix": "Onderneming {uidn}",
        "business_name_unknown": "Onbekend bedrijf",
        "address_unknown": "Adres onbekend",
        "stat_total": "Totaal aantal bedrijven",
        "stat_checked": "Aantal gecontroleerd",
        "stat_high_priority": "Hoge prioriteit",
        "stat_confirmed": "Bevestigd door ambtenaar",
        "map_header": "Kaart van bedrijven",
        "map_no_data": "Geen locatiegegevens beschikbaar om op de kaart te tonen.",
        "map_caption_legend": (
            "Rood = hoge prioriteit, oranje = gemiddelde prioriteit, groen = lage prioriteit, "
            "grijs = nog niet gecontroleerd."
        ),
        "demo_caption": "Snel een gevulde demo-omgeving tonen:",
        "demo_button": "Laad demo-scenario",
        "demo_spinner": "Demo-scenario wordt geladen...",
        "demo_success": "Demo-scenario geladen: {n} bedrijven gecontroleerd.",
        "casefile_no_verification": (
            "Nog geen verificatie uitgevoerd voor {name}. "
            "Klik op 'Voer verificatie uit' om de bronnen te raadplegen."
        ),
        "casefile_clause_active": "{active} van de {n} bronnen bevestigen activiteit",
        "casefile_clause_inactive": "{count} bron(nen) wijzen op sluiting",
        "casefile_clause_silent": "{count} bron(nen) gaven geen resultaat",
        "casefile_clause_disagreement": "{count} bron(nen) geven tegenstrijdige informatie",
        "casefile_no_signal": "geen van de bronnen leverde een duidelijk signaal op",
        "casefile_summary": "{summary}. Laatst gecontroleerd: {date}.",
        "casefile_dampener_note": (
            " Prioriteit verlaagd, vermoedelijk seizoensgebonden sluiting op basis van "
            "sector of eerdere meldingen."
        ),
        "col_name": "Naam",
        "col_street": "Straat",
        "col_address": "Adres",
        "col_nace": "NACE-omschrijving",
        "col_priority": "Prioriteit",
        "col_status": "Status",
        "header_dashboard": "Dashboard",
        "dashboard_caption": (
            "Automatisch overzicht van het systeem: status van de dataset in één oogopslag. "
            "Geen acties op deze pagina."
        ),
        "dashboard_freshness_pointer": (
            "Bekijk 'Wat is er veranderd?' in het menu voor een overzicht van recente "
            "wijzigingen."
        ),
        "header_to_verify": "Te verifiëren",
        "to_verify_caption": (
            "Bedrijven die aandacht nodig hebben, gesorteerd op prioriteit. Dit is uw "
            "werklijst om te controleren en af te handelen."
        ),
        "no_businesses_found": "Geen bedrijven gevonden in de database.",
        "triage_checked_header": "Gecontroleerd, op prioriteit ({n})",
        "triage_no_checked": "Nog geen enkel bedrijf verificeerd. Zie hieronder om te starten.",
        "triage_unchecked_header": "Nog te controleren ({n})",
        "triage_open_dossier_header": "Dossier openen",
        "triage_select_business": "Kies een bedrijf om het dossier te openen",
        "triage_open_dossier_button": "Open dossier",
        "triage_verify_header": "Verificatie uitvoeren",
        "triage_verify_caption": (
            "Om de demo snel te houden wordt verificatie niet automatisch voor alle "
            "{n} nog te controleren bedrijven uitgevoerd. Kies hieronder hoeveel "
            "bedrijven nu geverifieerd worden, of open een dossier hierboven om één bedrijf "
            "tegelijk te verifiëren."
        ),
        "triage_batch_size_label": "Aantal te verifiëren bedrijven",
        "triage_run_verification_button": "Verificatie uitvoeren",
        "triage_verify_success": "Verificatie uitgevoerd voor {n} bedrijven.",
        "header_dossier": "Dossier",
        "dossier_select_business": "Kies een bedrijf",
        "dossier_not_found": "Bedrijf niet gevonden.",
        "dossier_label_name": "**Naam:** {value}",
        "dossier_label_address": "**Adres:** {value}",
        "dossier_label_business_number": "**Ondernemingsnummer:** {value}",
        "dossier_label_type": "**Type:** {value}",
        "dossier_label_nace": "**NACE-activiteit:** {value}",
        "dossier_label_registered_since": "**Ingeschreven sinds:** {value}",
        "dossier_current_status_header": "### Huidige status: {status}",
        "dossier_note_caption": "Notitie: {note}",
        "dossier_last_updated_caption": "Laatst bijgewerkt: {date}",
        "dossier_verification_header": "Verificatie",
        "dossier_run_verification_button": "Voer verificatie uit",
        "dossier_verification_spinner": "Bronnen worden geraadpleegd...",
        "dossier_verification_success": "Verificatie voltooid.",
        "dossier_call_simulation_button": "Simuleer telefoongesprek",
        "dossier_call_simulation_success": "Gesprek afgerond en gelogd als bewijs.",
        "dossier_case_file_header": "Case-dossier",
        "dossier_internal_debug_caption": "(interne detail, EN: {reason})",
        "dossier_score_header": "Prioriteitsscore",
        "dossier_metric_uncertainty": "Onzekerheid",
        "dossier_metric_impact": "Impact",
        "dossier_metric_priority_total": "Prioriteit (totaal)",
        "dossier_last_calculated_caption": "Laatst berekend: {date}",
        "dossier_no_score_info": "Nog geen score berekend. Voer eerst een verificatie uit.",
        "dossier_review_header": "Beoordeling",
        "dossier_note_input_label": "Notitie (optioneel)",
        "dossier_confirm_active_button": "Bevestigen: actief",
        "dossier_confirm_inactive_button": "Bevestigen: inactief",
        "dossier_status_updated": "Status bijgewerkt: {status}",
        "header_discovery": "Ontdekkingslijst",
        "discovery_intro": (
            "Deze functie toont bedrijven die via OpenStreetMap gevonden zijn maar niet in het "
            "KBO-register staan, nog in ontwikkeling."
        ),
        "discovery_caption": (
            "Onderstaande demonstratie haalt een beperkt aantal echte OSM-punten op rond het "
            "centrum van Schoten en toont welke namen niet overeenkomen met een bedrijf in het "
            "register. Dit is een best-effort demonstratie, geen volledige implementatie."
        ),
        "discovery_run_button": "Voer OSM-steekproef uit rond centrum Schoten",
        "discovery_spinner": "OpenStreetMap wordt geraadpleegd...",
        "discovery_error": "De steekproef kon niet worden uitgevoerd: {error}",
        "discovery_no_results": "Geen mogelijk onbekende locaties gevonden in deze steekproef.",
        "discovery_results_count": "{n} mogelijk onbekende locatie(s) gevonden:",
        "discovery_result_item": (
            "- **{name}** ({category}): geen duidelijk overeenkomstig bedrijf in het "
            "register (beste gelijkenis: {ratio})"
        ),
    },
    "en": {
        "page_title": "PROV-AI: Local economy Schoten",
        "sidebar_caption": "Local economy verification tool, Schoten municipality",
        "nav_label": "Navigation",
        "nav_primary_label": "Primary tasks",
        "nav_dashboard": "Dashboard",
        "nav_to_verify": "To verify",
        "nav_dossier": "Case file",
        "nav_discovery": "Discovery queue",
        "nav_freshness": "What's changed?",
        "status_pending": "Not yet checked",
        "status_confirmed_active": "Confirmed: active",
        "status_confirmed_inactive": "Confirmed: inactive",
        "unknown": "unknown",
        "map_legend_high": "High priority",
        "map_legend_medium": "Medium priority",
        "map_legend_low": "Low priority",
        "map_legend_unchecked": "Not yet checked",
        "entity_type_enterprise": "Enterprise",
        "entity_type_establishment": "Establishment",
        "business_name_prefix": "Business {uidn}",
        "business_name_unknown": "Unknown business",
        "address_unknown": "Address unknown",
        "stat_total": "Total number of businesses",
        "stat_checked": "Number checked",
        "stat_high_priority": "High priority",
        "stat_confirmed": "Confirmed by officer",
        "map_header": "Map of businesses",
        "map_no_data": "No location data available to show on the map.",
        "map_caption_legend": (
            "Red = high priority, orange = medium priority, green = low priority, "
            "grey = not yet checked."
        ),
        "demo_caption": "Quickly show a populated demo environment:",
        "demo_button": "Load demo scenario",
        "demo_spinner": "Loading demo scenario...",
        "demo_success": "Demo scenario loaded: {n} businesses checked.",
        "casefile_no_verification": (
            "No verification has been carried out yet for {name}. "
            "Click 'Run verification' to consult the sources."
        ),
        "casefile_clause_active": "{active} of {n} sources confirm activity",
        "casefile_clause_inactive": "{count} source(s) indicate closure",
        "casefile_clause_silent": "{count} source(s) gave no result",
        "casefile_clause_disagreement": "{count} source(s) give conflicting information",
        "casefile_no_signal": "none of the sources produced a clear signal",
        "casefile_summary": "{summary}. Last checked: {date}.",
        "casefile_dampener_note": (
            " Priority lowered, likely a seasonal closure based on sector or "
            "previous reports."
        ),
        "col_name": "Name",
        "col_street": "Street",
        "col_address": "Address",
        "col_nace": "NACE description",
        "col_priority": "Priority",
        "col_status": "Status",
        "header_dashboard": "Dashboard",
        "dashboard_caption": (
            "Automatic overview of the system: the state of the dataset at a glance. "
            "No actions on this page."
        ),
        "dashboard_freshness_pointer": (
            "See 'What's changed?' in the menu for an overview of recent changes."
        ),
        "header_to_verify": "To verify",
        "to_verify_caption": (
            "Businesses that need attention, sorted by priority. This is your worklist to "
            "check and act on."
        ),
        "no_businesses_found": "No businesses found in the database.",
        "triage_checked_header": "Checked, by priority ({n})",
        "triage_no_checked": "No business has been verified yet. See below to get started.",
        "triage_unchecked_header": "Still to be checked ({n})",
        "triage_open_dossier_header": "Open case file",
        "triage_select_business": "Choose a business to open its case file",
        "triage_open_dossier_button": "Open case file",
        "triage_verify_header": "Run verification",
        "triage_verify_caption": (
            "To keep the demo fast, verification is not automatically run for all "
            "{n} businesses still to be checked. Choose below how many businesses to "
            "verify now, or open a case file above to verify one business at a time."
        ),
        "triage_batch_size_label": "Number of businesses to verify",
        "triage_run_verification_button": "Run verification",
        "triage_verify_success": "Verification completed for {n} businesses.",
        "header_dossier": "Case file",
        "dossier_select_business": "Choose a business",
        "dossier_not_found": "Business not found.",
        "dossier_label_name": "**Name:** {value}",
        "dossier_label_address": "**Address:** {value}",
        "dossier_label_business_number": "**Business number:** {value}",
        "dossier_label_type": "**Type:** {value}",
        "dossier_label_nace": "**NACE activity:** {value}",
        "dossier_label_registered_since": "**Registered since:** {value}",
        "dossier_current_status_header": "### Current status: {status}",
        "dossier_note_caption": "Note: {note}",
        "dossier_last_updated_caption": "Last updated: {date}",
        "dossier_verification_header": "Verification",
        "dossier_run_verification_button": "Run verification",
        "dossier_verification_spinner": "Consulting sources...",
        "dossier_verification_success": "Verification completed.",
        "dossier_call_simulation_button": "Simulate phone call",
        "dossier_call_simulation_success": "Call completed and logged as evidence.",
        "dossier_case_file_header": "Case file",
        "dossier_internal_debug_caption": "(internal detail, EN: {reason})",
        "dossier_score_header": "Priority score",
        "dossier_metric_uncertainty": "Uncertainty",
        "dossier_metric_impact": "Impact",
        "dossier_metric_priority_total": "Priority (total)",
        "dossier_last_calculated_caption": "Last calculated: {date}",
        "dossier_no_score_info": "No score calculated yet. Run a verification first.",
        "dossier_review_header": "Review",
        "dossier_note_input_label": "Note (optional)",
        "dossier_confirm_active_button": "Confirm: active",
        "dossier_confirm_inactive_button": "Confirm: inactive",
        "dossier_status_updated": "Status updated: {status}",
        "header_discovery": "Discovery queue",
        "discovery_intro": (
            "This feature shows businesses found via OpenStreetMap that are not in the "
            "KBO register, still under development."
        ),
        "discovery_caption": (
            "The demonstration below fetches a limited number of real OSM points around "
            "the center of Schoten and shows which names do not match a business in the "
            "register. This is a best-effort demonstration, not a full implementation."
        ),
        "discovery_run_button": "Run OSM sample around Schoten center",
        "discovery_spinner": "Consulting OpenStreetMap...",
        "discovery_error": "The sample could not be run: {error}",
        "discovery_no_results": "No possibly unknown locations found in this sample.",
        "discovery_results_count": "{n} possibly unknown location(s) found:",
        "discovery_result_item": (
            "- **{name}** ({category}): no clear matching business in the register "
            "(best match: {ratio})"
        ),
    },
}


def t(key: str, lang: str, **kwargs) -> str:
    """Look up UI string ``key`` for ``lang`` and .format() any kwargs.

    Falls back to the Dutch ("nl") value if the key is missing for the
    requested language -- defensive only, should not happen given
    TRANSLATIONS is kept complete for both languages, but a missing
    translation must never crash the dashboard.
    """
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS["nl"])
    text = lang_dict.get(key, TRANSLATIONS["nl"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


def status_labels(lang: str) -> dict:
    return {
        None: t("status_pending", lang),
        "pending": t("status_pending", lang),
        "confirmed_active": t("status_confirmed_active", lang),
        "confirmed_inactive": t("status_confirmed_inactive", lang),
    }


def map_legend_labels(lang: str) -> dict:
    return {
        "high": t("map_legend_high", lang),
        "medium": t("map_legend_medium", lang),
        "low": t("map_legend_low", lang),
        "unchecked": t("map_legend_unchecked", lang),
    }


def entity_type_labels(lang: str) -> dict:
    return {
        "enterprise": t("entity_type_enterprise", lang),
        "establishment": t("entity_type_establishment", lang),
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

def business_name(b: dict, lang: str) -> str:
    b = b or {}
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "zoeknaam"):
        value = b.get(key)
        if value:
            return value
    uidn = b.get("uidn")
    return t("business_name_prefix", lang, uidn=uidn) if uidn is not None else t(
        "business_name_unknown", lang
    )


def format_address(b: dict, lang: str) -> str:
    b = b or {}
    straat = b.get("kbo_straat") or ""
    huisnr = b.get("kbo_huisnr") or ""
    postcode = b.get("kbo_postcode") or ""
    gemeente = b.get("kbo_gemeente") or ""
    straat_huisnr = f"{straat} {huisnr}".strip()
    rest = " ".join(p for p in (postcode, gemeente) if p)
    parts = [p for p in (straat_huisnr, rest) if p]
    return ", ".join(parts) if parts else t("address_unknown", lang)


def format_date(value, lang: str) -> str:
    if not value:
        return t("unknown", lang)
    text = str(value)[:10]
    return text if text else t("unknown", lang)


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


def render_stats_header(db_path: str, lang: str) -> None:
    stats = get_stats(db_path)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("stat_total", lang), stats["total"])
    c2.metric(t("stat_checked", lang), stats["checked"])
    c3.metric(t("stat_high_priority", lang), stats["high_priority"])
    c4.metric(t("stat_confirmed", lang), stats["confirmed"])


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


def build_map_dataframe(rows: list, lang: str) -> pd.DataFrame:
    """Turn ``load_map_rows`` output into a DataFrame ready for st.map/pydeck."""
    scored = [r["priority_score"] for r in rows if r.get("priority_score") is not None]
    terciles = compute_priority_terciles(scored)

    labels = map_legend_labels(lang)
    records = []
    for r in rows:
        category = classify_priority(r.get("priority_score"), terciles)
        records.append(
            {
                "uidn": r["uidn"],
                "lat": r["latitude"],
                "lon": r["longitude"],
                "naam": business_name(r, lang),
                "prioriteit_label": labels[category],
                "color": _hex_to_rgb(MAP_CATEGORY_COLORS[category]),
            }
        )
    return pd.DataFrame(records)


def render_map(db_path: str, lang: str) -> None:
    st.subheader(t("map_header", lang))
    rows = load_map_rows(db_path)
    if not rows:
        st.info(t("map_no_data", lang))
        return

    df = build_map_dataframe(rows, lang)
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
    st.caption(t("map_caption_legend", lang))


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


def render_demo_scenario_control(db_path: str, lang: str) -> None:
    st.sidebar.divider()
    st.sidebar.caption(t("demo_caption", lang))
    if st.sidebar.button(t("demo_button", lang)):
        with st.sidebar:
            with st.spinner(t("demo_spinner", lang)):
                progress = st.progress(0.0)
                processed = run_demo_scenario(db_path, progress.progress)
        st.cache_data.clear()
        st.sidebar.success(t("demo_success", lang, n=processed))
        st.rerun()


# --------------------------------------------------------------------------
# Case-file paragraph (template-based, no LLM call -- see brief).
# --------------------------------------------------------------------------

def generate_case_file_text(business: dict, evidence_rows: list, dampener: dict, lang: str) -> str:
    name = business_name(business, lang)
    n = len(evidence_rows or [])
    if n == 0:
        return t("casefile_no_verification", lang, name=name)

    active = sum(1 for e in evidence_rows if e.get("signal") == "active")
    inactive = sum(1 for e in evidence_rows if e.get("signal") == "inactive")
    disagreement = sum(1 for e in evidence_rows if e.get("signal") == "disagreement")
    silent = sum(1 for e in evidence_rows if e.get("signal") == "silent")
    last_checked = max(
        (e.get("created_at") for e in evidence_rows if e.get("created_at")), default=None
    )

    clauses = []
    if active:
        clauses.append(t("casefile_clause_active", lang, active=active, n=n))
    if inactive:
        clauses.append(t("casefile_clause_inactive", lang, count=inactive))
    if silent:
        clauses.append(t("casefile_clause_silent", lang, count=silent))
    if disagreement:
        clauses.append(t("casefile_clause_disagreement", lang, count=disagreement))

    summary = ", ".join(clauses) if clauses else t("casefile_no_signal", lang)
    summary = summary[0].upper() + summary[1:]
    text = t("casefile_summary", lang, summary=summary, date=format_date(last_checked, lang))

    if dampener and dampener.get("dampener_factor", 1.0) < 1.0:
        # Note: app.seasonal returns `reason` in English (frozen module, not
        # ours to change) -- never interpolate it into officer-facing Dutch
        # text. Show a generic sentence here; the raw English reason is
        # surfaced separately as a labeled debug caption in the Dossier view.
        text += t("casefile_dampener_note", lang)

    return text


# --------------------------------------------------------------------------
# View 1 -- Dashboard (read-only monitoring: is the automatic system working)
# --------------------------------------------------------------------------

def view_dashboard(db_path: str, lang: str) -> None:
    """Pure monitoring view -- no actions to take here.

    Shows the stats banner, the map, and a short pointer to the freshness
    view. Deliberately minimal: it must not duplicate app/freshness.py's
    logic, just point the officer at it.
    """
    st.header(t("header_dashboard", lang))
    st.caption(t("dashboard_caption", lang))

    render_stats_header(db_path, lang)
    st.divider()
    render_map(db_path, lang)
    st.divider()
    st.caption(t("dashboard_freshness_pointer", lang))


# --------------------------------------------------------------------------
# View 2 -- Te verifiëren (the actionable queue)
# --------------------------------------------------------------------------

def view_to_verify(db_path: str, lang: str) -> None:
    """The action queue: what needs manual verification, and controls to act.

    This is what remains of the former single Triage-werklijst view once its
    stats banner and map (now monitoring-only) moved to view_dashboard.
    """
    st.header(t("header_to_verify", lang))
    st.caption(t("to_verify_caption", lang))

    rows = load_worklist(db_path)
    if not rows:
        st.info(t("no_businesses_found", lang))
        return

    labels = status_labels(lang)
    table_rows = []
    for r in rows:
        table_rows.append(
            {
                "uidn": r["uidn"],
                "naam": business_name(r, lang),
                "straat": r.get("kbo_straat") or "",
                "adres": format_address(r, lang),
                "nace": r.get("omschrijving_hoofdact_rsz")
                or r.get("omschrijving_hoofdact_btw")
                or "",
                "prioriteit": r.get("priority_score"),
                "status": labels.get(r.get("review_status"), labels[None]),
            }
        )
    df = pd.DataFrame(table_rows)

    checked = df[df["prioriteit"].notna()].sort_values("prioriteit", ascending=False)
    unchecked = df[df["prioriteit"].isna()]

    # Column keys above are neutral/internal so sorting and filtering never
    # depend on the display language; translate only at render time.
    column_labels = {
        "naam": t("col_name", lang),
        "straat": t("col_street", lang),
        "adres": t("col_address", lang),
        "nace": t("col_nace", lang),
        "prioriteit": t("col_priority", lang),
        "status": t("col_status", lang),
    }

    st.subheader(t("triage_checked_header", lang, n=len(checked)))
    if checked.empty:
        st.info(t("triage_no_checked", lang))
    else:
        st.dataframe(
            checked.drop(columns=["uidn"]).rename(columns=column_labels),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander(t("triage_unchecked_header", lang, n=len(unchecked))):
        st.dataframe(
            unchecked.drop(columns=["uidn", "prioriteit"]).rename(columns=column_labels),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader(t("triage_open_dossier_header", lang))
    options = {
        f"{business_name(r, lang)}, {format_address(r, lang)} (UIDN {r['uidn']})": r["uidn"]
        for r in rows
    }
    sorted_labels = sorted(options.keys())
    label = st.selectbox(t("triage_select_business", lang), sorted_labels)
    if st.button(t("triage_open_dossier_button", lang)):
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
    st.subheader(t("triage_verify_header", lang))
    st.caption(t("triage_verify_caption", lang, n=len(unchecked)))
    max_batch = max(1, min(50, len(unchecked)))
    batch_size = st.number_input(
        t("triage_batch_size_label", lang),
        min_value=1,
        max_value=max_batch,
        value=min(5, max_batch),
        step=1,
        disabled=unchecked.empty,
    )
    if st.button(t("triage_run_verification_button", lang), disabled=unchecked.empty):
        candidate_uidns = unchecked["uidn"].tolist()[: int(batch_size)]
        progress = st.progress(0.0)
        for i, uidn in enumerate(candidate_uidns):
            business = get_business(uidn, db_path)
            if business:
                scoring.run_all_sources(business, db_path)
                scoring.compute_score(uidn, db_path)
            progress.progress((i + 1) / len(candidate_uidns))
        st.cache_data.clear()
        st.success(t("triage_verify_success", lang, n=len(candidate_uidns)))
        st.rerun()


# --------------------------------------------------------------------------
# View 3 -- Dossier (Case File)
# --------------------------------------------------------------------------

def view_dossier(db_path: str, lang: str) -> None:
    st.header(t("header_dossier", lang))
    render_stats_header(db_path, lang)
    st.divider()

    businesses = cached_list_businesses(db_path)
    if not businesses:
        st.info(t("no_businesses_found", lang))
        return

    options = {f"{business_name(b, lang)} (UIDN {b['uidn']})": b["uidn"] for b in businesses}
    sorted_labels = sorted(options.keys())

    default_uidn = st.session_state.get("selected_uidn")
    default_label = next(
        (label for label, uidn in options.items() if uidn == default_uidn), None
    )
    default_index = sorted_labels.index(default_label) if default_label in sorted_labels else 0

    label = st.selectbox(t("dossier_select_business", lang), sorted_labels, index=default_index)
    uidn = options[label]
    st.session_state["selected_uidn"] = uidn

    business = get_business(uidn, db_path)
    if not business:
        st.error(t("dossier_not_found", lang))
        return

    st.subheader(business_name(business, lang))
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(t("dossier_label_name", lang, value=business_name(business, lang)))
        st.markdown(t("dossier_label_address", lang, value=format_address(business, lang)))
        st.markdown(
            t(
                "dossier_label_business_number",
                lang,
                value=business.get("ondernemingsnr") or t("unknown", lang),
            )
        )
    with col2:
        entity_type = business.get("entity_type")
        type_label = entity_type_labels(lang).get(entity_type, t("unknown", lang))
        st.markdown(t("dossier_label_type", lang, value=type_label))
        nace = (
            business.get("omschrijving_hoofdact_rsz")
            or business.get("omschrijving_hoofdact_btw")
            or t("unknown", lang)
        )
        st.markdown(t("dossier_label_nace", lang, value=nace))
        st.markdown(
            t(
                "dossier_label_registered_since",
                lang,
                value=format_date(business.get("datum_inschrijving"), lang),
            )
        )

    st.divider()
    status_row = get_status_row(uidn, db_path)
    current_status = status_row.get("review_status") if status_row else None
    labels = status_labels(lang)
    st.markdown(
        t("dossier_current_status_header", lang, status=labels.get(current_status, labels[None]))
    )
    if status_row and status_row.get("note"):
        st.caption(t("dossier_note_caption", lang, note=status_row["note"]))
    if status_row and status_row.get("updated_at"):
        st.caption(
            t(
                "dossier_last_updated_caption",
                lang,
                date=format_date(status_row["updated_at"], lang),
            )
        )

    st.divider()
    st.subheader(t("dossier_verification_header", lang))
    if st.button(t("dossier_run_verification_button", lang)):
        with st.spinner(t("dossier_verification_spinner", lang)):
            scoring.run_all_sources(business, db_path)
            scoring.compute_score(uidn, db_path)
        st.cache_data.clear()
        st.success(t("dossier_verification_success", lang))
        st.rerun()

    if st.button(t("dossier_call_simulation_button", lang)):
        render_call_simulation(business, db_path, lang)
        scoring.compute_score(uidn, db_path)
        st.cache_data.clear()
        st.success(t("dossier_call_simulation_success", lang))
        st.rerun()

    evidence_rows = get_evidence(uidn, db_path)
    score = get_score(uidn, db_path)
    dampener = seasonal.seasonal_dampener(business, evidence_rows, date.today().month)

    st.divider()
    st.subheader(t("dossier_case_file_header", lang))
    st.write(generate_case_file_text(business, evidence_rows, dampener, lang))
    if dampener and dampener.get("dampener_factor", 1.0) < 1.0 and dampener.get("reason"):
        # app.seasonal's `reason` field is English (module is frozen, not ours
        # to change) -- shown only as clearly-labeled internal/debug detail,
        # never as officer-facing Dutch text.
        st.caption(t("dossier_internal_debug_caption", lang, reason=dampener["reason"]))

    st.divider()
    st.subheader(t("dossier_score_header", lang))
    if score:
        c1, c2, c3 = st.columns(3)
        c1.metric(t("dossier_metric_uncertainty", lang), score.get("uncertainty_score"))
        c2.metric(t("dossier_metric_impact", lang), score.get("impact_score"))
        c3.metric(t("dossier_metric_priority_total", lang), score.get("priority_score"))
        st.caption(
            t(
                "dossier_last_calculated_caption",
                lang,
                date=format_date(score.get("updated_at"), lang),
            )
        )
    else:
        st.info(t("dossier_no_score_info", lang))

    st.divider()
    render_history(business, evidence_rows, lang, db_path)

    st.divider()
    st.subheader(t("dossier_review_header", lang))
    note = st.text_input(t("dossier_note_input_label", lang))
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(t("dossier_confirm_active_button", lang)):
            set_status(uidn, "confirmed_active", note or None, db_path)
            st.cache_data.clear()
            st.success(t("dossier_status_updated", lang, status=labels["confirmed_active"]))
            st.rerun()
    with col_b:
        if st.button(t("dossier_confirm_inactive_button", lang)):
            set_status(uidn, "confirmed_inactive", note or None, db_path)
            st.cache_data.clear()
            st.success(t("dossier_status_updated", lang, status=labels["confirmed_inactive"]))
            st.rerun()


# --------------------------------------------------------------------------
# View 4 -- Ontdekkingslijst (Discovery Queue) -- minimal placeholder + demo
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


def run_discovery_sample(db_path: str, lang: str) -> list:
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

    # Fixed to "nl": this list is only used internally for fuzzy name
    # matching below, never displayed, so it must not vary with the UI
    # language toggle (that would change matching behavior).
    known_names = [business_name(b, "nl") for b in cached_list_businesses(db_path)]

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
            category = (
                tags.get("shop") or tags.get("office") or tags.get("amenity") or t("unknown", lang)
            )
            unmatched.append({"name": name, "category": category, "best_ratio": best_ratio})
        if len(unmatched) >= DISCOVERY_MAX_RESULTS:
            break
    return unmatched


def view_discovery_queue(db_path: str, lang: str) -> None:
    st.header(t("header_discovery", lang))
    render_stats_header(db_path, lang)
    st.divider()
    st.write(t("discovery_intro", lang))
    st.caption(t("discovery_caption", lang))

    if st.button(t("discovery_run_button", lang)):
        with st.spinner(t("discovery_spinner", lang)):
            try:
                results = run_discovery_sample(db_path, lang)
            except Exception as exc:  # noqa: BLE001 -- demo must degrade, not crash
                st.error(t("discovery_error", lang, error=exc))
                results = None

        if results is not None:
            if not results:
                st.info(t("discovery_no_results", lang))
            else:
                st.write(t("discovery_results_count", lang, n=len(results)))
                for r in results:
                    st.markdown(
                        t(
                            "discovery_result_item",
                            lang,
                            name=r["name"],
                            category=r["category"],
                            ratio=f"{r['best_ratio']:.0%}",
                        )
                    )


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

def main() -> None:
    # Read the previous run's language choice (if any) so the page title can
    # reflect it immediately; on a fresh session there is no "lang" key yet,
    # so this defaults to Dutch, per the compliance requirement.
    lang = st.session_state.get("lang", "nl")
    st.set_page_config(page_title=t("page_title", lang), layout="wide")

    st.sidebar.title("PROV-AI")

    # Language toggle, prominently placed above the nav radio. Deliberately
    # bilingual/invariant label ("Taal / Language") and Dutch-first ordering
    # so the default is always Dutch on a fresh load. Uses its own widget key
    # ("lang_select") distinct from the "lang" session_state key we read
    # above/write below, since a widget-bound key cannot be reassigned after
    # the widget already exists in this run (same constraint as "nav" below).
    lang_labels = list(LANGUAGES.keys())
    current_label = next(k for k, v in LANGUAGES.items() if v == lang)
    lang_label = st.sidebar.selectbox(
        "Taal / Language",
        lang_labels,
        index=lang_labels.index(current_label),
        key="lang_select",
    )
    lang = LANGUAGES[lang_label]
    st.session_state["lang"] = lang

    st.sidebar.caption(t("sidebar_caption", lang))

    if "pending_nav" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("pending_nav")
    if "nav" not in st.session_state:
        st.session_state["nav"] = NAV_OPTIONS[0]
    # Flat radio list, ordered with the two primary screens (Dashboard,
    # Te verifiëren) first -- a caption above the radio conveys the
    # primary/secondary hierarchy without restructuring the widget itself,
    # which would risk the pending_nav/key="nav" session-state contract
    # relied on elsewhere (see the "Open dossier" button in view_to_verify).
    st.sidebar.caption(t("nav_primary_label", lang))
    nav = st.sidebar.radio(
        t("nav_label", lang),
        NAV_OPTIONS,
        key="nav",
        format_func=lambda opt: t(NAV_LABEL_KEYS[opt], lang),
    )
    render_demo_scenario_control(DB_PATH, lang)

    if nav == "Dashboard":
        view_dashboard(DB_PATH, lang)
    elif nav == "Te verifiëren":
        view_to_verify(DB_PATH, lang)
    elif nav == "Dossier":
        view_dossier(DB_PATH, lang)
    elif nav == "Ontdekkingslijst":
        view_discovery_queue(DB_PATH, lang)
    else:
        freshness_view.render(DB_PATH)


if __name__ == "__main__":
    main()
