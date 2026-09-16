"""Self-contained UI helper: animate a multi-provider verification search,
then run the real ``scoring.run_all_sources``/``scoring.compute_score``
pipeline behind it.

Kept separate from streamlit_app.py: it owns its own small translation dict
(_SEARCH_STRINGS, distinct from streamlit_app.py's TRANSLATIONS) and does not
import anything from streamlit_app.py. Mirrors the single-reused-st.empty()
placeholder pattern already established by app/ui/call_animation.py (not
imported from here, kept self-contained).

Per explicit product direction the on-screen stage timing is abbreviated: a
brief time.sleep() per source (roughly 0.2-0.4s) so the full 8-9 stage
sequence still reads clearly but takes only a couple of seconds in total.
"""
import time

import streamlit as st

from app import scoring

_SEARCH_STRINGS = {
    "nl": {
        "stage": "{source} doorzoeken... ({index}/{total})",
        "complete": "Verificatie voltooid",
    },
    "en": {
        "stage": "Searching {source}... ({index}/{total})",
        "complete": "Verification complete",
    },
}

# Per-stage pause: short enough that the full 8-9 stage sequence still
# finishes in roughly 2-3.5 seconds total, long enough that each stage is
# actually readable rather than flashing past.
STAGE_SLEEP_SECONDS = 0.3

# Brief pause on the final message so it is visible for a moment before the
# caller's own st.rerun() (see streamlit_app.py's "Voer verificatie uit"
# button) redraws the page.
FINAL_SLEEP_SECONDS = 0.4


def _s(key: str, lang: str, **kwargs) -> str:
    """Look up a stage/result string for lang, falling back to nl if missing."""
    lang_dict = _SEARCH_STRINGS.get(lang, _SEARCH_STRINGS["nl"])
    text = lang_dict.get(key, _SEARCH_STRINGS["nl"].get(key, key))
    if kwargs:
        return text.format(**kwargs)
    return text


def render_search_animation(
    business: dict, db_path: str, lang: str, include_mailbox: bool = True
) -> None:
    """Play a short animated multi-source search, then run real verification.

    Renders every stage into one placeholder (created with ``st.empty()``)
    so each update replaces the previous stage instead of stacking. Calls
    ``scoring.run_all_sources(business, db_path, on_progress=..., \
    include_mailbox=include_mailbox)`` -- the progress callback advances the
    placeholder to the next stage immediately before each source actually
    runs -- followed by ``scoring.compute_score(business["uidn"], db_path)``,
    matching what the caller's previous direct-call handler already did.
    Does not call ``st.rerun()`` or clear any cache itself; the caller is
    expected to do both afterward, same as before.
    """
    business = business or {}

    placeholder = st.empty()

    def on_progress(source_name, index, total):
        placeholder.markdown(
            f"🔎 {_s('stage', lang, source=source_name, index=index + 1, total=total)}"
        )
        time.sleep(STAGE_SLEEP_SECONDS)

    scoring.run_all_sources(
        business, db_path, on_progress=on_progress, include_mailbox=include_mailbox
    )
    scoring.compute_score(business.get("uidn"), db_path)

    placeholder.markdown(f"✅ {_s('complete', lang)}")
    time.sleep(FINAL_SLEEP_SECONDS)
