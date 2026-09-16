"""Simulated per-business verification-history timeline for the officer dossier.

Honesty note (read this before trusting any date this module prints): this
repo has no real verification log that stretches back over months. The
``evidence`` table only holds whatever rows the mock sources and the AI voice
stub have written since this demo started running, all effectively "today".
There is no genuine historical record of past checks to draw from. To make
a business's dossier feel like it has a real check history instead of a
sparse, empty-looking one, ``generate_history`` deterministically *fabricates*
a plausible-looking sequence of past check events for a given business,
spread over the last several months. Nothing here is read from or written to
the database, and nothing here is a real event that ever happened. It must
never be presented to an officer as an actual historical record; the UI layer
that renders this (``app/ui/history_view.py``) is required to show a visible
disclosure saying so.

Public API:
    generate_history(business_uidn, seed=None) -> list[dict]
"""

import random
from datetime import date, timedelta

# Fixed, small pool of source labels, matching the sources this codebase
# actually uses elsewhere (see app/sources/*.py and app/ui/streamlit_app.py),
# just written out in human-readable form for display purposes.
SOURCES = [
    "Google Maps",
    "Trustpilot",
    "Infobel / bedrijvengids",
    "OpenStreetMap",
    "AI voice check",
    "E-mail check",
]

SIGNALS = ["active", "inactive", "disagreement", "silent"]

# Cumulative-probability weighting so most simulated past checks look
# "active" (the common case for a still-open business), with the other
# signals appearing less often. Order must match SIGNALS above.
SIGNAL_WEIGHTS = [0.55, 0.15, 0.15, 0.15]

# One short, plausible English note per (source, signal) combination. Kept in
# English on purpose, exactly like app/seasonal.py's frozen `reason` field:
# this is raw stored data, and the UI layer decides how to localize or label
# it for the officer, not this module.
NOTES = {
    ("Google Maps", "active"): "Google Maps listing shows the business as open, hours look current.",
    ("Google Maps", "inactive"): "Google Maps listing is marked permanently closed.",
    ("Google Maps", "disagreement"): "Google Maps hours do not match what was found elsewhere.",
    ("Google Maps", "silent"): "Google Maps listing found but has no recent reviews or activity.",
    ("Trustpilot", "active"): "Trustpilot page has a recent review mentioning the business by name.",
    ("Trustpilot", "inactive"): "Trustpilot reviewers report the business has shut down.",
    ("Trustpilot", "disagreement"): "Trustpilot reviews are mixed on whether the business still operates.",
    ("Trustpilot", "silent"): "No Trustpilot page or reviews found for this business.",
    ("Infobel / bedrijvengids", "active"): "Directory listing confirmed, contact details match.",
    ("Infobel / bedrijvengids", "inactive"): "Directory listing has been removed.",
    ("Infobel / bedrijvengids", "disagreement"): "Directory address does not match the registered address.",
    ("Infobel / bedrijvengids", "silent"): "No directory listing found for this business.",
    ("OpenStreetMap", "active"): "OpenStreetMap shows a matching point of interest at this address.",
    ("OpenStreetMap", "inactive"): "OpenStreetMap point of interest tagged as disused or removed.",
    ("OpenStreetMap", "disagreement"): "OpenStreetMap tag for this address describes a different business.",
    ("OpenStreetMap", "silent"): "No matching point of interest found on OpenStreetMap.",
    ("AI voice check", "active"): "Call answered, person confirmed the business is still active.",
    ("AI voice check", "inactive"): "Call answered, person confirmed the business has closed.",
    ("AI voice check", "disagreement"): "Call reached someone who gave a different business name at this number.",
    ("AI voice check", "silent"): "No answer after the planned call attempts.",
    ("E-mail check", "active"): "E-mail reply received confirming the business is still active.",
    ("E-mail check", "inactive"): "E-mail bounced or reply confirmed the business has closed.",
    ("E-mail check", "disagreement"): "E-mail reply came from a different business than expected.",
    ("E-mail check", "silent"): "No reply received to the e-mail check.",
}

MIN_EVENTS = 4
MAX_EVENTS = 8

# Spread simulated events across roughly the last 6 to 12 months.
MIN_DAYS_AGO = 30 * 6
MAX_DAYS_AGO = 30 * 12


def _pick_signal(rng: random.Random) -> str:
    roll = rng.random()
    cumulative = 0.0
    for signal, weight in zip(SIGNALS, SIGNAL_WEIGHTS):
        cumulative += weight
        if roll < cumulative:
            return signal
    return SIGNALS[-1]


def generate_history(business_uidn, seed: int = None) -> list:
    """Deterministically fabricate a plausible past check-event timeline.

    Returns 4 to 8 simulated events, oldest first, each a dict:
        {"date": "YYYY-MM-DD", "source": str, "signal": str, "note": str}

    ``seed`` defaults to ``business_uidn`` itself, so the same business
    always gets the same simulated history on every call, regardless of how
    many times this is invoked. This is fabricated demo data only: see the
    module docstring for the full disclosure.
    """
    if seed is None:
        seed = business_uidn

    rng = random.Random(seed)

    n_events = rng.randint(MIN_EVENTS, MAX_EVENTS)

    today = date.today()
    used_dates = set()
    events = []
    for _ in range(n_events):
        days_ago = rng.randint(MIN_DAYS_AGO, MAX_DAYS_AGO)
        event_date = today - timedelta(days=days_ago)
        while event_date in used_dates:
            event_date -= timedelta(days=1)
        used_dates.add(event_date)

        source = rng.choice(SOURCES)
        signal = _pick_signal(rng)
        note = NOTES[(source, signal)]

        events.append(
            {
                "date": event_date.isoformat(),
                "source": source,
                "signal": signal,
                "note": note,
            }
        )

    events.sort(key=lambda e: e["date"])
    return events
