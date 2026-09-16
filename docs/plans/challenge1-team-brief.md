# Challenge 1 — Team Approval Brief

A 3-minute read. Approve or push back on scope *before* we commit to building. This is a summary, not a new plan — full detail lives in the docs linked at the bottom.

---

## 1. The pitch

We're building a verification funnel for local business activity: check each business the cheapest way first, and only pay for a more expensive check when the cheaper one is inconclusive.

The closing pitch line:

> We don't just guess whether a business is active — we check it three ways, cheapest first: scrape the public web, reach out directly if that's not enough, and fall back on a prediction from seasonal patterns only as a last resort. Then the officer decides, every time.

Supporting line, if the presentation layer (triage + discovery merged into one list) is built and demoed:

> One ranked list tells the officer, for one street, both which existing register entries need a second look and which storefronts aren't in the register at all — ordered by where the next ten minutes matter most.

## 2. What we are committing to build

**Priority 1 — Scrape (the foundation, never cut):**
- CSV ingestion (registry numbers as text), enterprise/establishment split via `Ondernemingsnr_maatsch_zetel`
- Multi-source scraping checks per address — Google Maps, Google reviews, OpenStreetMap, Trustpilot (mocked responses acceptable now, live APIs as credentials allow)
- A certainty marker (High/Medium/Low) from cross-source agreement, review UI skeleton, mandatory confirm/reject gating
- The street-sweep discovery extension, with its own graduated fallback: full automated sweep → narrowed hand-curated set → drop the extension (core scraping is never dropped, only this extension steps down)

**Priority 2 — Reach-out (escalation only, for addresses Priority 1 left uncertain):**
- **Phone**: the AI voice-agent call, triggered on Priority 1 conflict/silence, transcript captured as a reviewable evidence row
- **Email**: template + send + log mechanism (Dutch template text), logged as an evidence row with a "sent, awaiting reply" status — a live reply during the demo is not guaranteed

**The presentation layer (built on top of whichever priorities are working, not a fourth priority):**
- Triage worklist ranking (`priority_score = uncertainty × impact`) and the discovery queue merged into one ranked list
- The Dutch case-file paragraph per row (template-string fallback acceptable if no LLM call)

**Time-permitting, not full commitments:**
- **Priority 3 — Predict**: sector-level seasonal prior (buildable, ~30–45 min) plus review-text keyword mining (stretch, ~30–60 min) — build only once Priorities 1–2 are solid
- **Secondary/polish**: second-dataset reusability re-run (do this first if time allows — cheap, directly demonstrates criterion 3), snapshot-diff freshness screen

## 3. What's explicitly NOT being built — narrated only in the video

- Postal mail as a reach-out channel (turnaround too slow for a 6-hour build)
- Cross-municipality sharing of confirmed corrections
- Active learning from officer decisions
- Priority 3's layer-3 multi-year self-accumulating seasonal history (the dataset is a single snapshot — nothing to build here without fabricating evidence)
- Full live-API coverage beyond what's actually demoed (every mocked scraping call replaced by live calls, across all records)

## 4. Honest risk/effort callout

- **The discovery extension inside Priority 1 is genuinely expensive**: ~3–4.5 hours for the full automated sweep (POI enumeration, address-matching/fuzzy-diff, noise-mitigation). It has its own graduated fallback for exactly this reason — the core register-row scraping never depends on the sweep finishing.
- **Live API credentials (Google Maps / Trustpilot) may not materialize in time.** Mocked evidence must look convincing on camera; state plainly which sources are real vs mocked.
- **Reach-out costs real time or carries real delay**: a phone call needs credentials/consent framing, an email reply may never arrive inside the demo window. This is exactly why it's an escalation for addresses Priority 1 leaves uncertain, not a default run on every address.
- **Officer-facing text — including the email template — must be in Dutch**, even though this document is in English.
- **Cut-line order if behind schedule**: cut Priority 3 (prediction) first — it's a plausibility adjustment on existing evidence, not evidence itself. Then cut Priority 2's weaker channels, email before phone — if only one reach-out channel survives, keep phone, since it's already scoped as an MVP item and produces a reviewable transcript. Within Priority 1, step down the discovery extension's graduated path (full sweep → hand-curated set → drop) before touching anything else — the core scraping baseline is never cut. Secondary/polish items go last, and the second-dataset re-run should rarely be the one cut since it's the cheapest way to demonstrate criterion 3.

## 5. Sign-off checklist

- [ ] We agree Priority 1 (scraping, including its own core baseline) is the foundation and is never cut, even under time pressure.
- [ ] We understand reach-out (Priority 2) escalates only when scraping is inconclusive or silent — it is not a default run on every address.
- [ ] We accept postal mail is narrated-only, not built.
- [ ] We accept the officer-facing text — worklist rows, case-file paragraph, and the email template — will be in Dutch.
- [ ] We agree the discovery sweep may step down to the narrowed hand-curated set if the ~10:35 spike is behind schedule by the 14:00 checkpoint, and may be dropped entirely as a last resort without affecting Priority 1's core.
- [ ] We agree that if only one Priority-2 channel survives, it will be phone, not email.
- [ ] We accept Priority 3 (prediction) and the secondary/polish items (snapshot-diff, second-dataset re-run) are time-permitting, not commitments, and Priority 3 is the first thing cut if time is short.
- [ ] We understand Priority 3's layer-3 history, cross-municipality sharing, active learning, and full live-API coverage must never be presented in the video as if they were built.

## 6. Full detail, if you want it

Full architecture: `challenge1-plan.md`. Full brainstorm/rationale: `gamechanger-discovery-freshness.md`, `gamechanger-triage-and-briefing.md`. Full build sequence: `challenge1-action-plan.md`.
