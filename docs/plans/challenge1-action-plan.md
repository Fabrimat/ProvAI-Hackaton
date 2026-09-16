# Challenge 1 · Action Plan: Prioritized Build Sequence for the Day

**Event:** PROV-AI Public AI Hackathon, Wednesday 16 September 2026, AP Hogeschool Campus Spoor Noord, Antwerp (agent.md, Source 1).
**Grounded in:** `agent.md` (the participant-guide snapshot) and the three planning documents this file reorganizes: `docs/plans/challenge1-plan.md` (the foundation build plan), `docs/plans/gamechanger-discovery-freshness.md` and `docs/plans/gamechanger-triage-and-briefing.md` (brainstorm docs). Any factual claim traces to `agent.md`/`source-metadata.json` or is explicitly marked as the team's own proposed idea.

**What this document is.** This is **not** a fourth brainstorm document and it does not duplicate the detail already written up elsewhere. For architecture, MVP scope, the officer workflow sketch, data caveats and open questions, see `challenge1-plan.md`; for the full reasoning behind each game-changer idea, see the two gamechanger docs. This file is the **reorganization/sequencing layer**, structured around one concrete idea: **verify each business three ways, cheapest and fastest first, escalating only when the cheaper method is inconclusive**: scrape, then reach out, then predict. Everything the team builds should be placed on that funnel. Where this file's placement differs from a source doc's own framing (e.g. `challenge1-plan.md`'s MVP/stretch split, or an earlier tiering of this same plan), this file's placement is the one to follow for sequencing purposes.

---

## 1. Idea inventory

Every idea from both gamechanger docs, one row each, nothing dropped. `challenge1-plan.md`'s own MVP items (CSV ingestion, enterprise/establishment split, mocked-then-live multi-source scraping, the evidence-breakdown review table, confirm/reject gating) are the **Priority 1 foundation by definition** and are not re-listed here as individual rows; see Section 2 for how they anchor the funnel.

| Idea name | Source doc | Where it sits in the funnel | Status / rationale |
|---|---|---|---|
| Proactive street sweep (discovery inversion) | `gamechanger-discovery-freshness.md`, Idea 1 | Priority 1: Scrape (extended scope) | Folded into scraping-based verification: it's the same OSM/Maps sources, just enumerated street-first instead of register-first. Real engineering cost (~3–4.5h per the doc's own estimate); graduated fallback applies (Section 2). |
| Living registry as snapshot diff (freshness screen) | `gamechanger-discovery-freshness.md`, Idea 2 | Secondary / polish | Cheap (well under 2h per the doc's estimate) but explicitly secondary: build only after the three verification priorities have a working baseline. |
| Cross-municipality sharing of confirmed corrections | `gamechanger-discovery-freshness.md`, Idea 3 | Narrated-only | Explicitly framed in its own source doc as "narrated only... not something to build in the hackathon." |
| Impact × uncertainty triage worklist | `gamechanger-triage-and-briefing.md`, Idea 1 | Presentation layer | Sits on top of whichever verification priorities are working; ranks whatever evidence exists, it does not gather evidence itself. |
| Seasonal/cyclical inactivity inference | `gamechanger-triage-and-briefing.md`, Idea 2 | Priority 3: Predict | The prediction fallback in the funnel: used only once scraping and reach-out are inconclusive or silent. Layer 1 (sector prior) is buildable; layer 3 (multi-year history) is narrated-only, honestly, because the real dataset is a single snapshot. |
| AI-generated Dutch case-file paragraph | `gamechanger-triage-and-briefing.md`, Idea 3 | Presentation layer | A rendering detail on top of the worklist row, not a verification method. |
| Active learning from officer decisions | `gamechanger-triage-and-briefing.md`, Idea 4 | Narrated-only | Explicitly labelled in its own source doc as "a single narrated slide/idea for the pitch video, not a component to implement on the day." |

Two reach-out channels used in Priority 2 below are not brainstorm-doc ideas and so have no row above: **phone** is the AI voice-agent escalation call already designed in `challenge1-plan.md` §3.2; **email** and **postal mail** are new channels for this action plan (email buildable, postal mail narrated-only); see Section 2, Priority 2.

---

## 2. The three verification priorities, in build order

The whole point of this plan: **don't guess whether a business is active: check it, cheapest method first, and only pay for a more expensive check when the cheaper one didn't give a clear answer.** Each priority below states what it is, why it sits at that point in the order, concrete build steps, a feasibility estimate, and exactly what triggers escalation to the next priority.

### Priority 1: Data verification via scraping (build this first; the actual foundation)

**What it is.** Automated, multi-source checks against public data, no human contact required: **Google Maps** (listing status, photo recency, opening hours), **Google reviews** (recency/content), **OpenStreetMap** (tag presence/recency via the free, keyless Overpass API), and **Trustpilot** (review presence/recency), per `challenge1-plan.md` §3.2. This priority also absorbs the **proactive street sweep** (`gamechanger-discovery-freshness.md`, Idea 1): instead of only checking register rows outward against these same sources, also enumerate real-world POIs on the chosen street first and diff them against the register, surfacing unmatched storefronts. Both directions use the same sources and the same "no live API key required" caveat: they are one priority, not two.

**Why priority 1.** Cheapest (OSM is free and keyless; Maps/Trustpilot need only a per-account key, not a per-contact cost), fastest (no waiting on a human to answer a phone or reply to an email), and most scalable (can run against every row in the dataset without per-contact cost or consent questions). This is buildable today with mocked responses and improvable later by swapping in live API calls as credentials allow (`challenge1-plan.md` §3.2, §6); it does not depend on anything else in this plan.

**Concrete build steps:**
1. Ingest the CSV with registry numbers as text; split into 457 legal entities and 543 establishments via `Ondernemingsnr_maatsch_zetel` (`source-metadata.json`).
2. For each address in the chosen street, query the four sources (mocked JSON per test address is acceptable for the MVP; wire in live Google Places/Trustpilot Business API calls only as far as credentials and time allow).
3. Combine per-source signals into a certainty marker (High/Medium/Low) based on **agreement across sources**, not any single source alone.
4. **Extended scope: the street sweep, with a graduated fallback** (this is "how thorough priority-1 discovery gets," not a separate tier to cut wholesale):
   - **(a) Full automated sweep**: enumerate every OSM/Maps POI on the street, address-match against the register, gate entries into the discovery queue only with 2+ independent signals, label them "Nazicht," never assert. Estimated **~3–4.5 hours** end to end (POI enumeration ~30–45 min, Maps integration ~45–60 min if pursued live, address-matching/fuzzy-diff ~60–90 min, the fiddliest part, noise-mitigation ~30 min, discovery-queue UI ~30–45 min if the main review UI already exists), per `gamechanger-discovery-freshness.md`. Its first steps (pick the street, pull POIs, start matching) do **not** depend on the review-UI/confirm-reject work in step 3 being finished, only on the street being chosen (already done at kickoff, ~10:00) and the register CSV being loaded. If 1–2 people can be spared, start this spike from **~10:35** in parallel with the rest of the team building the core of Priority 1, rather than waiting until after lunch.
   - **(b) Narrowed hand-curated discovery set**, the realistic default deliverable: a handful of manually-assembled discovery-queue rows for the one demo street, built by a person checking Maps/OSM directly rather than a fully automated pipeline, still following the same 2+-signal and "Nazicht" rules and the same confirm/reject flow. Buildable in **well under an hour**. Step down to this the moment the automated sweep looks behind schedule.
   - **(c) Drop the street-sweep extension**: last resort if even (b) isn't ready; the core register-row-outward scraping in steps 1–3 still stands on its own as Priority 1's baseline and is never dropped.

**What happens when it's inconclusive.** When sources actively disagree (e.g. Maps says "permanently closed," OSM shows an open-tagged node) or are all silent (no listing, no reviews, no OSM tag at all; the register's claim is neither confirmed nor denied), escalate that address to **Priority 2 (reach-out)**. Agreement across sources needs no escalation.

### Priority 2: Data verification via reach-out (build second; escalation only, not a default)

**What it is.** Direct contact with the business, used only for addresses Priority 1 left uncertain: three channels, in order of what's realistic to build and demo today:
- **Phone**: the AI voice-agent escalation call already designed in `challenge1-plan.md` §3.2: triggered only on conflicting/silent Priority 1 results, transcript (and/or recording) captured as its own evidence row, reviewable by the officer like any other source. If the call reaches a wrong number or a current occupant who's never heard of the business, the script's fallback branch asks whether they know an updated phone/email for that business, logged as a lead to verify, not a confirmed correction, going through the same confirm/reject flow as everything else. A failed call still produces something usable instead of a dead end.
- **Email**, new for this plan: an automated email to the business's listed address (the `Email` field present in the GeoJSON, per agent.md Source 7's column guide) asking the business to confirm its current status. Cheap and realistically buildable in the hackathon as a **send-and-log** mechanism: template the message, send it, record it as an evidence row with a timestamp and a "sent, awaiting reply" status. A reply arriving inside a 6-hour build window is unlikely, so demo the send/template mechanism and treat "reply received" as a state the evidence row supports, not something guaranteed to happen live on camera.
- **Postal mail**: **narrated-only, not built.** Turnaround time (days to weeks) makes it infeasible to demo inside a 6-hour hackathon. State plainly in the video: "in a real deployment this could also include a mailed notice for businesses with no working phone or email"; do not fake a mailed letter or its response.

**Why priority 2.** Each contact costs real time (a call takes minutes and needs its own credentials/consent framing, per `challenge1-plan.md` §6) or carries a real delay (an email reply may not arrive at all inside the demo window; a letter takes days-to-weeks). Reach-out is only worth that cost when the free/fast scraping check in Priority 1 didn't already produce a confident answer: this is why it comes second, as an escalation, not why it's cheap enough to run on everything.

**Concrete build steps:**
1. Phone: reuse the existing design: trigger condition (Priority 1 conflict/silence), call, transcript capture, evidence row, officer review before it affects anything (`challenge1-plan.md` §3.2, §5 criterion 1).
2. Email: a simple template ("Beste [naam], kan u bevestigen of [onderneming] nog actief is op [adres]?", illustrative only, in Dutch per the officer-facing-text requirement, agent.md Source 6), a send mechanism (any SMTP/email API the team already has access to), and a logged evidence row per address with source = "e-mail (verzonden)" and a timestamp.
3. Postal mail: one sentence in the pitch video only, no build step.

**Feasibility.** Phone: already scoped as an MVP item in `challenge1-plan.md` §4 ("at least one demonstrated AI voice-agent call"); budget accordingly. Email: roughly **30–45 minutes** for template + send + log, comparable in cost to the cheaper Priority 1/3 sub-steps. Postal mail: **zero build time**, one line in the script.

**What happens when it's inconclusive.** No answer to the call after the attempts already planned, no email reply within the build/demo window, or no contact details known at all → escalate that address to **Priority 3 (predict)**.

### Priority 3: Prediction based on past data (build third, time-permitting)

**What it is.** The seasonal/cyclical inactivity inference from `gamechanger-triage-and-briefing.md`, Idea 2: a **sector-level prior** (a small hand-curated lookup of NACE/RSZ activity descriptions known to be seasonal: ijssalon, terraszaak, seizoensgebonden verhuur, kerstmarkt/foorkraam, flagging a business even with zero prior observations of its own) plus **review-text mining** (scanning the same review text already pulled in Priority 1/2 for explicit Dutch seasonal phrases like *"enkel open in de zomer," "gesloten in de winter"*). Both layers work with the near-zero real history the actual dataset has: `source-metadata.json` records one `retrieved_on` snapshot date, and there is no multi-year time series to mine.

**Why priority 3: last, not first.** This is not new evidence; it is a **plausibility adjustment** applied only once scraping and reach-out have both failed to produce a clear answer. It never confirms a business is active or inactive on its own, and it never overrides the officer's confirm/reject decision; it only dampens how urgently an otherwise-silent case gets flagged, so a business that's predictably closed for the season doesn't get treated the same as one that looks genuinely gone. Putting it after Priorities 1 and 2 keeps the funnel honest: real signals (scraped or human-contacted) always outrank a heuristic prior.

**Concrete build steps:**
1. Curate ~10–15 seasonal NACE/keyword entries; wire a conditional into the scoring/ranking step (Section 3) that dampens uncertainty when the current month falls in a flagged business's expected closed season.
2. (Stretch) Scan already-fetched review text for explicit seasonal Dutch phrases.
3. Never suppress the row outright: the officer still sees it and can override the dampening, same as every other automated judgment in this plan.
4. **Not building layer 3** (multi-year self-accumulating history): the honest long-term answer is that the snapshot-diff mechanism (Section 1, "Secondary / polish") starts accumulating exactly this history from its first run, but there is nothing to fake for the demo: say this as a roadmap point, not a built feature.

**Feasibility.** Layer 1 (sector lookup + one conditional): **~30–45 minutes**, assuming the ranking step from Section 3 already exists. Layer 2 (review-text keyword scan): **~30–60 minutes**, a stretch add-on. Layer 3: **not built**, narrated only.

**End of the funnel.** Whichever priority produced the evidence (scrape, reach-out, or prediction), the officer still has to confirm or reject before anything is final (`challenge1-plan.md` §2, point 5; §5 criterion 2). No priority level, including a live phone call or email reply, auto-publishes anything.

---

## 3. The officer-facing presentation layer

This is not a fourth priority competing with scrape/reach-out/predict: it is **how the results of Priorities 1–3 get surfaced to the officer**, built on top of whichever of those are working by the time it's assembled. It does not gather any evidence of its own.

A flat per-address evidence table, however well each row breaks down its scrape/reach-out/predict results, does not survive the officer's real scale. Per agent.md's "Officer context": *"One municipality of about 20,000 residents counted roughly 33,000 register entries."* That is the stated baseline problem for this challenge, not a hypothetical stress case; a solo officer facing even a few hundred rows, each with a Maps cell, an OSM cell, a Trustpilot cell and a reach-out/prediction cell, has no way to know which row to open first. This is exactly why the presentation layer ranks rather than just lists.

- **The triage worklist** (`gamechanger-triage-and-briefing.md`, Idea 1): ranks every address by `priority_score = uncertainty_score × impact_score`, where `uncertainty_score` counts source disagreement/silence from whichever of Priorities 1–2 have run on that address, dampened by Priority 3 when it applies, and `impact_score` uses cheap, honest proxies already in the data (commercial NACE signal, street density, staleness/last-checked date; never a fabricated metric). This is mostly a sort/rank step over data the priorities already compute; no new data source, no new API.
- **The discovery queue** (Priority 1's extended scope, Section 2) feeds into the **same** ranked list as regular register-row entries, not a separate screen: a business the register never knew about and a business the register got wrong should compete for the officer's attention in one place.
- **The Dutch case-file paragraph** (`gamechanger-triage-and-briefing.md`, Idea 3): a short (2–4 sentence) Dutch narrative per worklist row synthesizing whichever evidence exists (scrape result, reach-out outcome, seasonal context if Priority 3 applied) into one recommended action. Degrades gracefully to a template-string sentence if no LLM call is available; either way, officer-facing text stays in Dutch (agent.md, Source 6).
- Opening any row from the worklist drops the officer into the same per-source evidence-breakdown table `challenge1-plan.md` already designs; the worklist is the entry point, not a replacement.

Build this layer once Priority 1's baseline evidence exists; it gets richer automatically as Priorities 2 and 3 come online, and poorer but still functional if they don't.

---

## 4. Hour-by-hour build sequence for the day

Same clock times, same real 16:30 hard cutoff as `challenge1-plan.md` §8 (agent.md, Source 1/6): this file only reorganizes what happens inside those hours around the verification funnel.

| Time | Programme | Team focus | Funnel checkpoint |
|---|---|---|---|
| 09:00–09:30 | Doors, check-in, kickoff | Form team, pick challenge and municipality/street | n/a |
| 10:00–10:35 | Build starts | First-35-minutes flow: load CSV as text, split enterprises/establishments, pick one street | Priority 1 ingestion starting |
| 10:35–12:00 | Build | Main group: Priority 1 core: multi-source scraping checks (mocked Maps/OSM/Trustpilot), certainty marker, review-table UI skeleton, confirm/reject interaction. **In parallel, 1–2 people spike Priority 1's discovery extension**: pull OSM/Maps POIs for the street and start address-matching; this doesn't block on the review UI | Priority 1 (core + discovery spike) in progress |
| **12:00** | Lunch starts | n/a | **Checkpoint: Priority 1's core (ingestion, mocked multi-source scraping, certainty marker, review table, confirm/reject) must be functionally complete.** Separately assess the discovery spike: on track for the full sweep, or should it plan to fall back to the hand-curated set after lunch? |
| 12:00–13:00 | Lunch | n/a | n/a |
| 13:00–14:00 | Build resumes, mentoring | Close any remaining Priority 1 core gaps first. Start **Priority 2**: wire the voice-agent escalation call against Priority 1's conflict/silence output; build the email template + send/log mechanism. Discovery spike continues toward the full sweep or switches to hand-curating a handful of rows. Start the **presentation layer**'s triage scoring function; it only needs Priority 1's evidence fields, so it can begin now | Priority 2 starting; discovery graduated path in progress; presentation layer starting |
| **14:00** | n/a | n/a | **Checkpoint, in order: (1) confirm Priority 1's core is solid; if not, stop everything else and fix it, nothing downstream matters without it. (2) Assess the discovery extension against its graduated path: full sweep / hand-curated set / drop. (3) Confirm at least the phone channel of Priority 2 works end to end. (4) Only if 1–3 are ahead of schedule, start Priority 3's sector-prior dampener.** | Go/no-go for Priority 3 and presentation-layer polish |
| 14:00–14:30 | Build | Finish whichever level of the discovery extension was reached; finish Priority 2's email logging; build Priority 3's sector-prior dampener if time allows; assemble the presentation layer: merged worklist row (triage + whatever discovery rows exist), Dutch case-file paragraph (template fallback acceptable) | Presentation layer wrap-up |
| 14:30–15:00 | Build | **Secondary/polish only, and only if Priorities 1–3's working baseline plus the presentation layer are already solid:** second-dataset reusability re-run (do this first: "minutes, not hours" and directly demonstrates criterion 3), then the snapshot-diff freshness screen | Secondary/polish (optional) |
| ~15:00–15:15 | Feature freeze | Stop building. Freeze the prototype; label what's real vs mocked; do not start anything new after this point | Freeze: whatever funnel state exists is final |
| 15:15–15:30 | Final check | One clean run-through of the demo path to be recorded | n/a |
| 15:30–16:00 | Record, upload, verify | Record the 3-minute video (segments per agent.md Source 6); upload to YouTube; complete the private-window playback check | n/a |
| by 16:00–16:15 | Submit | Submit the YouTube link via the Google Form, leaving real buffer before 16:30 | n/a |

No new deadline is invented here: 16:30 (Europe/Brussels) remains the only hard cutoff (agent.md, Source 1/6: "Late submissions are not accepted").

---

## 5. Explicit cut-lines

If behind schedule, drop in this order (**never Priority 1**), because scraping-based verification is the foundation: without it there is nothing to show, nothing for reach-out to escalate from, and nothing for prediction to dampen.

1. **Cut Priority 3 (prediction) first.** It is a plausibility adjustment on top of real evidence, not evidence itself: the plan works, just less gracefully around seasonal businesses, without it. Narrate it instead: "we designed a seasonal-inactivity dampener; see the plan for the design," and cite the honest cold-start constraint (single-snapshot dataset) as the reason it's a roadmap item.
2. **Cut Priority 2's weaker channels next, keep phone if anything survives.** Postal mail was never built (narrated-only from the start). Cut the email channel next if time is tight: narrate it as "an email-based confirmation request, cheap to add" rather than half-building an unreliable send/log mechanism. If only one reach-out channel can be finished, keep the **phone** call, since it's the one already scoped into `challenge1-plan.md`'s own MVP and produces a reviewable transcript on camera.
3. **Within Priority 1, step down the discovery extension's graduated path before cutting anything else in the core.** The base register-row-outward scraping (ingestion, multi-source checks, certainty marker, review table, confirm/reject) is never cut; it is the foundation. Only the street-sweep extension degrades: (a) full automated sweep, if the ~10:35 spike is genuinely on track by the 14:00 checkpoint → (b) narrowed hand-curated discovery set (the realistic default) → (c) drop the extension entirely, keeping only the core register-row checks, as the last resort.
4. **Cut the secondary/polish items last, in this order:** the snapshot-diff freshness screen first (freshness can be narrated, since the second-dataset re-run already covers criterion 3's "reusable" half on its own), then the second-dataset re-run only if truly out of time (it costs "minutes, not hours" and is the cheapest way to demonstrate a required criterion, so it should rarely be the one that's cut).

---

## 6. Closing pitch

The verification-funnel framing, stated plainly:

> We check whether a business is active three ways, cheapest first: scrape the public web, reach out directly if that's not enough, and fall back on a prediction from seasonal patterns only as a last resort. Then the officer decides, every time.

Supporting line, if the presentation layer (triage + discovery) is built and demoed on camera:

> One ranked list tells the officer, for one street, both which existing register entries need a second look and which storefronts aren't in the register at all, ordered by where the next ten minutes matter most.
