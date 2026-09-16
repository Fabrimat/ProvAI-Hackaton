"""Streamlit view: "Data sources" admin-style screen.

Shows the evidence sources the platform currently draws on for business
verification, and lets an officer connect a new one (an internal mailbox
search) through a short animated flow.

Self-contained on purpose, following the pattern in ``app/ui/history_view.py``
and ``app/ui/freshness_view.py``: it exposes a single ``render(...)``
function, keeps its own small local translation dict, and does not import
from or touch ``app/ui/streamlit_app.py``.

Shared contract with the rest of the app: the session-state boolean key
``mailbox_source_enabled`` (default/absent treated as False) controls whether
the internal mailbox source is considered connected. This module only flips
that flag; it does not consume it anywhere else.

The "Analyze" flow does not parse or evaluate whatever text is pasted into
the text area. The animated stages and the results summary shown afterward
are fixed and always the same, regardless of the input.
"""

import html
import time

import streamlit as st

from app.ui import theme

_DS_STRINGS = {
    "nl": {
        "header": "Databronnen",
        "intro": (
            "Overzicht van de bronnen die het platform raadpleegt bij het "
            "verifiëren van een onderneming."
        ),
        "active_subheader": "Actieve bronnen",
        "active_badge": "Actief",
        "source_google_maps_name": "Google Maps",
        "source_google_maps_desc": "Controleert bedrijfsstatus en recente reviewactiviteit.",
        "source_trustpilot_name": "Trustpilot",
        "source_trustpilot_desc": "Doorzoekt klantbeoordelingen op signalen van activiteit of sluiting.",
        "source_directory_name": "Bedrijven- en telefoongids",
        "source_directory_desc": "Vergelijkt contactgegevens en vermeldingen in externe gidsen.",
        "source_osm_name": "OpenStreetMap",
        "source_osm_desc": "Controleert of de locatie als bedrijf op de kaart geregistreerd staat.",
        "source_voice_call_name": "AI-telefooncontrole",
        "source_voice_call_desc": "Belt het geregistreerde nummer en vraagt naar de huidige status.",
        "source_email_name": "E-mailcontrole",
        "source_email_desc": "Verstuurt een controle-e-mail naar het geregistreerde adres.",
        "source_nearby_name": "Controle bij buurbedrijven",
        "source_nearby_desc": "Vraagt naburige ondernemingen om de bevindingen te bevestigen.",
        "source_address_name": "Adrescontrole",
        "source_address_desc": (
            "Signaleert wanneer een andere, nieuwere onderneming zich op "
            "hetzelfde adres heeft ingeschreven."
        ),
        "source_mailbox_name": "Interne mailbox",
        "source_mailbox_desc": "Doorzoekt interne mailboxen op vermeldingen van ondernemingen.",
        "remove_mailbox_button": "Verwijderen",
        "add_new_subheader": "Nieuwe databron toevoegen",
        "add_new_intro": (
            "Verbind een nieuwe bron, bijvoorbeeld een export van een "
            "e-mailinbox, zodat het platform deze kan doorzoeken op "
            "vermeldingen van ondernemingen."
        ),
        "textarea_label": "Voorbeeldtekst",
        "textarea_placeholder": (
            "Plak hier bijvoorbeeld de inhoud van een e-mailexport of "
            "postvak..."
        ),
        "analyze_button": "Analyseren",
        "stage_reading": "Gegevens lezen...",
        "stage_names": "Bedrijfsnamen herkennen...",
        "stage_contacts": "Contactgegevens koppelen...",
        "stage_register": "Kruisverwijzing met het register...",
        "results_summary": (
            "3 vermeldingen van geregistreerde ondernemingen gevonden. "
            "2 contactpersonen geïdentificeerd. Klaar om toe te voegen "
            "als databron."
        ),
        "add_source_button": "Bron toevoegen",
        "add_source_success": "Interne mailbox toegevoegd als databron.",
        "available_connectors_header": "Beschikbare connectoren",
        "available_badge": "Beschikbaar",
    },
    "en": {
        "header": "Data sources",
        "intro": (
            "Overview of the sources the platform consults when verifying "
            "a business."
        ),
        "active_subheader": "Active sources",
        "active_badge": "Active",
        "source_google_maps_name": "Google Maps",
        "source_google_maps_desc": "Checks business status and recent review activity.",
        "source_trustpilot_name": "Trustpilot",
        "source_trustpilot_desc": "Searches customer reviews for signals of activity or closure.",
        "source_directory_name": "Business and phone directory",
        "source_directory_desc": "Cross-checks contact details and listings in external directories.",
        "source_osm_name": "OpenStreetMap",
        "source_osm_desc": "Checks whether the location is registered as a business on the map.",
        "source_voice_call_name": "AI voice-call check",
        "source_voice_call_desc": "Calls the registered number and asks about the current status.",
        "source_email_name": "E-mail check",
        "source_email_desc": "Sends a verification e-mail to the registered address.",
        "source_nearby_name": "Nearby businesses check",
        "source_nearby_desc": "Asks neighboring businesses to corroborate the findings.",
        "source_address_name": "Address cross-reference",
        "source_address_desc": (
            "Flags when a different, newer business has registered at the "
            "same address."
        ),
        "source_mailbox_name": "Internal mailbox",
        "source_mailbox_desc": "Searches internal mailboxes for mentions of businesses.",
        "remove_mailbox_button": "Remove",
        "add_new_subheader": "Add a new data source",
        "add_new_intro": (
            "Connect a new source, for example an export of an e-mail "
            "inbox, so the platform can search it for mentions of "
            "businesses."
        ),
        "textarea_label": "Sample text",
        "textarea_placeholder": (
            "Paste, for example, the contents of an e-mail export or "
            "inbox here..."
        ),
        "analyze_button": "Analyze",
        "stage_reading": "Reading the data...",
        "stage_names": "Recognizing business names...",
        "stage_contacts": "Linking contact details...",
        "stage_register": "Cross-referencing with the register...",
        "results_summary": (
            "3 mentions of registered businesses found. 2 contact persons "
            "identified. Ready to add as a data source."
        ),
        "add_source_button": "Add source",
        "add_source_success": "Internal mailbox added as a data source.",
        "available_connectors_header": "Available connectors",
        "available_badge": "Available",
    },
}

# (name_key, desc_key) for the sources always shown, in display order.
_BASE_SOURCES = [
    ("source_google_maps_name", "source_google_maps_desc"),
    ("source_trustpilot_name", "source_trustpilot_desc"),
    ("source_directory_name", "source_directory_desc"),
    ("source_osm_name", "source_osm_desc"),
    ("source_voice_call_name", "source_voice_call_desc"),
    ("source_email_name", "source_email_desc"),
    ("source_nearby_name", "source_nearby_desc"),
    ("source_address_name", "source_address_desc"),
]

# Thin border used for card outlines and the grid's own "hairline" gaps
# (the grid background shows through the 1px gap between cells).
_CARD_BORDER = theme.COLOR_NEUTRAL_300
_CARD_GRID_STYLE = (
    "display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); "
    f"gap:1px; background-color:{_CARD_BORDER}; border:1px solid {_CARD_BORDER};"
)

# List of available connectors: (emoji, name) tuples for the gallery section.
_AVAILABLE_CONNECTORS = [
    ("🏢", "Locatus Online"),
    ("🗺️", "Google Maps"),
    ("⭐", "Trustpilot"),
    ("📖", "Gouden Gids"),
    ("🌍", "OpenStreetMap"),
    ("📋", "Chamber of Commerce"),
    ("💼", "LinkedIn Company Pages"),
]


def _s(strings: dict, key: str) -> str:
    return strings.get(key, key)


def _badge_html(label: str, connected: bool) -> str:
    """A small status tag: solid dark when connected, outlined when not."""
    label = html.escape(str(label))
    if connected:
        return (
            '<span style="font-size:10px; letter-spacing:.08em; text-transform:uppercase; '
            f'font-weight:600; background-color:{theme.COLOR_NEUTRAL_800}; color:#fff; '
            f'padding:2px 7px;">{label}</span>'
        )
    return (
        '<span style="font-size:10px; letter-spacing:.08em; text-transform:uppercase; '
        f'font-weight:600; border:1px solid {_CARD_BORDER}; padding:1px 6px; '
        f'color:{theme.COLOR_NEUTRAL_700};">{label}</span>'
    )


def _connector_card_html(
    name: str, description: str, badge_label: str, connected: bool, icon: str = ""
) -> str:
    """One bordered connector cell for the cards grid.

    ``icon``, when given, is reused as-is (an emoji already assigned to
    that connector elsewhere in this module) inside a small bordered
    square; connectors without an assigned icon simply render without one.
    """
    name = html.escape(str(name))
    icon_html = ""
    if icon:
        icon_html = (
            f'<div style="width:32px; height:32px; border:1px solid {_CARD_BORDER}; '
            f'display:grid; place-items:center; color:{theme.COLOR_ACCENT}; flex:none; '
            f'font-size:1.05em;">{html.escape(str(icon))}</div>'
        )
    desc_html = ""
    if description:
        desc_html = (
            f'<div style="font-size:12.5px; line-height:1.45; '
            f'color:{theme.COLOR_NEUTRAL_700};">{html.escape(str(description))}</div>'
        )
    return f"""
    <div style="background-color:#fff; padding:14px; display:flex;
                flex-direction:column; gap:10px; min-height:110px;">
        <div style="display:flex; align-items:flex-start; gap:10px;">
            {icon_html}
            <div style="margin-left:auto;">{_badge_html(badge_label, connected)}</div>
        </div>
        <div>
            <div style="font-weight:600; font-size:14.5px; line-height:1.3;">{name}</div>
            {desc_html}
        </div>
    </div>
    """


def _render_active_sources(strings: dict, mailbox_enabled: bool) -> None:
    st.markdown(
        theme.panel_header(_s(strings, "active_subheader")), unsafe_allow_html=True
    )

    cards_html = f'<div style="{_CARD_GRID_STYLE}">'
    for name_key, desc_key in _BASE_SOURCES:
        cards_html += _connector_card_html(
            _s(strings, name_key),
            _s(strings, desc_key),
            _s(strings, "active_badge"),
            connected=True,
        )
    if mailbox_enabled:
        cards_html += _connector_card_html(
            _s(strings, "source_mailbox_name"),
            _s(strings, "source_mailbox_desc"),
            _s(strings, "active_badge"),
            connected=True,
        )
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)

    if mailbox_enabled:
        _, remove_col = st.columns([5, 1])
        with remove_col:
            if st.button(_s(strings, "remove_mailbox_button"), key="ds_remove_mailbox"):
                st.session_state["mailbox_source_enabled"] = False


def _play_mailbox_analysis_animation(strings: dict) -> None:
    """Play the fixed animated analysis sequence in one reused placeholder.

    Purely cosmetic: does not parse or evaluate any real input. Total sleep
    time across the four stages is 2.4 seconds.
    """
    placeholder = st.empty()

    stage_keys = ["stage_reading", "stage_names", "stage_contacts", "stage_register"]
    for stage_key in stage_keys:
        placeholder.markdown(f"⏳ {_s(strings, stage_key)}")
        time.sleep(0.6)

    placeholder.markdown(
        f"""
        <div style="border:1px solid {_CARD_BORDER}; border-left:4px solid {theme.COLOR_ACCENT};
                    padding: 8px 12px; margin-bottom: 6px; background-color:#fff;">
            <span style="font-size:0.9em;">{html.escape(_s(strings, "results_summary"))}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_add_source_flow(strings: dict) -> None:
    st.markdown(
        theme.panel_header(_s(strings, "add_new_subheader")), unsafe_allow_html=True
    )
    st.write(_s(strings, "add_new_intro"))

    st.text_area(
        _s(strings, "textarea_label"),
        placeholder=_s(strings, "textarea_placeholder"),
        key="ds_mailbox_sample_text",
        height=150,
    )

    if st.button(_s(strings, "analyze_button"), key="ds_analyze_mailbox"):
        st.session_state["ds_mailbox_analyzed"] = True

    if st.session_state.get("ds_mailbox_analyzed"):
        _play_mailbox_analysis_animation(strings)

        if st.button(_s(strings, "add_source_button"), key="ds_add_mailbox_source"):
            st.session_state["mailbox_source_enabled"] = True
            st.session_state["ds_mailbox_analyzed"] = False
            st.success(_s(strings, "add_source_success"))


def _render_available_connectors(strings: dict) -> None:
    """Render a decorative gallery of available third-party data connectors.

    This section is purely informational and contains no interactive elements.
    Each connector is displayed with an emoji icon, name, and neutral badge.
    """
    st.markdown(
        theme.panel_header(_s(strings, "available_connectors_header")),
        unsafe_allow_html=True,
    )

    cards_html = f'<div style="{_CARD_GRID_STYLE}">'
    for emoji, name in _AVAILABLE_CONNECTORS:
        cards_html += _connector_card_html(
            name, "", _s(strings, "available_badge"), connected=False, icon=emoji
        )
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)


def render(db_path: str, lang: str) -> None:
    """Render the data sources screen.

    ``db_path`` is accepted for interface symmetry with other render helpers
    in this app but is not used: this screen only reads/writes Streamlit
    session state, it does not query the database. ``lang`` is ``"nl"`` or
    ``"en"``.
    """
    strings = _DS_STRINGS.get(lang, _DS_STRINGS["nl"])

    st.header(_s(strings, "header"))
    st.caption(_s(strings, "intro"))

    mailbox_enabled = bool(st.session_state.get("mailbox_source_enabled", False))

    _render_active_sources(strings, mailbox_enabled)

    if not mailbox_enabled:
        st.divider()
        _render_add_source_flow(strings)

    st.divider()
    _render_available_connectors(strings)
