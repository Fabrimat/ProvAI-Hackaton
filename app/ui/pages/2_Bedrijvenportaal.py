"""Business-facing self-service portal for the PROV-AI Schoten MVP.

This is a completely separate audience from the officer-facing dashboard in
``app/ui/streamlit_app.py``: here a business OWNER looks up their own
business and confirms/updates their contact details. It is an explicit MOCK
for demo purposes -- there is no real authentication or identity
verification (see the disclaimer rendered at the top of the page).

Streamlit's multipage-app convention picks this file up automatically
because it lives under ``app/ui/pages/`` next to ``streamlit_app.py`` -- no
wiring/imports needed in that file.

All user-visible text is in Dutch, per the same convention as the officer
tool. Code, comments and docstrings are in English.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# Ensure the repo root is on sys.path so `app.*` imports work regardless of
# the working directory Streamlit was launched from (same bootstrap pattern
# as app/ui/streamlit_app.py).
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.db import get_connection  # noqa: E402
from app.ingest import list_businesses  # noqa: E402

DB_PATH = str(REPO_ROOT / "data" / "provai.db")

EVIDENCE_SOURCE = "Bedrijf zelf (zelfbedieningsportaal)"


# --------------------------------------------------------------------------
# Small formatting helpers (mirrors app/ui/streamlit_app.py's conventions --
# defensive .get() style, since many fields are null in the source data).
# --------------------------------------------------------------------------

def business_name(b: dict) -> str:
    b = b or {}
    for key in ("commerciele_naam", "maatschappelijke_naam", "afgekorte_naam", "zoeknaam"):
        value = b.get(key)
        if value:
            return value
    uidn = b.get("uidn")
    return f"Onderneming {uidn}" if uidn is not None else "Onbekend bedrijf"


def format_address(b: dict) -> str:
    b = b or {}
    straat = b.get("kbo_straat") or ""
    huisnr = b.get("kbo_huisnr") or ""
    postcode = b.get("kbo_postcode") or ""
    gemeente = b.get("kbo_gemeente") or ""
    straat_huisnr = f"{straat} {huisnr}".strip()
    rest = " ".join(p for p in (postcode, gemeente) if p)
    parts = [p for p in (straat_huisnr, rest) if p]
    return ", ".join(parts) if parts else "Adres onbekend"


# --------------------------------------------------------------------------
# Lookup logic (pure Python, no Streamlit -- kept testable in isolation).
# --------------------------------------------------------------------------

def search_businesses(query: str, businesses: list) -> list:
    """Case-insensitive substring match on name fields and enterprise number.

    ``query`` is matched against commerciele_naam, maatschappelijke_naam,
    afgekorte_naam and ondernemingsnr. Returns the list of matching business
    dicts, unchanged order (as returned by ``list_businesses``).
    """
    needle = (query or "").strip().lower()
    if not needle:
        return []

    matches = []
    for b in businesses:
        fields = (
            b.get("commerciele_naam"),
            b.get("maatschappelijke_naam"),
            b.get("afgekorte_naam"),
            b.get("ondernemingsnr"),
        )
        for field in fields:
            if field and needle in str(field).lower():
                matches.append(b)
                break
    return matches


def insert_self_reported_evidence(
    business_uidn: int,
    is_active: bool,
    phone: str,
    email: str,
    note: str,
    db_path: str,
) -> None:
    """Insert one evidence row for a business's own self-reported update.

    Column names/order match app.db's real `evidence` table schema exactly:
    (business_uidn, source, signal, detail, created_at).
    """
    signal = "active" if is_active else "inactive"
    detail = (
        f"Bedrijf meldde zelf: {'actief' if is_active else 'gestopt'}. "
        f"Telefoon: {phone or 'niet opgegeven'}. "
        f"E-mail: {email or 'niet opgegeven'}. "
        f"Opmerking: {note or '-'}."
    )
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO evidence (business_uidn, source, signal, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (business_uidn, EVIDENCE_SOURCE, signal, detail, created_at),
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_current_data(business: dict) -> None:
    st.markdown("### Huidige gegevens in het register")
    st.markdown(f"**Naam:** {business_name(business)}")
    st.markdown(f"**Ondernemingsnummer:** {business.get('ondernemingsnr') or 'onbekend'}")
    st.markdown(f"**Adres:** {format_address(business)}")
    st.markdown(f"**Telefoonnummer:** {business.get('telefoonnummer') or 'niet geregistreerd'}")
    st.markdown(f"**E-mailadres:** {business.get('email') or 'niet geregistreerd'}")


def render_update_form(business: dict) -> None:
    uidn = business["uidn"]
    with st.form("update_form"):
        is_active_label = st.radio(
            "Is uw bedrijf nog actief?",
            ("Ja", "Nee"),
            horizontal=True,
        )
        phone = st.text_input(
            "Actueel telefoonnummer",
            value=business.get("telefoonnummer") or "",
            placeholder="bv. 03 123 45 67",
        )
        email = st.text_input(
            "Actueel e-mailadres",
            value=business.get("email") or "",
            placeholder="bv. info@mijnbedrijf.be",
        )
        note = st.text_area("Opmerking (optioneel)")
        submitted = st.form_submit_button("Gegevens bevestigen")

    if submitted:
        insert_self_reported_evidence(
            business_uidn=uidn,
            is_active=(is_active_label == "Ja"),
            phone=phone.strip(),
            email=email.strip(),
            note=note.strip(),
            db_path=DB_PATH,
        )
        st.success(
            "Bedankt! Uw gegevens zijn doorgegeven aan de gemeente en verschijnen in het "
            "dossier van uw bedrijf."
        )


def render_lookup_and_form(businesses: list) -> None:
    query = st.text_input(
        "Zoek uw bedrijf op naam of ondernemingsnummer",
        placeholder="bv. Bakkerij De Vries of 0123.456.789",
    )
    if not query:
        return

    matches = search_businesses(query, businesses)

    if not matches:
        st.warning(
            "Geen resultaten gevonden. Controleer de schrijfwijze van de naam of het "
            "ondernemingsnummer en probeer opnieuw."
        )
        return

    if len(matches) == 1:
        selected = matches[0]
    else:
        st.info("Meerdere resultaten gevonden, kies uw bedrijf:")
        options = {
            f"{business_name(b)} ({format_address(b)}, ondernemingsnr {b.get('ondernemingsnr') or 'onbekend'})": b
            for b in matches
        }
        label = st.selectbox("Kies uw bedrijf", sorted(options.keys()))
        selected = options[label]

    st.divider()
    render_current_data(selected)
    st.divider()
    render_update_form(selected)


def main() -> None:
    # Deliberately kept "centered" (unlike the officer-facing app and page 1,
    # both "wide"): this is a citizen self-service portal and should feel
    # like a simple form, not a dense officer dashboard.
    st.set_page_config(page_title="Bedrijvenportaal", layout="centered")

    # Hide Streamlit's own automatic sidebar page-list (testid stSidebarNav)
    # so only the main app's custom sidebar navigation is visible -- otherwise
    # both are stacked in the sidebar at once. Selector targets stSidebarNav
    # as of streamlit 1.38; re-check if streamlit is upgraded.
    st.markdown(
        "<style>[data-testid='stSidebarNav'] {display: none;}</style>",
        unsafe_allow_html=True,
    )

    # Back-link to the main entrypoint script, since this page's own
    # automatic nav entry is hidden above -- without this there would be no
    # visible way back to the main dashboard on camera.
    st.sidebar.page_link("streamlit_app.py", label="Terug naar hoofdscherm")

    st.title("Bedrijvenportaal: controleer en werk uw gegevens bij")
    st.info(
        "In deze versie van het portaal wordt niet ingelogd. In een volledige versie "
        "zou u hier inloggen met uw ondernemingsnummer of eID."
    )
    st.write(
        "Zoek hieronder uw bedrijf op en bevestig of uw gegevens nog kloppen. Uw melding "
        "wordt automatisch doorgegeven aan de gemeente."
    )

    businesses = list_businesses(DB_PATH)
    if not businesses:
        st.error("Geen bedrijven gevonden in de database.")
        return

    render_lookup_and_form(businesses)


if __name__ == "__main__":
    main()
