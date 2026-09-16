"""Streamlit view: "Wat is er veranderd sinds <baseline_date>?" (freshness demo).

Renders the simulated snapshot-diff produced by ``app.freshness.compute_diff``.
This module only renders content; it does not call ``st.set_page_config``
and does not build its own sidebar navigation; it is meant to be invoked
from within an existing ``st.sidebar.radio`` branch of the main app (see
``app/ui/streamlit_app.py``).

All officer-visible text is in Dutch, per the rest of this app's UI
convention. See ``app.freshness`` module docstring for the honest
disclosure of what is simulated here and why.
"""

import streamlit as st

from app.freshness import compute_diff


def render(db_path: str = None) -> None:
    """Render the freshness/snapshot-diff demo view."""
    diff = compute_diff(db_path=db_path)

    st.header(f"Wat is er veranderd sinds {diff['baseline_date']}?")
    st.caption(
        "Ter demonstratie: dit scherm simuleert een eerdere momentopname, aangezien er "
        "nog maar één echte data-snapshot beschikbaar is. De 'huidige' gegevens zijn "
        "echt; de situatie op de eerdere datum is kunstmatig gesimuleerd om het concept "
        "van veranderingsdetectie te tonen."
    )

    new_businesses = diff.get("new_businesses") or []
    status_changes = diff.get("status_changes") or []
    closures_detected = diff.get("closures_detected") or []

    col1, col2, col3 = st.columns(3)
    col1.metric("Aantal nieuw", len(new_businesses))
    col2.metric("Aantal statuswijzigingen", len(status_changes))
    col3.metric("Aantal mogelijke sluitingen", len(closures_detected))

    st.caption(
        f"Aantal bedrijven toen: {diff.get('total_businesses_then')}, "
        f"nu: {diff.get('total_businesses_now')}."
    )

    st.divider()
    st.subheader(f"Nieuwe bedrijven ({len(new_businesses)})")
    if not new_businesses:
        st.info("Geen nieuwe bedrijven gevonden sinds de vorige momentopname.")
    else:
        st.dataframe(
            [
                {
                    "UIDN": e["uidn"],
                    "Naam": e["name"],
                    "Adres": e["address"],
                    "Datum inschrijving": e.get("datum_inschrijving") or "onbekend",
                }
                for e in new_businesses
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader(f"Statuswijzigingen ({len(status_changes)})")
    if not status_changes:
        st.info("Geen statuswijzigingen gevonden sinds de vorige momentopname.")
    else:
        st.dataframe(
            [
                {
                    "UIDN": e["uidn"],
                    "Naam": e["name"],
                    "Adres": e["address"],
                    "Was": e.get("old_status"),
                    "Nu": e.get("new_status"),
                }
                for e in status_changes
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader(f"Mogelijke sluitingen ({len(closures_detected)})")
    if not closures_detected:
        st.info("Geen mogelijke sluitingen gevonden sinds de vorige momentopname.")
    else:
        st.dataframe(
            [
                {
                    "UIDN": e["uidn"],
                    "Naam": e["name"],
                    "Adres": e["address"],
                    "Was": e.get("old_rechtstoestand"),
                    "Nu": e.get("new_rechtstoestand"),
                }
                for e in closures_detected
            ],
            use_container_width=True,
            hide_index=True,
        )
