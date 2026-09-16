# Game-changer brainstorm: Discovery & Freshness — Challenge 1

**Event:** PROV-AI Public AI Hackathon, 16 Sept 2026, AP Hogeschool Campus Spoor Noord, Antwerp
**Grounded in:** `agent.md` (Challenge 1 brief, Examples & Technical Guidance, Starter Files & Source Guide) and the real files in the repo root: `schoten-kbo-1000-2026-09-07.csv`, `source-metadata.json`.

**What this document is.** This is a **brainstorm / proposal doc**, not the build plan. The team's actual, already-agreed build plan is `docs/plans/challenge1-plan.md` — it already covers multi-source verification (Google Maps/OSM/Trustpilot), an AI voice-agent escalation call when sources disagree, a per-source evidence-breakdown review table, mandatory officer confirm/reject before anything is final, and a second-dataset re-run to prove reusability. This document does **not** repeat any of that. It proposes additional, genuinely differentiated ideas along the "discovery" and "freshness" angle of Challenge 1's three success criteria (agent.md, Challenge 1 brief, "Three success criteria"). Nothing here is a commitment; it is material for the team to pick from, time permitting.

---

## Idea 1 — Proactive street sweep (the discovery inversion)

### What it is

The worked example in agent.md's own Examples & Technical Guidance page already shows one row of "reactive" ghost-detection: Voorbeeldstraat 20, "Kapsalon Voorbeeld (niet in register op dit adres)," where a sign and reviews mention the address but the register has no entry there, labelled *"Nazicht: vestiging ontbreekt of adres verkeerd"* (agent.md, Source 3, "Optional worked example"). `challenge1-plan.md`'s own MVP flow (§2, step 2–3) is built the same way: start from the register rows for a street, then check each one against public sources. That direction — **register row → does evidence support it?** — is the version a judge has already seen demoed in the brief itself. It answers "is this listed business real?" but it structurally cannot find a storefront that was never listed at all, because the loop never leaves the register's own row list.

Idea 1 inverts the direction: **evidence → does the register have a matching row at all?**

1. **Enumerate real-world points of interest (POIs) on the chosen street first, independent of the register.** Query OSM (Overpass API, free, no key) and/or Google Maps Places for every shop/office/service tagged on that street segment — addresses, names, categories, photos, review counts — before looking at a single KBO row.
2. **Diff that POI list against the KBO register rows for the same street.** Match by address (and loosely by name where possible).
3. **Surface every POI that has no register match at all** into a dedicated **discovery queue** — a distinct list from the "existing row, evidence conflicts" table in `challenge1-plan.md`. This is the harder, more valuable half of success criterion 1's "find missing... records" (agent.md, Challenge 1 brief): a truly missing register entry, not just a stale one.

Concretely, this queue looks like a second table alongside the existing evidence-breakdown table:

| POI (source) | Address | Category | Evidence signals | Register match | Status |
|---|---|---|---|---|---|
| "Kapsalon XYZ" (Google Maps) | Paalstraat 8 | Hairdresser | Maps listing + 4 recent reviews citing this address | None found | Nazicht: mogelijk niet geregistreerd op dit adres |
| "Café ABC" (OSM) | Paalstraat 11 | Café | OSM tag + Maps listing, both showing "open" | None found | Nazicht: mogelijk niet geregistreerd op dit adres |

### Why this is more novel than the reactive version already in the plan

`challenge1-plan.md` never claims to solve this direction — its Section 2 table and Section 3.2 enrichment step both start from register rows and check them outward. A reviewer who has read the challenge brief and its worked example will recognise "check existing rows for missing evidence" as the expected, already-demonstrated pattern. Starting from the street's real-world footprint and working *backward* to the register is the half of "missing... records" that a team verifying existing rows will structurally never surface, because a business with zero register presence never appears as a row to check in the first place. That inversion — not the evidence-gathering mechanics, which reuse the same OSM/Maps sources already planned — is the differentiator.

### Concrete workflow

1. Officer picks a street (same selection step as `challenge1-plan.md` §2, step 1 — reuse it, don't rebuild it).
2. System calls Overpass API for that street's `shop=*`/`office=*`/`amenity=*` tagged nodes, and (where credentials allow) Google Places nearby-search restricted to the street's bounding box.
3. System normalizes both POI lists to `{name, address, category, source, evidence links}`.
4. System address-matches each POI against the KBO rows already loaded for that street (reusing `challenge1-plan.md`'s ingestion step — same CSV, same address columns `KBO_Straat`/`KBO_Huisnr` or `AR_straat`/`AR_huisnr`).
5. Unmatched POIs go into the discovery queue, subject to the noise-mitigation rules below.
6. Officer reviews the queue through the **same confirm/reject UI** as the register-row table (Section 3.3 of `challenge1-plan.md`) — no separate approval path, no auto-publishing.

### Noise-mitigation design (this is the part that must be airtight)

A naive POI-diff will flood the officer with false positives — mismatched address formats, POIs slightly off the exact street segment, duplicate listings, businesses that *are* registered but under a different trade name than what Maps/OSM displays. To keep this credible and useful rather than noisy:

- **Require at least 2 independent evidence signals per POI before it enters the queue** — e.g. both OSM tag presence *and* a Google Maps listing, or a Maps listing *and* at least one dated review mentioning the address. A single unconfirmed OSM tag or a single stale Maps pin is not enough on its own.
- **Cap the discovery queue size** shown to the officer at once (e.g. top N by evidence strength/recency) rather than dumping every unmatched POI — a street may have dozens of address-matching near-misses; surface the strongest candidates first and let the officer ask for more.
- **Label every row "Nazicht" (Dutch: "to review/suggestion") — never as an assertion.** The tool must never say "this business exists" or "this business is unregistered." It says only "real-world evidence found here; no matching register row found; please check." This mirrors the exact phrasing discipline agent.md's own worked example uses for its one reactive ghost row (*"Nazicht: vestiging ontbreekt of adres verkeerd"*, Source 3) and matches Instruction 4 in agent.md's own assistant-instructions section: never invent or assert what isn't verified.
- **Feed the same confirm/reject flow as the rest of the tool, with no separate "auto-add" path.** A discovery-queue row is a suggestion for a human to investigate (e.g. via a follow-up visit, a phone call, or address-fuzzy-matching against a trade name already in the register) — never something the tool writes back to any record on its own.

### Feasibility in remaining build time (be honest)

This needs real engineering beyond what `challenge1-plan.md`'s MVP already budgets for, mainly because it adds a second data source integration (Overpass/Places POI enumeration, not just per-address lookup) plus a nontrivial address-matching/fuzzy-diff step:

- POI enumeration via Overpass API for one street segment: **~30–45 min** (Overpass is free/keyless, so this is mostly query-writing and bounding-box selection, not credential setup).
- Google Places nearby-search integration (if pursued live rather than mocked): **~45–60 min**, contingent on API key availability — same credential caveat as `challenge1-plan.md` §6 applies here (mock first, wire in real calls opportunistically).
- Address normalization + matching logic (KBO address fields vs. POI address strings, handling house-number/street-name variants): **~60–90 min** — this is the fiddliest part and the most likely to eat the schedule.
- Discovery-queue UI (a second table/tab reusing the existing review-table component and confirm/reject action): **~30–45 min** if the main review UI already exists.
- Noise-mitigation logic (2-signal gate, cap, labeling): **~30 min**, mostly a filter on top of the matching step.

**Total realistic estimate: roughly 3–4.5 hours** for a working version covering one street with a handful of discovered POIs — i.e., this is a genuine second half-day feature, not a "few minutes" add-on. Given `challenge1-plan.md`'s ~6-hour budget is already committed to its own MVP (ingestion, multi-source verification, voice-agent escalation, review UI, second-dataset re-run), Idea 1 should be scoped honestly as **a stretch goal built after the core MVP is solid**, or as a narrowed demo (one street, one or two manually-curated discovery-queue rows shown working end-to-end) if time is tight, rather than a fully generalized POI-diff engine.

### How it maps to criterion 1

Criterion 1 is "find missing or inaccurate records, flag potentially inactive entries, enrich the data with evidence and confidence" (agent.md, Challenge 1 brief). `challenge1-plan.md` already covers "inaccurate" and "potentially inactive." Idea 1 is aimed squarely and only at "**missing**" — the one word in criterion 1 that the reactive, register-row-first design cannot fully answer on its own.

---

## Idea 2 — Living registry as a snapshot diff (not a scheduler)

### What it is

Do not narrate a periodic-scheduler story ("the tool re-checks sources every night in production") — with no live deployment to point to, that reads as vaporware in a 3-minute video and cannot be demonstrated on camera. Instead, make "freshness" a concrete, demoable **screen**, built and shown within the hackathon itself:

1. Take the real dataset already in the repo (`schoten-kbo-1000-2026-09-07.csv`) as the "current" snapshot.
2. Create a **deliberately perturbed second copy** simulating an earlier snapshot — e.g. flip a `Rechtstoestand` (legal status) value on a couple of rows, change a `Startdatum`/`Datum_inschrijving` on a couple more (both are present in the CSV's 30 columns; `Datum_stopzetting` is GeoJSON-only and not available if working from the CSV), remove a couple of rows entirely (simulating "not yet registered as of the earlier date"), and/or add a couple of rows that don't exist in the "current" file (simulating "deregistered since"). This can be done by hand in a spreadsheet or with a short script — either is fine, the point is that it's a controlled, explainable perturbation, not a real second retrieval.
3. Run the **exact same ingestion + verification pipeline** (the one `challenge1-plan.md` §3 already builds) against both files independently.
4. Produce a concrete **"what changed since 7 September" delta screen**: new entries, status flips, entries that dropped out — computed by diffing the two pipeline outputs, not narrated.

This turns freshness from a claim ("our approach would stay up to date") into an on-camera demoed screen ("here is what changed between these two runs of the same tool").

### Exact demo mechanism

- Two input files: `schoten-kbo-1000-2026-09-07.csv` (real, "now") and a hand-perturbed `schoten-kbo-<earlier-date>-simulated.csv` (clearly labelled as a simulated earlier snapshot, not a real historical retrieval — this must be stated plainly in the video per the Submission FAQ's rule on labelling mocked/unfinished parts, agent.md Source 6).
- Same ingestion/split/enrichment code path from `challenge1-plan.md` §3, run twice, once per file.
- A diff step comparing the two runs' outputs row-by-row on `Ondernemingsnr` (registry number, kept as text per the existing "import as text" caveat): rows present only in the "now" file → **new**; rows present only in the "earlier" file → **dropped out**; rows present in both with a changed `Rechtstoestand`/`Startdatum`/other tracked field → **status flip**.
- A simple delta screen: three short lists (new / flipped / dropped), each row linking back to the same evidence/review mechanics already built for the main table — so a "new" or "flipped" row can be inspected and confirmed/rejected exactly like any other row, not treated as an automatic fact.

### Feasibility

This should be genuinely quick relative to Idea 1:

- Hand-perturbing 4–6 rows in a spreadsheet copy: **~10–15 minutes**.
- Running the existing pipeline twice (no new pipeline code needed if ingestion is already built per `challenge1-plan.md` §3): **near-zero additional time**, assuming the pipeline already accepts a CSV path as a parameter.
- Writing the diff logic (compare two output sets by registry number, bucket into new/flipped/dropped): **~30–60 minutes** for a straightforward implementation.
- A minimal delta-screen UI (three lists, reusing existing row/evidence components): **~30–45 minutes**.

**Total realistic estimate: well under two hours**, and most of that is optional polish — the core diff logic could be a console/table output in a pinch and still make the point on camera.

### How it maps to criterion 3

Criterion 3 is "fresh and reusable — show how the data stays up to date and how the approach adapts to another municipality or province" (agent.md, Challenge 1 brief). `challenge1-plan.md`'s own MVP already demonstrates the "reusable" half concretely, via a second-dataset re-run proving the pipeline is municipality-agnostic (§4, §5 criterion 3). Idea 2 demonstrates the "stays up to date" half with equal concreteness: instead of narrating that the approach *would* catch changes if run again later, it actually runs the pipeline against two time points and shows a real delta — closing the one part of criterion 3 that `challenge1-plan.md` currently leaves as a stretch goal ("automated periodic re-checks against the public source," §4 stretch list) with something fully demoable today.

---

## Idea 3 — Cross-municipality stretch (narrated only, one paragraph max)

Only 28 of the 543 establishments in the Schoten sample have their parent enterprise present in the same 1,000-row sample (`source-metadata.json`, `establishment_rows_with_parent_number: 543` against the dataset's total; confirmed narratively in `challenge1-plan.md` §3.1 and §6: "only 28 of the 543 establishments have their parent among these 1,000 rows") — meaning most registered seats for Schoten's establishments sit in municipalities outside the sample entirely. As a narrated stretch idea only — explicitly **not something to build in the hackathon** — one could imagine that when an officer in one municipality confirms or corrects an enterprise record (via the confirm/reject flow already in `challenge1-plan.md`), that confirmation could become visible to an officer in a different municipality where the same enterprise (by `Ondernemingsnr`) has a different establishment, so verification effort isn't duplicated across municipal boundaries. This would require shared infrastructure, data-sharing agreements and consent questions well beyond a one-day build, and is mentioned here purely to signal the idea's direction for a future iteration.

---

## The winning synthesis

Idea 1 (the proactive discovery sweep) and the officer-triage concept from the companion doc `docs/plans/gamechanger-triage-and-briefing.md` (written in parallel — its contents are not reproduced or assumed here beyond its filename) combine naturally into **one screen**: a single prioritized worklist for the chosen street that mixes known-uncertain register entries needing review with newly-discovered, unregistered storefronts needing a first look. In one sentence a judge could repeat back: **one worklist, one street, both directions of "what's wrong here" — the businesses the register got wrong, and the businesses the register never knew about.**
