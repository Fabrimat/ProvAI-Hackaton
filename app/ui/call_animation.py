"""Self-contained UI helper: a modal "phone call" experience for the AI
voice-agent reach-out, backed by the real deterministic outcome from
app.sources.voice_stub.

Kept separate from streamlit_app.py: it owns its own small translation dict
(_CALL_STRINGS, distinct from streamlit_app.py's TRANSLATIONS), its own
styled result card, and does not import anything from streamlit_app.py.

The call is rendered as a true modal overlay via st.dialog, with a small
call_dialog_stage state machine in st.session_state:
    "dialing" -> "connected" -> "ended"

Dialing plays once with a single blocking time.sleep() -- the CSS pulse
keeps animating on its own in the browser for that couple of seconds, no
reruns needed. The connected stage needs to stay responsive to the
officer clicking "Hang up" at any moment, so it is driven by a small
nested @st.fragment(run_every=...) ticker that polls elapsed time every
_CALL_TICK_SECONDS instead of sleeping through the whole stage in one go.
Ending the call (by timeout or Hang up) calls voice_stub.call() exactly
once per call session and shows a report card plus a Close button, which
closes the dialog by calling the ordinary, full-app st.rerun().
"""
import html
import random
import time

import streamlit as st

from app import scoring
from app.sources import voice_stub
from app.ui import theme

# The connected stage lasts this long before it ends on its own if the
# officer never clicks "Hang up". Single, clearly-named knob so this is
# trivial to tune later -- the final duration is still being decided.
CALL_CONNECTED_DURATION_SECONDS = 5

# The dialing stage plays for this long before it auto-advances to
# "connected".
CALL_DIALING_DURATION_SECONDS = 2

# How often the connected-stage ticker re-checks the clock and the Hang up
# button while the call is live.
_CALL_TICK_SECONDS = 0.5

# st.session_state keys, prefixed so they can't collide with anything else.
_STAGE_UIDN_KEY = "call_dialog_uidn"
_STAGE_KEY = "call_dialog_stage"
_CONNECTED_AT_KEY = "call_dialog_connected_at"
_OUTCOME_KEY = "call_dialog_outcome"

_CALL_STRINGS = {
    "nl": {
        "dialog_title": "Bellen: {name}",
        "dialing_label": "Bellen naar {phone}...",
        "hang_up": "Ophangen",
        "connected_label": "In gesprek",
        "result_active": "Actief bevestigd",
        "result_inactive": "Sluiting bevestigd",
        "result_silent": "Geen resultaat",
        "detail_label": "Detail",
        "unknown_business": "deze onderneming",
        "ended_heading": "Gesprek beëindigd",
        "added_to_record": "Toegevoegd aan het dossier van dit bedrijf.",
        "close_button": "Sluiten",
    },
    "en": {
        "dialog_title": "Calling: {name}",
        "dialing_label": "Dialing {phone}...",
        "hang_up": "Hang up",
        "connected_label": "On the call",
        "result_active": "Active confirmed",
        "result_inactive": "Closure confirmed",
        "result_silent": "No result",
        "detail_label": "Detail",
        "unknown_business": "this business",
        "ended_heading": "Call ended",
        "added_to_record": "Added to the business record.",
        "close_button": "Close",
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

# One shared pulse dot style for both the dialing (single dot) and
# connected (two dots) stages. Rendered as plain HTML/CSS so the pulse
# keeps animating in the browser between Python reruns. Uses the shared
# theme's accent color instead of a one-off blue, so the call modal reads as
# part of the same Business Pulse look as the rest of the app.
_PULSE_STYLE = f"""
<style>
.pav-call-dot {{
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background-color: {theme.COLOR_ACCENT};
    display: inline-block;
    margin: 0 9px;
    animation: pav-call-pulse 1.2s ease-in-out infinite;
}}
.pav-call-dot--b {{
    animation-delay: 0.35s;
}}
@keyframes pav-call-pulse {{
    0% {{ transform: scale(0.85); opacity: 0.65; box-shadow: 0 0 0 0 rgba(236, 48, 19, 0.45); }}
    50% {{ transform: scale(1.15); opacity: 1; box-shadow: 0 0 0 10px rgba(236, 48, 19, 0); }}
    100% {{ transform: scale(0.85); opacity: 0.65; box-shadow: 0 0 0 0 rgba(236, 48, 19, 0); }}
}}
</style>
"""

# Dialog chrome: sharp corners and a hairline border on the modal panel
# itself, matching the theme's "no rounded containers" rule (see
# app/ui/theme.py's _STYLE_BLOCK) -- best-effort selector since Streamlit
# does not expose a documented class name for the dialog panel, only the
# "stDialog" testid on its outer wrapper.
_DIALOG_CHROME_STYLE = f"""
<style>
[data-testid="stDialog"] > div {{
    border-radius: 0 !important;
    border: 1px solid {theme.COLOR_NEUTRAL_300} !important;
}}
</style>
"""


def _s(key: str, lang: str, **kwargs) -> str:
    """Look up a UI string for lang, falling back to nl if missing."""
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
    """A cosmetic local-looking phone number shown while dialing/connected.

    Deterministic per business uidn so the same dossier always shows the
    same number on replay. Purely decorative and separate from voice_stub's
    own outcome randomness (voice_stub seeds its own random.Random(uidn)
    independently).
    """
    rng = random.Random(uidn)
    return f"03-{rng.randint(100, 999)}-{rng.randint(1000, 9999)}"


def _render_dialing_pulse(phone: str, lang: str) -> None:
    st.markdown(
        _PULSE_STYLE
        + f"""
        <div style="text-align:center; padding: 22px 0;">
            <div class="pav-call-dot"></div>
            <div style="margin-top:14px; font-size:1.05em;">{html.escape(_s('dialing_label', lang, phone=phone))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_connected_pulse(name_html: str, phone: str, lang: str) -> None:
    st.markdown(
        _PULSE_STYLE
        + f"""
        <div style="text-align:center; padding: 20px 0;">
            <div>
                <span class="pav-call-dot"></span><span class="pav-call-dot pav-call-dot--b"></span>
            </div>
            <div style="margin-top:16px; font-size:1.15em; font-weight:600;">{name_html}</div>
            <div style="margin-top:2px; font-size:0.95em; color:#666;">{phone}</div>
            <div style="margin-top:6px; font-size:0.9em;">{html.escape(_s('connected_label', lang))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_ended_stage(business: dict, db_path: str, lang: str) -> None:
    """Log the real outcome (once) and show the report card + Close button.

    Guarded by _OUTCOME_KEY so voice_stub.call() -- which logs its own
    evidence row as a side effect -- runs exactly once per call session,
    even though this function is re-entered on later reruns once the
    stage is already "ended" (e.g. every time the Close button itself is
    rendered again).
    """
    outcome = st.session_state.get(_OUTCOME_KEY)
    if outcome is None:
        outcome = voice_stub.call(business, db_path)
        st.session_state[_OUTCOME_KEY] = outcome
        # Recompute the score now, right as the new evidence is logged, so
        # the dossier's badges/score are already up to date once the
        # officer closes this dialog.
        scoring.compute_score(business.get("uidn"), db_path)
        st.cache_data.clear()

    signal = outcome.get("signal") or "silent"
    detail = html.escape(str(outcome.get("detail") or ""))
    color = _RESULT_COLORS.get(signal, "#757575")
    result_label = _s(_RESULT_LABEL_KEYS.get(signal, "result_silent"), lang)

    st.markdown(theme.panel_header(_s("ended_heading", lang)), unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="border-left: 4px solid {color}; border-top: 1px solid {theme.COLOR_NEUTRAL_300};
                    border-right: 1px solid {theme.COLOR_NEUTRAL_300}; border-bottom: 1px solid {theme.COLOR_NEUTRAL_300};
                    padding: 10px 14px; margin: 10px 0; background-color: {theme.COLOR_NEUTRAL_100};">
            <span style="color:{color}; font-weight:700;">{result_label}</span><br/>
            <span style="font-size:0.92em;">{_s('detail_label', lang)}: {detail}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(_s("added_to_record", lang))

    if st.button(_s("close_button", lang), key="call_dialog_close", use_container_width=True):
        # A plain, default-scope st.rerun() here reruns the full script.
        # Since the dialog is only (re)opened by the "Call this business"
        # button click that triggered open_call_dialog(), and that button
        # is not clicked again on this rerun, the dialog does not reopen --
        # this is what actually closes it.
        st.rerun()


def _run_connected_stage(business: dict, db_path: str, lang: str, name_html: str, phone: str) -> None:
    """Poll the connected stage every _CALL_TICK_SECONDS via a nested,
    auto-rerunning fragment, so both the Hang up button and the
    CALL_CONNECTED_DURATION_SECONDS timeout are checked in near real time
    instead of behind one long blocking sleep.
    """
    stage_now = st.session_state.get(_STAGE_KEY)
    # Stop scheduling further ticks once the call has ended -- the ticker
    # below is only recreated by a widget interaction (e.g. Close) after
    # that point, not by the timer.
    tick_interval = None if stage_now == "ended" else _CALL_TICK_SECONDS

    @st.fragment(run_every=tick_interval)
    def _connected_ticker() -> None:
        stage = st.session_state.get(_STAGE_KEY)
        if stage == "ended":
            _render_ended_stage(business, db_path, lang)
            return
        if stage != "connected":
            return

        # Rendered into its own placeholder so it can be explicitly cleared
        # below if this same tick also ends the call -- otherwise the pulse
        # would stay stacked above the report instead of being replaced by
        # it (a fragment only clears its container between separate
        # reruns, not partway through one execution).
        pulse_area = st.empty()
        with pulse_area.container():
            _render_connected_pulse(name_html, phone, lang)
            hung_up = st.button(
                _s("hang_up", lang), key="call_dialog_hangup_connected", use_container_width=True
            )
        started_at = st.session_state.get(_CONNECTED_AT_KEY) or time.time()
        elapsed = time.time() - started_at

        if hung_up or elapsed >= CALL_CONNECTED_DURATION_SECONDS:
            pulse_area.empty()
            st.session_state[_STAGE_KEY] = "ended"
            _render_ended_stage(business, db_path, lang)

    _connected_ticker()


def open_call_dialog(business: dict, db_path: str, lang: str) -> None:
    """Open the call modal for `business` and (re)start its state machine.

    This is only ever called from the Dossier view's "Call this business"
    button handler, i.e. only on the single script run in which that
    button was actually clicked. Every call therefore represents a
    genuinely fresh call attempt, so the state machine is unconditionally
    reset here (uidn, stage, connected timestamp, outcome) -- re-opening
    never shows a stale stage or outcome from a previous call, whether for
    the same business or a different one.
    """
    business = business or {}
    uidn = business.get("uidn")
    st.session_state[_STAGE_UIDN_KEY] = uidn
    st.session_state[_STAGE_KEY] = "dialing"
    st.session_state[_CONNECTED_AT_KEY] = None
    st.session_state[_OUTCOME_KEY] = None

    name = _business_name(business, lang)
    name_html = html.escape(str(name))
    phone = _fake_phone_number(uidn)
    title = _s("dialog_title", lang, name=name)

    @st.dialog(title)
    def _call_dialog() -> None:
        st.markdown(_DIALOG_CHROME_STYLE, unsafe_allow_html=True)
        stage = st.session_state.get(_STAGE_KEY, "dialing")

        if stage == "dialing":
            # Rendered into its own placeholder so it can be explicitly
            # cleared below before falling through to the next stage in
            # this same pass -- otherwise it would stay stacked above
            # whatever renders next instead of being replaced by it.
            dialing_area = st.empty()
            with dialing_area.container():
                _render_dialing_pulse(phone, lang)
                hung_up = st.button(
                    _s("hang_up", lang), key="call_dialog_hangup_dialing", use_container_width=True
                )
            if hung_up:
                dialing_area.empty()
                st.session_state[_STAGE_KEY] = "ended"
                stage = "ended"
            else:
                # One blocking sleep for the whole dialing stage: the CSS
                # keyframe pulse above keeps animating on its own in the
                # browser, no extra reruns needed just to keep it moving.
                time.sleep(CALL_DIALING_DURATION_SECONDS)
                dialing_area.empty()
                st.session_state[_STAGE_KEY] = "connected"
                st.session_state[_CONNECTED_AT_KEY] = time.time()
                stage = "connected"

        if stage == "connected":
            _run_connected_stage(business, db_path, lang, name_html, phone)
            return

        if stage == "ended":
            _render_ended_stage(business, db_path, lang)

    _call_dialog()
