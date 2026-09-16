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

from app import db, description, scoring, seasonal  # noqa: E402
from app.db import get_connection  # noqa: E402
from app.ingest import get_business, list_businesses  # noqa: E402
from app.sources import address_crosscheck  # noqa: E402
from app.ui import call_animation, freshness_view, search_animation  # noqa: E402
from app.ui.history_view import render_history  # noqa: E402
from app.ui import ai_search_chat, data_sources_view, theme  # noqa: E402

DB_PATH = str(REPO_ROOT / "data" / "provai.db")

# Startup migration safety net: local/non-Docker runs of this app must also
# get the schema migration and evidence-dedupe cleanup that the Docker
# container's own entrypoint already performs. Cheap and idempotent, so
# running these on every script execution/rerun is acceptable overhead.
db.init_db(DB_PATH)
description.backfill_missing_descriptions(DB_PATH)
scoring.dedupe_evidence(DB_PATH)

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
        "nav_more_label": "Meer",
        "nav_full_list_link": "Volledige gegevenslijst",
        "nav_business_portal_link": "Bedrijvenportaal",
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
        "map_legend_panel_title": "Legenda",
        "map_coverage_panel_title": "Overzicht",
        "map_coverage_caption": (
            "Deze aantallen worden bij elke vernieuwing van het dashboard opnieuw berekend."
        ),
        "demo_caption": "Snel gevulde voorbeeldgegevens laden:",
        "demo_button": "Voorbeeldgegevens laden",
        "demo_spinner": "Voorbeeldgegevens worden geladen...",
        "demo_success": "Voorbeeldgegevens geladen: {n} bedrijven gecontroleerd.",
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
            "Verificatie wordt niet automatisch uitgevoerd voor alle {n} nog te "
            "controleren bedrijven. Kies hieronder hoeveel bedrijven nu geverifieerd "
            "worden, of open een dossier hierboven om één bedrijf tegelijk te verifiëren."
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
        "dossier_verification_success": "Verificatie voltooid.",
        "dossier_call_simulation_button": "Bel dit bedrijf",
        "dossier_case_file_header": "Case-dossier",
        "dossier_internal_debug_caption": "(interne detail, EN: {reason})",
        "dossier_reliability_header": "Betrouwbaarheid",
        "reliability_status_active": "Actief",
        "reliability_status_inactive": "Inactief",
        "reliability_status_unknown": "Onbekend",
        "reliability_trust_trusted": "Betrouwbaar",
        "reliability_trust_needs_verification": "Verificatie aanbevolen",
        "reliability_freshness_fresh": "Actueel",
        "reliability_freshness_aging": "Verouderend",
        "reliability_freshness_stale": "Verouderd",
        "dossier_address_conflict_label": "Adresconflict",
        "dossier_open_related_dossier_button": "Open dossier van dit bedrijf",
        "dossier_sources_overview_header": "Bronnen in één oogopslag",
        "source_not_yet_checked": "Nog niet gecontroleerd",
        "dossier_technical_details_header": "Technische details",
        "col_reliability": "Betrouwbaarheid",
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
            "Onderstaande weergave haalt een beperkt aantal echte OSM-punten op rond het "
            "centrum van Schoten en toont welke namen niet overeenkomen met een bedrijf in het "
            "register. Dit is een best-effort steekproef, geen volledige implementatie."
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
        "nav_more_label": "More",
        "nav_full_list_link": "Full data list",
        "nav_business_portal_link": "Business portal",
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
        "map_legend_panel_title": "Legend",
        "map_coverage_panel_title": "Overview",
        "map_coverage_caption": (
            "These counts are recalculated every time the dashboard refreshes."
        ),
        "demo_caption": "Quickly load a populated set of sample data:",
        "demo_button": "Load sample data",
        "demo_spinner": "Loading sample data...",
        "demo_success": "Sample data loaded: {n} businesses checked.",
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
            "Verification is not automatically run for all {n} businesses still to be "
            "checked. Choose below how many businesses to verify now, or open a case "
            "file above to verify one business at a time."
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
        "dossier_verification_success": "Verification completed.",
        "dossier_call_simulation_button": "Call this business",
        "dossier_case_file_header": "Case file",
        "dossier_internal_debug_caption": "(internal detail, EN: {reason})",
        "dossier_reliability_header": "Reliability",
        "reliability_status_active": "Active",
        "reliability_status_inactive": "Inactive",
        "reliability_status_unknown": "Unknown",
        "reliability_trust_trusted": "Reliable",
        "reliability_trust_needs_verification": "Verification recommended",
        "reliability_freshness_fresh": "Up to date",
        "reliability_freshness_aging": "Aging",
        "reliability_freshness_stale": "Outdated",
        "dossier_address_conflict_label": "Address conflict",
        "dossier_open_related_dossier_button": "Open this business's dossier",
        "dossier_sources_overview_header": "Sources at a glance",
        "source_not_yet_checked": "Not yet checked",
        "dossier_technical_details_header": "Technical details",
        "col_reliability": "Reliability",
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
            "The view below fetches a limited number of real OSM points around "
            "the center of Schoten and shows which names do not match a business in the "
            "register. This is a best-effort sample, not a full implementation."
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
    row_html = theme.stat_row_html(
        [
            theme.stat_block_html(t("stat_total", lang), str(stats["total"])),
            theme.stat_block_html(t("stat_checked", lang), str(stats["checked"])),
            theme.stat_block_html(
                t("stat_high_priority", lang), str(stats["high_priority"]), accent=True
            ),
            theme.stat_block_html(t("stat_confirmed", lang), str(stats["confirmed"])),
        ]
    )
    st.markdown(row_html, unsafe_allow_html=True)


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

# Evidence signal -> badge color, shared by the dossier's reliability badges,
# the "sources at a glance" overview and the worklist's per-row color-coding
# below. Reuses the exact same hex palette as MAP_CATEGORY_COLORS above so
# every color-coded surface in this app reads consistently.
SIGNAL_BADGE_COLORS = {
    "active": MAP_COLOR_LOW,
    "inactive": MAP_COLOR_HIGH,
    "disagreement": MAP_COLOR_MEDIUM,
    "silent": MAP_COLOR_UNCHECKED,
}

# Human-readable names for every evidence source (keyed by each
# app.sources.*.SOURCE_NAME), used by the dossier's "sources at a glance"
# overview.
SOURCE_DISPLAY_NAMES = {
    "google_maps": {"nl": "Google Maps", "en": "Google Maps"},
    "trustpilot": {"nl": "Trustpilot", "en": "Trustpilot"},
    "infobel": {"nl": "Bedrijvengids (Infobel)", "en": "Business directory (Infobel)"},
    "osm": {"nl": "OpenStreetMap", "en": "OpenStreetMap"},
    "voice_agent": {"nl": "Telefooncontrole", "en": "Phone call check"},
    "email": {"nl": "E-mailcontrole", "en": "E-mail check"},
    "internal_mailbox": {"nl": "Interne postbus", "en": "Internal mailbox"},
    "neighbor_check": {"nl": "Burencontrole", "en": "Neighbor check"},
    "address_crosscheck": {"nl": "Adrescontrole", "en": "Address cross-check"},
}

# Display order for the sources-overview grid, matching
# scoring.run_all_sources's own run order (Google Maps ... address cross-check).
SOURCE_DISPLAY_ORDER = [
    "google_maps",
    "trustpilot",
    "infobel",
    "osm",
    "voice_agent",
    "email",
    "internal_mailbox",
    "neighbor_check",
    "address_crosscheck",
]


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


def _map_legend_panel_html(lang: str) -> str:
    """HTML for the map's aside "Legend" panel: one color swatch + label per
    priority category, reusing MAP_CATEGORY_COLORS/map_legend_labels as-is.
    """
    labels = map_legend_labels(lang)
    rows_html = "".join(
        '<div style="display:flex;align-items:center;gap:9px;">'
        f'<span style="width:9px;height:9px;background:{MAP_CATEGORY_COLORS[category]};'
        'flex:none;display:inline-block;"></span>'
        f"{html.escape(labels[category])}</div>"
        for category in ("unchecked", "low", "medium", "high")
    )
    return (
        f'<div style="border:1px solid {theme.COLOR_NEUTRAL_300};background:#ffffff;'
        'margin-bottom:16px;">'
        f'{theme.panel_header(t("map_legend_panel_title", lang))}'
        '<div style="display:flex;flex-direction:column;gap:9px;font-size:13px;'
        f'padding:12px 14px;">{rows_html}</div></div>'
    )


def _map_coverage_panel_html(db_path: str, lang: str) -> str:
    """HTML for the map's aside coverage panel: a few already-computed
    get_stats() counts as key/value rows, plus a short explanatory caption.
    """
    stats = get_stats(db_path)
    kv_rows = [
        (t("stat_total", lang), stats["total"]),
        (t("stat_checked", lang), stats["checked"]),
        (t("stat_confirmed", lang), stats["confirmed"]),
    ]
    last = len(kv_rows) - 1
    rows_html = "".join(
        '<div style="display:flex;justify-content:space-between;gap:14px;padding:8px 14px;'
        + ("border-bottom:0;" if i == last else f"border-bottom:1px solid {theme.COLOR_NEUTRAL_200};")
        + 'font-size:13px;">'
        f'<span style="color:{theme.COLOR_NEUTRAL_700};">{html.escape(label)}</span>'
        f"<b>{html.escape(str(value))}</b></div>"
        for i, (label, value) in enumerate(kv_rows)
    )
    caption_html = (
        '<p style="font-size:12.5px;margin:0;padding:12px 14px;'
        f'border-top:1px solid {theme.COLOR_NEUTRAL_200};color:{theme.COLOR_NEUTRAL_700};">'
        f'{html.escape(t("map_coverage_caption", lang))}</p>'
    )
    return (
        f'<div style="border:1px solid {theme.COLOR_NEUTRAL_300};background:#ffffff;">'
        f'{theme.panel_header(t("map_coverage_panel_title", lang))}'
        f"{rows_html}{caption_html}</div>"
    )


def render_map(db_path: str, lang: str) -> None:
    st.subheader(t("map_header", lang))
    rows = load_map_rows(db_path)
    if not rows:
        st.info(t("map_no_data", lang))
        return

    df = build_map_dataframe(rows, lang)
    map_col, aside_col = st.columns([3, 1])
    with map_col:
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
            st.pydeck_chart(
                pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip)
            )
        except Exception:  # noqa: BLE001 -- map must degrade, never crash the dashboard
            st.map(df[["lat", "lon"]])
        st.caption(t("map_caption_legend", lang))
    with aside_col:
        st.markdown(_map_legend_panel_html(lang), unsafe_allow_html=True)
        st.markdown(_map_coverage_panel_html(db_path, lang), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# One-click demo scenario (curated set of real businesses).
# --------------------------------------------------------------------------

def run_demo_scenario(db_path: str, on_progress=None, include_mailbox: bool = True) -> int:
    """Run the scoring pipeline for CURATED_DEMO_UIDNS.

    Safe to call repeatedly: run_all_sources/compute_score already
    upsert/accumulate, so re-running never duplicates scores and only
    adds (harmless) extra evidence rows. Returns the number of curated
    businesses actually found and processed. ``on_progress``, if given,
    is called with a float in [0, 1] after each business (matching the
    ``st.progress(...)`` calling convention already used elsewhere in
    this file). ``include_mailbox`` is threaded straight through to
    ``scoring.run_all_sources``.
    """
    total = len(CURATED_DEMO_UIDNS)
    processed = 0
    for i, uidn in enumerate(CURATED_DEMO_UIDNS):
        business = get_business(uidn, db_path)
        if business:
            scoring.run_all_sources(business, db_path, include_mailbox=include_mailbox)
            scoring.compute_score(uidn, db_path)
            processed += 1
        if on_progress:
            on_progress((i + 1) / total)
    return processed


def render_demo_scenario_control(db_path: str, lang: str) -> None:
    st.sidebar.divider()
    st.sidebar.caption(t("demo_caption", lang))
    if st.sidebar.button(t("demo_button", lang)):
        include_mailbox = st.session_state.get("mailbox_source_enabled", False)
        with st.sidebar:
            with st.spinner(t("demo_spinner", lang)):
                progress = st.progress(0.0)
                processed = run_demo_scenario(db_path, progress.progress, include_mailbox=include_mailbox)
        st.cache_data.clear()
        # Flash pattern, see render_flash(): a success message right before
        # st.rerun() would only be visible for a fraction of a second (if at
        # all) before the redraw wipes it, so it is stashed and rendered on
        # the next run instead.
        st.session_state["flash"] = {
            "kind": "success",
            "text": t("demo_success", lang, n=processed),
        }
        st.rerun()


# --------------------------------------------------------------------------
# Flash messages: a single session_state slot for a success/info message that
# must survive an immediately-following st.rerun(). Without this, a message
# rendered right before st.rerun() is drawn for a fraction of a second (if at
# all) and then wiped by the redraw -- on video this looks like the button
# click did nothing. Every st.success(...) + st.rerun() pair in this file
# goes through this instead.
# --------------------------------------------------------------------------

def render_flash() -> None:
    """Render and consume the pending flash message, if any.

    Called once near the top of main(), before any view is dispatched, so
    the message appears above whichever view is currently shown.
    """
    flash = st.session_state.get("flash")
    if not flash:
        return
    text = flash.get("text", "")
    if flash.get("kind") == "info":
        st.info(text)
    else:
        st.success(text)
    st.session_state["flash"] = None


# --------------------------------------------------------------------------
# Guided tour: a scripted sequence of navigation-only stops for a presenter
# to walk through. Steps only change nav/selected_uidn session_state (the
# same pending_nav mechanism used elsewhere in this file); they never trigger
# an in-view action themselves, so the presenter still visibly clicks the
# real buttons on camera. Assumes CURATED_DEMO_UIDNS was already seeded via
# the "Voorbeeldgegevens laden" button before recording started.
# --------------------------------------------------------------------------

DEMO_WALKTHROUGH_STEPS = [
    {
        "nav": "Dashboard",
        "caption_nl": "het automatische monitoringdashboard.",
        "caption_en": "the automatic monitoring dashboard.",
    },
    {
        "nav": "Te verifiëren",
        "caption_nl": "de actielijst van de ambtenaar.",
        "caption_en": "the officer's action queue.",
    },
    {
        "nav": "Dossier",
        "uidn": CURATED_DEMO_UIDNS[0],
        "caption_nl": "één gemarkeerd dossier openen.",
        "caption_en": "opening one flagged case.",
    },
    {
        "nav": "Dossier",
        "uidn": CURATED_DEMO_UIDNS[0],
        "caption_nl": "klik op de belknop om de AI-spraakcontrole te tonen.",
        "caption_en": "click the call button to show the AI voice check.",
    },
    {
        "nav": "Dossier",
        "uidn": CURATED_DEMO_UIDNS[0],
        "caption_nl": "bevestig de uitkomst met een van de knoppen hieronder.",
        "caption_en": "confirm the outcome with one of the buttons below.",
    },
    {
        "nav": "Wat is er veranderd?",
        "caption_nl": "wat er veranderd is sinds de laatste controle.",
        "caption_en": "what changed since the last check.",
    },
]


def render_demo_walkthrough_control(lang: str) -> None:
    """Sidebar expander stepping a presenter through DEMO_WALKTHROUGH_STEPS.

    Deliberately excludes Ontdekkingslijst and the batch-verification
    control (both make live network calls, better left to manual, off-script
    demonstration) and never calls run_demo_scenario() itself (that must be
    run before recording starts, see render_demo_scenario_control above).
    """
    total = len(DEMO_WALKTHROUGH_STEPS)
    expander_title = "Snelle rondleiding" if lang == "nl" else "Guided tour"
    with st.sidebar.expander(expander_title):
        step = st.session_state.get("demo_step", 0)
        if step > 0:
            current = DEMO_WALKTHROUGH_STEPS[step - 1]
            if lang == "nl":
                st.caption(f"Stap {step} van {total}: {current['caption_nl']}")
            else:
                st.caption(f"Step {step} of {total}: {current['caption_en']}")
        else:
            st.caption(
                "Nog niet gestart." if lang == "nl" else "Not started yet."
            )

        col_next, col_reset = st.columns(2)
        with col_next:
            next_label = "Volgende stap" if lang == "nl" else "Next step"
            if st.button(next_label, key="demo_walkthrough_next"):
                next_step = step + 1 if step < total else 1
                target = DEMO_WALKTHROUGH_STEPS[next_step - 1]
                st.session_state["pending_nav"] = target["nav"]
                if "uidn" in target:
                    st.session_state["selected_uidn"] = target["uidn"]
                st.session_state["demo_step"] = next_step
                st.rerun()
        with col_reset:
            # "Reset" reads the same in both languages, no translation needed.
            if st.button("Reset", key="demo_walkthrough_reset"):
                st.session_state["demo_step"] = 0
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

# Small dot + label tag styling for the worklist table, matching the
# mockup's ".stg"/".st-unknown"/".st-high"/".st-medium"/".st-low" tags
# (theme.py's semantic palette, not the red/orange/green MAP_COLOR_* one
# the map and dossier badges use). This only changes how a row's existing
# MAP_COLOR_* value is drawn here -- the category itself still comes from
# the same classify_priority()/_trust_proxy_badge() calls as before.
_MOCKUP_DOT_STYLE_BY_MAP_COLOR = {
    MAP_COLOR_UNCHECKED: ("○", theme.COLOR_UNKNOWN),  # outline dot, grey
    MAP_COLOR_LOW: ("●", theme.COLOR_SETTLED),  # filled dot, dark neutral
    MAP_COLOR_MEDIUM: ("●", theme.COLOR_ACCENT_LIGHT),  # filled dot, light accent
    MAP_COLOR_HIGH: ("●", theme.COLOR_ACCENT),  # filled dot, accent
}


def _mockup_dot_style(map_color_hex: str):
    """Map a MAP_COLOR_* hex to a mockup-style ``(glyph, text_color)`` pair."""
    return _MOCKUP_DOT_STYLE_BY_MAP_COLOR.get(
        map_color_hex, ("○", theme.COLOR_UNKNOWN)
    )


def _dot_label(label: str, map_color_hex: str) -> str:
    """Prefix ``label`` with the mockup's small dot glyph for ``map_color_hex``."""
    glyph, _ = _mockup_dot_style(map_color_hex)
    return f"{glyph} {label}"


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
                "onzekerheid": r.get("uncertainty_score"),
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
        # Color-coding for this worklist: priority tier reuses the exact
        # same terciles/classify_priority() as the map and the dossier
        # badges. The per-row trust/reliability indicator does NOT call
        # scoring.compute_reliability_report() once per row here -- that
        # would mean an extra set of evidence/gmaps/address-crosscheck
        # queries per business, on every render, for a worklist that can
        # hold hundreds of rows. Instead it uses the cheap uncertainty_score
        # proxy (see _trust_proxy_badge), which load_worklist() already
        # joined in with no extra query. The full, accurate reliability
        # verdict is still shown, but only for the single business currently
        # chosen in "Open dossier" below -- one compute_reliability_report()
        # call, not N.
        terciles = _worklist_priority_terciles(db_path)
        priority_col = column_labels["prioriteit"]
        trust_col = t("col_reliability", lang)

        row_colors = {
            idx: (
                MAP_CATEGORY_COLORS[classify_priority(r["prioriteit"], terciles)],
                _trust_proxy_badge(r["onzekerheid"], lang)[1],
            )
            for idx, r in checked.iterrows()
        }

        display = checked.drop(columns=["uidn"]).copy()
        display[trust_col] = checked["onzekerheid"].apply(
            lambda u: _dot_label(*_trust_proxy_badge(u, lang))
        )
        display = display.drop(columns=["onzekerheid"]).rename(columns=column_labels)

        def _highlight_row(row):
            tier_map_color, trust_map_color = row_colors.get(
                row.name, (MAP_COLOR_UNCHECKED, MAP_COLOR_UNCHECKED)
            )
            _, tier_dot_color = _mockup_dot_style(tier_map_color)
            _, trust_dot_color = _mockup_dot_style(trust_map_color)
            styles = pd.Series("", index=row.index)
            styles[priority_col] = f"color: {tier_dot_color}; font-weight: 700;"
            styles[trust_col] = f"color: {trust_dot_color}; font-weight: 600;"
            return styles

        st.dataframe(
            display.style.apply(_highlight_row, axis=1).hide(axis="index"),
            use_container_width=True,
        )

    with st.expander(t("triage_unchecked_header", lang, n=len(unchecked))):
        st.dataframe(
            unchecked.drop(columns=["uidn", "prioriteit", "onzekerheid"]).rename(
                columns=column_labels
            ),
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
    selected_uidn = options[label]
    # Full, accurate reliability verdict, computed for only this one
    # currently-selected business -- see the comment above the worklist
    # table for why this is not done for every row.
    selected_reliability = scoring.compute_reliability_report(selected_uidn, db_path)
    trust_label, trust_color = _trust_badge(selected_reliability.get("trust"), lang)
    render_badge_row([(trust_label, trust_color)])
    if st.button(t("triage_open_dossier_button", lang)):
        st.session_state["selected_uidn"] = selected_uidn
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
        include_mailbox = st.session_state.get("mailbox_source_enabled", False)
        progress = st.progress(0.0)
        for i, uidn in enumerate(candidate_uidns):
            business = get_business(uidn, db_path)
            if business:
                scoring.run_all_sources(business, db_path, include_mailbox=include_mailbox)
                scoring.compute_score(uidn, db_path)
            progress.progress((i + 1) / len(candidate_uidns))
        st.cache_data.clear()
        st.session_state["flash"] = {
            "kind": "success",
            "text": t("triage_verify_success", lang, n=len(candidate_uidns)),
        }
        st.rerun()


# --------------------------------------------------------------------------
# Reliability badges, address-conflict callout and sources-overview.
#
# Officers see plain words and colors here, not raw internal scores: this is
# the primary explanation of why the platform does or doesn't trust a
# business's information, per explicit product direction. The raw numeric
# scores and the per-evidence-row listing move into a collapsed "Technical
# details" expander instead (see view_dossier).
# --------------------------------------------------------------------------

def _worklist_priority_terciles(db_path: str):
    """Priority terciles over every scored business in the worklist.

    The same ``compute_priority_terciles``/``classify_priority`` pair the
    map already uses, reused as-is (not re-derived) so the dossier badges,
    the worklist table and the map all agree on what counts as
    low/medium/high priority.
    """
    rows = load_worklist(db_path)
    scored = [r.get("priority_score") for r in rows if r.get("priority_score") is not None]
    return compute_priority_terciles(scored)


def render_badge_row(items: list) -> None:
    """Render a compact row of color-coded pill badges.

    ``items`` is a list of ``(label, hex_color)`` tuples. Pure presentation;
    used by the dossier's reliability badges and the worklist's per-row
    trust indicator.
    """
    chips = "".join(
        f'<span style="display:inline-block; padding:4px 12px; margin:2px 8px 2px 0; '
        f'border-radius:12px; background-color:{color}; color:#ffffff; font-weight:600; '
        f'font-size:0.85em;">{html.escape(str(label))}</span>'
        for label, color in items
    )
    st.markdown(chips, unsafe_allow_html=True)


def _status_badge(status, lang: str):
    mapping = {
        "active": (t("reliability_status_active", lang), MAP_COLOR_LOW),
        "inactive": (t("reliability_status_inactive", lang), MAP_COLOR_HIGH),
    }
    return mapping.get(status, (t("reliability_status_unknown", lang), MAP_COLOR_UNCHECKED))


def _trust_badge(trust, lang: str):
    # Defensive default: an unrecognized or missing trust value must never
    # read as a false "trusted" -- fall back to the amber "needs
    # verification" state instead (matters for a business that has never
    # been checked yet).
    mapping = {
        "trusted": (t("reliability_trust_trusted", lang), MAP_COLOR_LOW),
        "needs_verification": (
            t("reliability_trust_needs_verification", lang),
            MAP_COLOR_MEDIUM,
        ),
    }
    return mapping.get(trust, (t("reliability_trust_needs_verification", lang), MAP_COLOR_MEDIUM))


def _freshness_badge(freshness, lang: str):
    mapping = {
        "fresh": (t("reliability_freshness_fresh", lang), MAP_COLOR_LOW),
        "aging": (t("reliability_freshness_aging", lang), MAP_COLOR_MEDIUM),
        "stale": (t("reliability_freshness_stale", lang), MAP_COLOR_HIGH),
    }
    return mapping.get(freshness, (t("reliability_freshness_stale", lang), MAP_COLOR_HIGH))


def _priority_badge(priority_score, terciles, lang: str):
    category = classify_priority(priority_score, terciles)
    return map_legend_labels(lang)[category], MAP_CATEGORY_COLORS[category]


def _trust_proxy_badge(uncertainty_score, lang: str):
    """Cheap, no-extra-query proxy for reliability, for the bulk worklist
    table only (see view_to_verify).

    Derived only from ``uncertainty_score``, which ``load_worklist`` already
    joins in with no extra query. This is NOT the same computation as
    ``scoring.compute_reliability_report``'s trust verdict (that also weighs
    Google Maps review recency and costs a handful of extra queries per
    business) -- it is a lighter-weight, still-useful stand-in so the full
    worklist can be color-coded without a per-row database round trip.
    """
    if uncertainty_score is None or pd.isna(uncertainty_score):
        return t("map_legend_unchecked", lang), MAP_COLOR_UNCHECKED
    if uncertainty_score == 0:
        return t("reliability_trust_trusted", lang), MAP_COLOR_LOW
    return t("reliability_trust_needs_verification", lang), MAP_COLOR_MEDIUM


def render_reliability_badges(reliability: dict, score, terciles, lang: str) -> None:
    """Render the compact row of status/trust/freshness/priority badges.

    ``reliability`` is ``scoring.compute_reliability_report(...)``'s return
    value, ``score`` is ``get_score(...)``'s return value (``None`` if this
    business has never been scored yet), ``terciles`` are the priority
    terciles from ``_worklist_priority_terciles``.
    """
    reliability = reliability or {}
    status_label, status_color = _status_badge(reliability.get("status"), lang)
    trust_label, trust_color = _trust_badge(reliability.get("trust"), lang)
    freshness_label, freshness_color = _freshness_badge(reliability.get("freshness"), lang)
    priority_score = score.get("priority_score") if score else None
    priority_label, priority_color = _priority_badge(priority_score, terciles, lang)

    render_badge_row(
        [
            (status_label, status_color),
            (trust_label, trust_color),
            (freshness_label, freshness_color),
            (priority_label, priority_color),
        ]
    )


def render_address_conflict_callout(note: str, related_uidn, lang: str) -> None:
    """A distinct, amber-bordered callout for an address conflict.

    ``related_uidn`` (may be ``None``) is the uidn of the other business
    registered at the same address, per ``address_crosscheck.check()``'s
    ``related_uidn`` field -- when present, offers a button that navigates
    to that business's own dossier via the established pending_nav
    mechanism.
    """
    color = MAP_COLOR_MEDIUM
    st.markdown(
        f"""
        <div style="border: 2px solid {color}; padding: 10px 14px; margin: 10px 0;
                    background-color: rgba(239,108,0,0.10); border-radius: 6px;">
            <span style="color:{color}; font-weight:700;">
                &#9888; {html.escape(t("dossier_address_conflict_label", lang))}
            </span><br/>
            <span style="font-size:0.95em;">{html.escape(str(note))}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if related_uidn is not None:
        if st.button(
            t("dossier_open_related_dossier_button", lang),
            key=f"open_related_dossier_{related_uidn}",
        ):
            # Same pending_nav indirection used elsewhere in this file: "nav"
            # is a widget-bound session_state key and cannot be reassigned
            # directly once its radio widget already exists in this run.
            st.session_state["selected_uidn"] = related_uidn
            st.session_state["pending_nav"] = "Dossier"
            st.rerun()


def render_sources_overview(evidence_rows: list, lang: str) -> None:
    """One compact card per evidence source, showing its most recent signal.

    ``evidence_rows`` is this business's evidence rows (see ``get_evidence``);
    grouped/indexed by ``source`` since every source keeps at most one row
    per business. Sources with no evidence row yet show a neutral "not yet
    checked" grey state.
    """
    by_source = {row.get("source"): row for row in (evidence_rows or []) if row.get("source")}

    cols = st.columns(3)
    for i, source_key in enumerate(SOURCE_DISPLAY_ORDER):
        names = SOURCE_DISPLAY_NAMES.get(source_key, {})
        name = names.get(lang, names.get("nl", source_key))
        row = by_source.get(source_key)
        if row:
            signal = row.get("signal") or "silent"
            color = SIGNAL_BADGE_COLORS.get(signal, MAP_COLOR_UNCHECKED)
            summary = row.get("detail") or t("source_not_yet_checked", lang)
        else:
            color = MAP_COLOR_UNCHECKED
            summary = t("source_not_yet_checked", lang)

        with cols[i % 3]:
            st.markdown(
                f"""
                <div style="border-left: 4px solid {color}; padding: 6px 10px; margin-bottom: 8px;
                            background-color: rgba(127,127,127,0.08); border-radius: 4px;
                            min-height: 88px;">
                    <b>{html.escape(name)}</b><br/>
                    <span style="font-size:0.85em;">{html.escape(str(summary))}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )


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
        search_animation.render_search_animation(
            business,
            db_path,
            lang,
            include_mailbox=st.session_state.get("mailbox_source_enabled", False),
        )
        st.cache_data.clear()
        st.session_state["flash"] = {
            "kind": "success",
            "text": t("dossier_verification_success", lang),
        }
        st.rerun()

    if st.button(t("dossier_call_simulation_button", lang)):
        call_animation.open_call_dialog(business, db_path, lang)

    evidence_rows = get_evidence(uidn, db_path)
    score = get_score(uidn, db_path)
    dampener = seasonal.seasonal_dampener(business, evidence_rows, date.today().month)
    reliability = scoring.compute_reliability_report(uidn, db_path)

    st.divider()
    st.subheader(t("dossier_case_file_header", lang))
    st.write(generate_case_file_text(business, evidence_rows, dampener, lang))
    if dampener and dampener.get("dampener_factor", 1.0) < 1.0 and dampener.get("reason"):
        # app.seasonal's `reason` field is English (module is frozen, not ours
        # to change) -- shown only as clearly-labeled internal/debug detail,
        # never as officer-facing Dutch text.
        st.caption(t("dossier_internal_debug_caption", lang, reason=dampener["reason"]))

    st.divider()
    st.subheader(t("dossier_reliability_header", lang))
    terciles = _worklist_priority_terciles(db_path)
    render_reliability_badges(reliability, score, terciles, lang)
    reason = reliability.get("reason") or ""
    if reason:
        st.markdown(f"**{html.escape(reason)}**")

    # Part B: a live, deterministic re-check (log=False, so this never
    # writes a duplicate evidence row on render) -- gives both the
    # officer-friendly note text (preferring compute_reliability_report's
    # own address_note when present) and the conflicting business's
    # related_uidn for the "open dossier" link below.
    conflict = address_crosscheck.check(business, db_path, log=False)
    if conflict.get("signal") == "disagreement":
        note_text = reliability.get("address_note") or conflict.get("detail")
        render_address_conflict_callout(note_text, conflict.get("related_uidn"), lang)

    st.divider()
    st.subheader(t("dossier_sources_overview_header", lang))
    render_sources_overview(evidence_rows, lang)

    with st.expander(t("dossier_technical_details_header", lang)):
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

        render_history(business, evidence_rows, lang, db_path)

    st.divider()
    st.subheader(t("dossier_review_header", lang))
    note = st.text_input(t("dossier_note_input_label", lang))
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(t("dossier_confirm_active_button", lang)):
            set_status(uidn, "confirmed_active", note or None, db_path)
            st.cache_data.clear()
            st.session_state["flash"] = {
                "kind": "success",
                "text": t("dossier_status_updated", lang, status=labels["confirmed_active"]),
            }
            st.rerun()
    with col_b:
        if st.button(t("dossier_confirm_inactive_button", lang)):
            set_status(uidn, "confirmed_inactive", note or None, db_path)
            st.cache_data.clear()
            st.session_state["flash"] = {
                "kind": "success",
                "text": t("dossier_status_updated", lang, status=labels["confirmed_inactive"]),
            }
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
    theme.inject()

    # Hide Streamlit's own automatic sidebar page-list (testid stSidebarNav)
    # so only this app's own custom sidebar navigation below is visible --
    # otherwise both are stacked in the sidebar at once. Selector targets
    # stSidebarNav as of streamlit 1.38; re-check if streamlit is upgraded.
    st.markdown(
        "<style>[data-testid='stSidebarNav'] {display: none;}</style>",
        unsafe_allow_html=True,
    )

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

    # Secondary pages (auto-discovered by Streamlit, but their own automatic
    # nav entry is hidden above): one deliberately-ordered "more" section
    # below the main radio, instead of two separate nav panels.
    st.sidebar.divider()
    st.sidebar.caption(t("nav_more_label", lang))
    st.sidebar.page_link("pages/1_Volledige_gegevenslijst.py", label=t("nav_full_list_link", lang))
    st.sidebar.page_link("pages/2_Bedrijvenportaal.py", label=t("nav_business_portal_link", lang))

    render_demo_scenario_control(DB_PATH, lang)
    render_demo_walkthrough_control(lang)

    render_flash()

    if nav == "Dashboard":
        view_dashboard(DB_PATH, lang)
    elif nav == "Te verifiëren":
        view_to_verify(DB_PATH, lang)
    elif nav == "Dossier":
        view_dossier(DB_PATH, lang)
    elif nav == "Zoeken":
        ai_search_chat.render(DB_PATH, lang)
    elif nav == "Databronnen":
        data_sources_view.render(DB_PATH, lang)
    elif nav == "Ontdekkingslijst":
        view_discovery_queue(DB_PATH, lang)
    else:
        freshness_view.render(DB_PATH)


if __name__ == "__main__":
    main()
