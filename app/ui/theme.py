"""Shared visual theme for the Streamlit app, matching the Business Pulse
mockup's Modernist design system (see
``docs/design/business-pulse-mockup/_ds/modernist-*/styles.css`` and
``docs/design/business-pulse-mockup/PROV-AI Demo.dc.html``).

Self-contained on purpose: it does not import from or depend on
``app/ui/streamlit_app.py``, the same pattern as ``app/ui/history_view.py``,
so any view module can import and call it without pulling in app state.

Exports:
    inject()               -- injects the global <style> block, call once
                               near the top of main().
    panel_header(...)      -- HTML snippet for a mockup ".ph" panel header bar.
    stat_block_html(...)   -- HTML snippet for one ".stat" cell.
    stat_row_html(...)     -- HTML snippet wrapping stat cells in a row.
    Color constants (COLOR_*) -- the mockup's semantic and raw token values.
"""

import html

import streamlit as st

# --------------------------------------------------------------------------
# Color tokens, mirrored from the mockup's :root block. Raw neutral/accent
# ramp values other view modules may need, plus clearly named semantic
# aliases for the status/signal mapping used on the map legend and the
# ".stg"/".tag" classes: unknown = neutral outline, high priority/conflict =
# full accent, medium/needs-a-look = light accent, low/verified = dark
# neutral. Deliberately not a red/orange/green traffic light.
# --------------------------------------------------------------------------

COLOR_ACCENT = "#ec3013"
COLOR_ACCENT_LIGHT = "#ff9783"  # accent-400, "needs a look" / medium signal
COLOR_ACCENT_DARK = "#ae1800"  # accent-700, hover/link text tone
COLOR_SETTLED = "#2d2b2b"  # neutral-900, "verified active" / low priority
COLOR_UNKNOWN = "#9b9797"  # neutral-500, "status unknown" outline dot

COLOR_NEUTRAL_100 = "#f8f4f4"
COLOR_NEUTRAL_200 = "#eae7e7"
COLOR_NEUTRAL_300 = "#d7d3d3"
COLOR_NEUTRAL_700 = "#605d5d"
COLOR_NEUTRAL_800 = "#444141"
COLOR_NEUTRAL_900 = "#2d2b2b"

COLOR_ACCENT_100 = "#fff2ef"
COLOR_ACCENT_600 = "#dd2b0f"
COLOR_ACCENT_700 = "#ae1800"

_STYLE_BLOCK = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&display=swap');

/* Headings, Archivo 800 with tight letter-spacing, matching the mockup. */
h1, h2, h3,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {
    font-family: "Archivo", system-ui, sans-serif;
    font-weight: 800;
    letter-spacing: -0.015em;
}

/* Sharp corners everywhere: no rounded buttons, inputs, containers. */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button,
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div,
[data-testid="stExpander"],
[data-testid="stExpander"] details,
[data-testid="stDataFrame"],
[data-testid="stTable"],
[data-testid="stMetric"],
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stAlert"],
[data-testid="stTabs"] {
    border-radius: 0 !important;
}

/* Primary buttons: mockup's .btn-primary / .btn-primary:hover. */
[data-testid="stButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background-color: #ec3013;
    border-color: #ec3013;
    color: #ffffff;
}
[data-testid="stButton"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
    background-color: #dd2b0f;
    border-color: #dd2b0f;
}
[data-testid="stButton"] button[kind="primary"]:active,
[data-testid="stFormSubmitButton"] button[kind="primary"]:active {
    background-color: #ae1800;
    border-color: #ae1800;
}

/* Tabs: thin bottom border underline look, best-effort. */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    border-bottom: 1px solid #d7d3d3;
    gap: 0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 0;
}
[data-testid="stTabs"] [aria-selected="true"] {
    border-bottom-color: #ec3013 !important;
    color: #201e1d;
}
</style>
"""


def inject() -> None:
    """Render the shared style block. Call once near the top of main().

    Pure ``st.markdown`` side effect, no session-state reads/writes, safe to
    call from any script context that already has an active Streamlit run.
    """
    st.markdown(_STYLE_BLOCK, unsafe_allow_html=True)


def panel_header(label: str, meta: str = "") -> str:
    """Return (does not render) the HTML for a mockup ".ph" panel header bar.

    ``label`` is shown left, uppercase, micro-label styled. ``meta`` is an
    optional small right-aligned string (e.g. a count or a date).
    """
    label_html = html.escape(label)
    meta_html = (
        f'<span style="font-size:11px;color:#605d5d;">{html.escape(meta)}</span>'
        if meta
        else ""
    )
    return (
        '<div style="padding:10px 14px;border-bottom:1px solid #d7d3d3;'
        'display:flex;justify-content:space-between;align-items:baseline;'
        'gap:12px;background:#f8f4f4;">'
        f'<span style="font-size:11px;letter-spacing:.06em;text-transform:uppercase;'
        f'color:#605d5d;">{label_html}</span>'
        f"{meta_html}"
        "</div>"
    )


def stat_block_html(label: str, value: str, caption: str = "", accent: bool = False) -> str:
    """Return (does not render) the HTML for one mockup ".stat" cell."""
    label_html = html.escape(label)
    value_html = html.escape(value)
    color = "#ec3013" if accent else "inherit"
    caption_html = (
        f'<div style="font-size:12px;color:#605d5d;">{html.escape(caption)}</div>'
        if caption
        else ""
    )
    return (
        '<div style="padding:12px 14px;">'
        f'<div style="font-size:11px;letter-spacing:.06em;text-transform:uppercase;'
        f'color:#605d5d;">{label_html}</div>'
        f'<div style="font-family:\'Archivo\',system-ui,sans-serif;font-weight:800;'
        f'font-size:28px;line-height:1.15;letter-spacing:-.02em;color:{color};">'
        f"{value_html}</div>"
        f"{caption_html}"
        "</div>"
    )


def stat_row_html(blocks: list) -> str:
    """Wrap ``stat_block_html`` outputs in the mockup's stat-row container
    with hairline dividers between cells.
    """
    last = len(blocks) - 1
    cells = "".join(
        '<div style="flex:1;min-width:150px;'
        + ("" if i == last else "border-right:1px solid #eae7e7;")
        + f'">{block}</div>'
        for i, block in enumerate(blocks)
    )
    return (
        '<div style="display:flex;flex-wrap:wrap;border:1px solid #d7d3d3;background:#ffffff;">'
        f"{cells}"
        "</div>"
    )
