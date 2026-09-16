"""Streamlit view: AI search assistant chat.

Lets an officer type a free-text question, or click a suggested example
question, and get back an answer drawn from the real business data in this
register. Under the hood this is plain, real keyword matching against the
``businesses``, ``status`` and ``scores`` tables (see ``generate_response``
below), dressed up with a chat interface and a brief "thinking" animation
that lists the connected data sources it appears to be consulting. There is
no language model involved.

Self-contained on purpose, following the pattern in ``app/ui/history_view.py``
and ``app/ui/data_sources_view.py``: it exposes a single ``render(...)``
function, keeps its own small local translation dict, and does not import
from or touch ``app/ui/streamlit_app.py``.

The response-generation logic (``generate_response`` and its helpers) is
kept free of any Streamlit calls so it can be exercised directly in tests
without a Streamlit runtime.
"""

import sqlite3
import time

import streamlit as st

from app.db import get_connection
from app.ingest import list_businesses

_AI_STRINGS = {
    "nl": {
        "header": "AI-zoekassistent",
        "intro": (
            "Stel een vraag over een geregistreerde onderneming en krijg een "
            "antwoord opgesteld op basis van alle gekoppelde databronnen."
        ),
        "chat_input_placeholder": "Stel hier je vraag...",
        "suggestion_1": "Zoek alle frituren in de buurt van het centrum.",
        "suggestion_2": "Welke bedrijven zijn recent bevestigd actief?",
        "suggestion_3": "Toon bedrijven die nog verificatie nodig hebben.",
        "suggestion_4": "Wat doet {name} eigenlijk?",
        "suggestion_4_generic": "Wat doet een bepaalde onderneming eigenlijk?",
        "thinking_stage_1": "Ondernemingsregister doorzoeken...",
        "thinking_stage_2": "Google Maps-gegevens controleren...",
        "thinking_stage_3": "Resultaten samenstellen...",
        "no_businesses_in_register": (
            "Er staan momenteel nog geen ondernemingen in het register."
        ),
        "unnamed_business": "Naamloze onderneming",
        "activity_intro": (
            "Dit zijn de ondernemingen uit het register die hierbij aansluiten:"
        ),
        "confirmed_intro": "Dit zijn de ondernemingen die recent zijn bevestigd:",
        "priority_intro": (
            "Dit zijn de ondernemingen met de hoogste prioriteit voor verificatie:"
        ),
        "name_match_intro": "Dit vond ik over deze onderneming:",
        "fallback_intro": (
            "Ik vond geen exacte match, maar deze ondernemingen uit het register "
            "zijn wellicht interessant:"
        ),
        "sources_consulted_label": "Geraadpleegde bronnen",
        "source_register": "Ondernemingsregister",
        "source_maps": "Google Maps",
        "source_osm": "OpenStreetMap",
        "source_scoring": "Scoringsmodule",
        "source_reviews": "Trustpilot",
    },
    "en": {
        "header": "AI search assistant",
        "intro": (
            "Ask a question about any registered business and get an answer "
            "compiled from all connected data sources."
        ),
        "chat_input_placeholder": "Ask your question here...",
        "suggestion_1": "Find all fry shops near the town center.",
        "suggestion_2": "Which businesses were recently confirmed active?",
        "suggestion_3": "Show businesses that still need verification.",
        "suggestion_4": "What does {name} actually do?",
        "suggestion_4_generic": "What does a particular business actually do?",
        "thinking_stage_1": "Searching the business register...",
        "thinking_stage_2": "Checking Google Maps data...",
        "thinking_stage_3": "Compiling results...",
        "no_businesses_in_register": "There are no businesses in the register yet.",
        "unnamed_business": "Unnamed business",
        "activity_intro": "Here are the businesses in the register that match:",
        "confirmed_intro": "Here are the businesses that were recently confirmed:",
        "priority_intro": (
            "Here are the businesses with the highest priority for verification:"
        ),
        "name_match_intro": "Here is what I found about this business:",
        "fallback_intro": (
            "I did not find an exact match, but these businesses from the "
            "register might be of interest:"
        ),
        "sources_consulted_label": "Sources consulted",
        "source_register": "Business register",
        "source_maps": "Google Maps",
        "source_osm": "OpenStreetMap",
        "source_scoring": "Scoring engine",
        "source_reviews": "Trustpilot",
    },
}

# (keyword variants to look for in the user's message, search term to look
# for in the business's activity description columns).
_ACTIVITY_KEYWORDS = (
    (("frituur", "frituren", "fry shop", "fry shops", "fries", "friet"), "frituur"),
    (("kapper", "kapsalon", "hairdresser", "hair salon"), "kap"),
    (("restaurant", "restaurants", "eatery", "eaterie"), "restaurant"),
    (("bakker", "bakkerij", "bakery", "bakeries"), "bakker"),
    (("slager", "slagerij", "butcher"), "slager"),
    (("apotheek", "apotheken", "pharmacy"), "apothe"),
)

_CONFIRMED_KEYWORDS = (
    "confirmed", "recently confirmed", "verified", "recently verified",
    "bevestigd", "recent bevestigd", "geverifieerd", "recent geverifieerd",
)

_PRIORITY_KEYWORDS = (
    "priority", "needs verification", "need verification", "still need",
    "unverified", "not yet verified",
    "prioriteit", "verificatie nodig", "nog te verifieren", "nog te controleren",
    "nog niet geverifieerd",
)

_SOURCE_KEYS_BY_CATEGORY = {
    "activity": ("source_register", "source_maps", "source_osm"),
    "confirmed": ("source_register", "source_maps"),
    "priority": ("source_register", "source_scoring"),
    "name": ("source_register", "source_maps", "source_reviews"),
    "fallback": ("source_register", "source_maps", "source_reviews"),
}

_MIN_NAME_MATCH_LENGTH = 3
_MAX_RESULTS = 5


def _strings(lang: str) -> dict:
    return _AI_STRINGS.get(lang, _AI_STRINGS["nl"])


def _safe_list_businesses(db_path: str) -> list:
    """list_businesses, but returns [] instead of raising on any DB error."""
    try:
        return list_businesses(db_path) or []
    except sqlite3.Error:
        return []


def _business_display_name(business: dict, strings: dict) -> str:
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return strings["unnamed_business"]


def _format_address(business: dict) -> str:
    street_bits = " ".join(
        str(part) for part in (business.get("kbo_straat"), business.get("kbo_huisnr")) if part
    )
    locality_bits = " ".join(
        str(part) for part in (business.get("kbo_postcode"), business.get("kbo_gemeente")) if part
    )
    return ", ".join(bit for bit in (street_bits, locality_bits) if bit)


def _format_business_list(businesses: list, strings: dict) -> str:
    lines = []
    for business in businesses:
        name = _business_display_name(business, strings)
        address = _format_address(business)
        entry = f"- **{name}**"
        if address:
            entry += f", {address}"
        lines.append(entry)
    return "\n".join(lines)


def _sources_line(strings: dict, category: str) -> str:
    keys = _SOURCE_KEYS_BY_CATEGORY.get(category, _SOURCE_KEYS_BY_CATEGORY["fallback"])
    names = ", ".join(strings[key] for key in keys)
    return f"*{strings['sources_consulted_label']}: {names}*"


def _match_activity_keyword(message_lower: str):
    """Return the DB search term for the first matching activity keyword, or None."""
    for variants, term in _ACTIVITY_KEYWORDS:
        if any(variant in message_lower for variant in variants):
            return term
    return None


def _build_activity_response(businesses: list, term: str, strings: dict):
    matches = []
    for business in businesses:
        haystack = " ".join(
            str(business.get(field) or "")
            for field in ("omschrijving_hoofdact_rsz", "omschrijving_hoofdact_btw")
        ).lower()
        if term in haystack:
            matches.append(business)
            if len(matches) >= _MAX_RESULTS:
                break
    if not matches:
        return None
    body = strings["activity_intro"] + "\n\n" + _format_business_list(matches, strings)
    return body + "\n\n" + _sources_line(strings, "activity")


def _build_confirmed_response(db_path: str, strings: dict):
    try:
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                """
                SELECT b.*, s.review_status, s.updated_at AS status_updated_at
                FROM status s
                JOIN businesses b ON b.uidn = s.business_uidn
                WHERE s.review_status IN ('confirmed_active', 'confirmed_inactive')
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (_MAX_RESULTS,),
            ).fetchall()
            matches = [dict(row) for row in rows]
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not matches:
        return None
    body = strings["confirmed_intro"] + "\n\n" + _format_business_list(matches, strings)
    return body + "\n\n" + _sources_line(strings, "confirmed")


def _build_priority_response(db_path: str, strings: dict):
    try:
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                """
                SELECT b.*, sc.priority_score
                FROM scores sc
                JOIN businesses b ON b.uidn = sc.business_uidn
                ORDER BY sc.priority_score DESC
                LIMIT ?
                """,
                (_MAX_RESULTS,),
            ).fetchall()
            matches = [dict(row) for row in rows]
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not matches:
        return None
    body = strings["priority_intro"] + "\n\n" + _format_business_list(matches, strings)
    return body + "\n\n" + _sources_line(strings, "priority")


def _match_business_names(businesses: list, message_lower: str) -> list:
    matches = []
    for business in businesses:
        for key in ("commerciele_naam", "maatschappelijke_naam", "zoeknaam"):
            name = business.get(key)
            if name and len(name) >= _MIN_NAME_MATCH_LENGTH and name.lower() in message_lower:
                matches.append(business)
                break
        if len(matches) >= _MAX_RESULTS:
            break
    return matches


def _build_name_match_response(matches: list, strings: dict) -> str:
    lines = []
    for business in matches:
        name = _business_display_name(business, strings)
        address = _format_address(business)
        entry = f"- **{name}**"
        if address:
            entry += f", {address}"
        description = business.get("description")
        if description:
            entry += f"\n  {description}"
        lines.append(entry)
    body = strings["name_match_intro"] + "\n\n" + "\n".join(lines)
    return body + "\n\n" + _sources_line(strings, "name")


def _build_fallback_response(businesses: list, strings: dict) -> str:
    sample = businesses[:_MAX_RESULTS]
    body = strings["fallback_intro"] + "\n\n" + _format_business_list(sample, strings)
    return body + "\n\n" + _sources_line(strings, "fallback")


def generate_response(message: str, db_path: str, lang: str) -> str:
    """Compute the assistant's reply to ``message`` using real business data.

    Plain keyword matching against the local database, no language model
    involved. Never raises and never returns an empty string: falls back to
    a generic, still-plausible-looking response when nothing more specific
    matches, and to a dedicated "no businesses yet" message when the
    register itself is empty (or unreachable).
    """
    strings = _strings(lang)
    businesses = _safe_list_businesses(db_path)
    if not businesses:
        return strings["no_businesses_in_register"]

    message_lower = (message or "").lower()

    activity_term = _match_activity_keyword(message_lower)
    if activity_term:
        response = _build_activity_response(businesses, activity_term, strings)
        if response:
            return response

    if any(keyword in message_lower for keyword in _CONFIRMED_KEYWORDS):
        response = _build_confirmed_response(db_path, strings)
        if response:
            return response

    if any(keyword in message_lower for keyword in _PRIORITY_KEYWORDS):
        response = _build_priority_response(db_path, strings)
        if response:
            return response

    name_matches = _match_business_names(businesses, message_lower)
    if name_matches:
        return _build_name_match_response(name_matches, strings)

    return _build_fallback_response(businesses, strings)


def _pick_example_business_name(db_path: str):
    """Return a real business name for the 4th suggestion button, or None."""
    for business in _safe_list_businesses(db_path):
        name = business.get("commerciele_naam") or business.get("maatschappelijke_naam")
        if name:
            return name
    return None


def _play_thinking_animation(strings: dict) -> None:
    """Play a short, fixed thinking sequence in one reused placeholder.

    Purely cosmetic: reuses a single st.empty() placeholder across all
    stages (replacing, not stacking) so it reads as one animated line.
    Total sleep time across the three stages is 1.5 seconds.
    """
    placeholder = st.empty()
    for stage_key in ("thinking_stage_1", "thinking_stage_2", "thinking_stage_3"):
        placeholder.markdown(f"🔎 {strings[stage_key]}")
        time.sleep(0.5)
    return placeholder


def render(db_path: str, lang: str) -> None:
    """Render the AI search assistant chat screen.

    Chat history lives in ``st.session_state["ai_chat_messages"]`` as a list
    of ``{"role": "user"|"assistant", "content": str}`` dicts and is
    replayed in full on every rerun via ``st.chat_message`` blocks.
    ``lang`` is ``"nl"`` or ``"en"``.
    """
    strings = _strings(lang)

    if "ai_chat_messages" not in st.session_state:
        st.session_state["ai_chat_messages"] = []

    st.header(strings["header"])
    st.caption(strings["intro"])

    example_name = _pick_example_business_name(db_path)
    suggestion_4 = (
        strings["suggestion_4"].format(name=example_name)
        if example_name
        else strings["suggestion_4_generic"]
    )
    suggestion_texts = [
        strings["suggestion_1"],
        strings["suggestion_2"],
        strings["suggestion_3"],
        suggestion_4,
    ]

    clicked_text = None
    columns = st.columns(len(suggestion_texts))
    for index, (column, text) in enumerate(zip(columns, suggestion_texts)):
        with column:
            if st.button(text, key=f"ai_suggestion_{index}", use_container_width=True):
                clicked_text = text

    for message in st.session_state["ai_chat_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    typed_text = st.chat_input(strings["chat_input_placeholder"])

    new_text = clicked_text or typed_text
    if new_text:
        st.session_state["ai_chat_messages"].append({"role": "user", "content": new_text})
        with st.chat_message("user"):
            st.markdown(new_text)

        with st.chat_message("assistant"):
            placeholder = _play_thinking_animation(strings)
            response = generate_response(new_text, db_path, lang)
            placeholder.markdown(response)

        st.session_state["ai_chat_messages"].append({"role": "assistant", "content": response})
