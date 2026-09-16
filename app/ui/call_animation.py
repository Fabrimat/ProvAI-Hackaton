"""Self-contained UI helper: animate an AI voice-agent call, then reveal the
real outcome from app.sources.voice_stub.

Kept separate from streamlit_app.py: it owns its own small translation dict
(_CALL_STRINGS, distinct from streamlit_app.py's TRANSLATIONS) and its own
styled result card, and does not import anything from streamlit_app.py.

The whole animation plays inside one st.empty() placeholder: each stage
replaces the previous one instead of stacking, and the placeholder ends on
the final result card. This blocks the current Streamlit rerun for a couple
of seconds while it plays out, which is expected for this demo.
"""
import html
import random
import time

import streamlit as st

from app.sources import voice_stub

_CALL_STRINGS = {
    "nl": {
        "dialing": "Bellen naar {phone}...",
        "ringing": "Rinkelt{dots}",
        "connected": "Verbonden, in gesprek met {name}...",
        "result_active": "Actief bevestigd",
        "result_inactive": "Sluiting bevestigd",
        "result_silent": "Geen resultaat",
        "detail_label": "Detail",
        "unknown_business": "deze onderneming",
    },
    "en": {
        "dialing": "Dialing {phone}...",
        "ringing": "Ringing{dots}",
        "connected": "Connected, talking to {name}...",
        "result_active": "Active confirmed",
        "result_inactive": "Closure confirmed",
        "result_silent": "No result",
        "detail_label": "Detail",
        "unknown_business": "this business",
    },
}

_RESULT_COLORS = {
    "active": "#2e7d32",    # green
    "inactive": "#c62828",  # red
    "silent": "#757575",    # grey, doubles as the "amber/neutral" tone here
}

_RESULT_LABEL_KEYS = {
    "active": "result_active",
    "inactive": "result_inactive",
    "silent": "result_silent",
}


def _s(key: str, lang: str, **kwargs) -> str:
    """Look up a stage/result string for lang, falling back to nl if missing."""
    lang_dict = _CALL_STRINGS.get(lang, _CALL_STRINGS["nl"])
    text = lang_dict.get(key, _CALL_STRINGS["nl"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


def _business_name(business: dict, lang: str) -> str:
    business = business or {}
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "naam", "zoeknaam"):
        value = business.get(key)
        if value:
            return value
    return _s("unknown_business", lang)


def _fake_phone_number(uidn) -> str:
    """A cosmetic local-looking phone number for the dialing stage.

    Deterministic per business uidn so the same dossier always shows the
    same number on replay, but this is purely decorative for the animation
    and separate from voice_stub's own outcome randomness (voice_stub seeds
    its own random.Random(uidn) independently).
    """
    rng = random.Random(uidn)
    return f"03-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"


def render_call_simulation(business: dict, db_path: str, lang: str) -> dict:
    """Play a short animated call sequence, then reveal the real outcome.

    Renders every stage into one placeholder (created with st.empty()) so
    each update replaces the previous stage instead of stacking. After the
    animation, calls voice_stub.call(business, db_path) for the real,
    deterministic outcome and replaces the placeholder with a styled result
    card. Returns the outcome dict ({"signal": ..., "detail": ...}) so the
    caller can react afterward, e.g. clear caches and rerun. Does not call
    st.rerun() or clear any cache itself.
    """
    business = business or {}
    name = html.escape(str(_business_name(business, lang)))
    phone = _fake_phone_number(business.get("uidn"))

    placeholder = st.empty()

    placeholder.markdown(f"📞 {_s('dialing', lang, phone=phone)}")
    time.sleep(0.5)

    for dots in (".", "..", "..."):
        placeholder.markdown(f"📞 {_s('ringing', lang, dots=dots)}")
        time.sleep(0.3)

    placeholder.markdown(f"📞 {_s('connected', lang, name=name)}")
    time.sleep(0.6)

    outcome = voice_stub.call(business, db_path)
    signal = outcome.get("signal") or "silent"
    detail = html.escape(str(outcome.get("detail") or ""))
    color = _RESULT_COLORS.get(signal, "#757575")
    result_label = _s(_RESULT_LABEL_KEYS.get(signal, "result_silent"), lang)

    placeholder.markdown(
        f"""
        <div style="border-left: 4px solid {color}; padding: 8px 12px; margin-bottom: 6px;
                    background-color: rgba(127,127,127,0.08); border-radius: 4px;">
            <span style="color:{color}; font-weight:700;">{result_label}</span><br/>
            <span style="font-size:0.9em;">{_s('detail_label', lang)}: {detail}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    return outcome
