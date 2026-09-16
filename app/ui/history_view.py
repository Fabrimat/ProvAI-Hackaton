"""Streamlit rendering helper: per-business verification-history timeline.

Renders a merged timeline of simulated past check events (from
``app.history.generate_history``) and the real ``evidence`` rows for one
business, oldest to newest. The simulated portion is fabricated demo data,
never real history: see ``app.history`` module docstring for the full
disclosure. This module always shows a visible caption saying so.

Self-contained on purpose: it does not import from or depend on
``app/ui/streamlit_app.py``, and keeps its own small local translation dict
for its own UI chrome instead of touching that file's ``TRANSLATIONS``.
"""

import html

import streamlit as st

from app.history import generate_history

# Local translation strings for this view only. Not the same dict as
# app/ui/streamlit_app.py's TRANSLATIONS; kept separate and small on purpose.
_HISTORY_STRINGS = {
    "nl": {
        "header": "Verificatiegeschiedenis",
        "disclosure": (
            "Let op: het oudere deel van deze tijdlijn is een schatting op basis van "
            "beschikbare gegevens, geen vastgelegde historische controles."
        ),
        "unknown_source": "onbekende bron",
        "date_unknown": "datum onbekend",
        "signal_active": "actief",
        "signal_inactive": "inactief",
        "signal_disagreement": "tegenstrijdig",
        "signal_silent": "stil",
    },
    "en": {
        "header": "Verification history",
        "disclosure": (
            "Note: the older part of this timeline is an estimate based on "
            "available data, not recorded historical checks."
        ),
        "unknown_source": "unknown source",
        "date_unknown": "date unknown",
        "signal_active": "active",
        "signal_inactive": "inactive",
        "signal_disagreement": "disagreement",
        "signal_silent": "silent",
    },
}

# Local color palette, kept separate from app/ui/streamlit_app.py's
# SIGNAL_COLORS on purpose (this module must not import from that file).
_SIGNAL_COLORS = {
    "active": "#2e7d32",
    "inactive": "#c62828",
    "disagreement": "#ef6c00",
    "silent": "#757575",
}


def _strings(lang: str) -> dict:
    return _HISTORY_STRINGS.get(lang, _HISTORY_STRINGS["nl"])


def _build_timeline(business_uidn, evidence_rows: list) -> list:
    """Merge simulated past events with real evidence rows, oldest first."""
    timeline = []

    for event in generate_history(business_uidn):
        timeline.append(
            {
                "date": event["date"],
                "source": event["source"],
                "signal": event["signal"],
                "note": event["note"],
                "simulated": True,
            }
        )

    for row in evidence_rows or []:
        created_at = row.get("created_at")
        date_str = str(created_at)[:10] if created_at else ""
        timeline.append(
            {
                "date": date_str,
                "source": row.get("source"),
                "signal": row.get("signal") or "silent",
                "note": row.get("detail") or "",
                "simulated": False,
            }
        )

    timeline.sort(key=lambda item: item["date"] or "")
    return timeline


def _render_event(item: dict, strings: dict) -> None:
    signal = item.get("signal") or "silent"
    color = _SIGNAL_COLORS.get(signal, "#757575")
    label = strings.get(f"signal_{signal}", signal)

    # source/note are untrusted free text (mock data today, real
    # scraped/API text once live adapters are enabled) interpolated into
    # unsafe_allow_html=True markdown, escape it. color/label/tag come from
    # fixed whitelists above, safe as-is.
    source = html.escape(str(item.get("source") or strings["unknown_source"]))
    note = html.escape(str(item.get("note") or ""))
    date_display = html.escape(str(item.get("date") or strings["date_unknown"]))

    st.markdown(
        f"""
        <div style="border-left: 4px solid {color}; padding: 6px 10px; margin-bottom: 6px;
                    background-color: rgba(127,127,127,0.08); border-radius: 4px;">
            <b>{source}</b>
            <span style="color:{color}; font-weight:600;">{label}</span>
            <span style="float:right; color:#888; font-size:0.85em;">{date_display}</span><br/>
            <span style="font-size:0.9em;">{note}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_history(business: dict, evidence_rows: list, lang: str, db_path: str = None) -> None:
    """Render a merged simulated + real verification-history timeline.

    ``business`` is a business row dict (needs at least ``uidn``),
    ``evidence_rows`` is the real evidence for that business,
    ``lang`` is ``"nl"`` or ``"en"``. ``db_path`` is accepted for interface
    symmetry with other render helpers in this app but is not used: the
    simulated part of the history needs no database access (see
    ``app.history``), and the real part is passed in already loaded.
    """
    business = business or {}
    strings = _strings(lang)

    st.subheader(strings["header"])
    st.caption(strings["disclosure"])

    timeline = _build_timeline(business.get("uidn"), evidence_rows)
    for item in timeline:
        _render_event(item, strings)
