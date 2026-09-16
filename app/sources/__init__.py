"""Evidence-gathering sources for the PROV-AI Schoten verification tool.

Each submodule exposes a single ``check(business: dict) -> dict`` (or
``call`` for the voice stub) function that returns
``{'signal': ..., 'detail': ...}`` where ``signal`` is one of
``'active'``, ``'inactive'``, ``'silent'``, ``'disagreement'``.

Every source is self-contained: it inserts its own row into the
``evidence`` table (via ``app.db.get_connection``) as part of running the
check, so callers don't need to do any extra bookkeeping.

- ``gmaps_mock`` / ``trustpilot_mock`` / ``directory_mock`` -- deterministic
  mocks (Priority 1, scraping stand-ins) that fall back automatically from
  a real API attempt (Google Places / Trustpilot Business Units / Infobel)
  when no API key is configured or the real call fails.
- ``osm_source`` -- a real call to the free, keyless OpenStreetMap
  Overpass API (Priority 1, real).
- ``voice_stub`` / ``email_stub`` -- deterministic stubs for the
  Priority 2 reach-out channels (phone, email).

See ``docs/plans/challenge1-action-plan.md`` for the verification funnel
these sources implement (scrape -> reach out -> predict).
"""
