# Challenge 1 · Game-Changer Brainstorm: Officer Cognition & Synthesis

**Event:** PROV-AI Public AI Hackathon, 16 Sept 2026, AP Hogeschool Campus Spoor Noord, Antwerp
**Grounded in:** `agent.md`, Challenge 1 brief and its Examples & Technical Guidance page (all quoted/paraphrased sections cited inline below).

**What this document is.** This is a **brainstorm / proposal document**, not the build plan. It does not repeat or replace `docs/plans/challenge1-plan.md`, which already specifies the team's multi-source verification approach (Google Maps / OSM / Trustpilot), the AI voice-agent escalation call, the per-source evidence-breakdown review table, the mandatory officer confirm/reject gate, and the second-dataset re-run for reusability. This document proposes **additional, differentiated ideas** along one specific angle: how the officer's limited attention gets allocated and synthesized once that evidence exists. It has already been reviewed once (by an independent advisor pass); the verdict was that the triage-ranking idea below (Idea 1) is the single strongest idea produced across the whole brainstorm, and it is written up accordingly with the most depth of anything here. Idea 2 (seasonal inference) was added afterward at the team's request, to handle a specific real failure mode (seasonal businesses being mistaken for closed ones) while being honest that the supplied data has no real multi-year history to learn from yet.

---

## Idea 1 (primary): Impact × uncertainty triage worklist

### The problem this solves, restated at the actual scale

`docs/plans/challenge1-plan.md` already designs a good per-address, per-source evidence table, but a flat table, however well it breaks down evidence, does not survive the officer's real scale. Straight from `agent.md` (Examples & Technical Guidance, "Officer context"):

> "One municipality of about 20,000 residents counted roughly 33,000 register entries."

That is not a hypothetical stress case; it is the stated baseline problem for this challenge. An officer facing a table with even a few hundred rows, each with a Google Maps cell, an OSM cell, a Trustpilot cell and a voice-check cell, has no way to know **which row to open first**. A well-organized table of 5,000 uncertain-but-unprioritized rows is barely more usable to a solo officer than the spreadsheet-and-shared-mailbox status quo agent.md itself describes for the fictional persona Marleen, who "cross-checks records by hand, in Excel, between emails" (agent.md, "Officer context"). The evidence-breakdown table answers "what do we know about this address?"; it does not answer "where should I spend my next ten minutes?" That second question is the one a solo officer with 33,000 entries and no dedicated data team actually needs answered first.

### The proposed design: rank, don't just list

Instead of (or on top of) the flat evidence table, compute a **single ranked worklist**: every address/entry gets a score along two independent axes, and the list is sorted so the highest-value next actions are at the top.

**Axis 1: Uncertainty ("why does this need attention at all").** This is directly derivable from the evidence-gathering step the team is already building in `challenge1-plan.md`:
- Sources actively disagree (e.g. Google Maps says "permanently closed" but OSM shows an open-tagged node, or the register says active but no source confirms it): highest uncertainty.
- Sources are silent (no listing, no reviews, no OSM tag at all): the register's claim is neither confirmed nor denied. This is the case agent.md's own worked example flags as "Zekerheid: Laag" for an advisory bureau with "geen website, geen vermelding, geen recente vergunning" (agent.md, "Optional worked example").
- Sources agree with each other and with the register: lowest uncertainty, nothing to prioritize.

A simple, honest computation: count how many of the configured sources returned a positive signal, how many returned a negative signal, and how many returned nothing, then treat both disagreement and total silence as forms of uncertainty (silence is not the same as confirmation; it just means the register's claim was never tested).

**Axis 2: Impact ("why this address matters more than another equally uncertain one").** This is the part that is easy to over-promise and easy to get wrong by inventing a fake metric. To stay honest, only use proxies that are actually computable from the CSV/enrichment data already in scope for this challenge, and say plainly that they are hackathon-grade proxies, not a validated economic-impact model:

- **Commercial NACE-type signal present.** `NACE_hoofdact_RSZ` / `Omschrijving_hoofdact_RSZ` exist for a minority of rows (per `source-metadata.json`, only 81 of 1,000 rows have an RSZ activity code (`missing_rsz_activity_code_rows: 919`); the VAT activity code is empty for all 1,000 rows). Where a NACE/RSZ activity code *is* present and indicates a plainly customer-facing category (retail, hospitality, personal services), that's a real, cheap-to-compute signal that the entry is more likely to be a visible street-level business an officer or resident would notice, worth weighting up. Where it's absent (the common case), this proxy simply contributes nothing rather than being guessed at.
- **Street density as a foot-traffic proxy.** Count how many other register entries share the same street (the same field the team's own "first 35 minutes" walkthrough already uses to pick a starting street, Paalstraat has the most records in the Schoten sample, 35, per agent.md). A street with many entries is a reasonable, cheap proxy for a busier commercial street where getting the register right matters to more residents and neighboring businesses than an isolated address on a quiet residential street. This is a proxy for likely foot traffic and cross-checkability (more neighbors to visually or socially confirm a business), not a measured traffic count.
- **Recency of prior attention (least-recently-checked wins).** Once the tool has run once, every entry has an "last observed/last reviewed" timestamp (already a field in the evidence table design in `challenge1-plan.md`). An entry nobody has looked at in the longest time is arguably the best use of the next ten minutes, all else equal; this is the cheapest and most honest impact proxy available on day one, before any external enrichment even runs, and it directly rewards actually working through the list instead of re-checking the same few addresses.
- **Explicitly not used as an impact proxy:** anything that would require inventing a number not present in the data: no fabricated "revenue estimate," no fabricated "customer footfall count," no scraped follower count. If a real dataset field doesn't support a proxy, leave it out rather than approximate it with a guess presented as a measurement.

### A concrete, honest scoring formula

This is intentionally a simple weighted sum, appropriate for a 6-hour build, not a claim of a validated model:

```
uncertainty_score  = (# sources disagreeing) * 2  +  (# sources silent) * 1
impact_score       = commercial_nace_signal (0 or 1) * 2
                    + street_density_bucket (0, 1, or 2: low/med/high entry count on the street)
                    + staleness_bucket (0, 1, or 2: never checked / checked long ago / checked recently, inverted)

priority_score = uncertainty_score * impact_score
```

Multiplying (rather than adding) the two axes is a deliberate, simple design choice: an address that is both highly uncertain *and* high-impact should visibly jump to the top, while an address that is either fully certain or genuinely low-impact should sink; even a moderately uncertain but zero-impact entry (no commercial signal, quiet street, checked recently) shouldn't crowd out a genuinely ambiguous case on a busy street. The exact weights (the `*2`, `*1`, bucket boundaries) are placeholders the team should tune against a handful of real rows during the build, not a tuned or validated model; say this plainly in the pitch if this feature is demoed.

### What the worklist screen looks like

A single ranked list, one row per address, sorted by `priority_score` descending:

| # | Address | Priority | Why flagged (uncertainty) | Why it matters (impact proxy) | Last checked |
|---|---|---|---|---|---|
| 1 | Paalstraat 14 | High | Maps: closed / OSM: no recent edit, sources disagree | Commercial NACE signal; busy street (12 other entries) | Never |
| 2 | Paalstraat 31 | High | No source has any listing at all | Busy street; not checked in 6 months | 2026-03-02 |
| 3 | Kerkstraat 4 | Medium | One source silent, one confirms | No commercial signal; moderate street density | Never |
| … | … | … | … | … | … |

Opening a row from the worklist drops the officer straight into the existing per-source evidence-breakdown table from `challenge1-plan.md` for that one address; the worklist is the entry point/triage layer sitting on top of that table, not a replacement for it. "These 8 addresses are where your next hour of work matters most" becomes an actual, literal top-8 slice of this ranked list, not a rhetorical framing.

### Feasibility

This should be genuinely buildable within the hackathon's timeframe, because it is mostly a **sort/rank step on data the team is already computing** for the evidence-breakdown table (`challenge1-plan.md`, Section 3.2): no new data source, no new API, no new UI paradigm, just:
1. a small scoring function over fields already present (source agreement counts, street grouping, a timestamp), and
2. sorting the existing table by that score instead of, say, alphabetically or by register order.

The only genuinely new UI element is a compact "why flagged / why it matters" summary column, which can be generated directly from the same inputs used to compute the score (no extra enrichment call needed).

### How this maps to the official criteria

Straight to success criterion 2, **"Useful and trustworthy for officers"** (agent.md, Challenge 1 brief, "Three success criteria": "make records easy to find, inspect and correct, with officer approval before publication"). A flat table, however trustworthy each individual row is, does not make records "easy to find" at 33,000-entry scale; ranking does. This is a usability multiplier on top of the trust mechanism already designed in `challenge1-plan.md`, not a substitute for it: confirm/reject still gates every change: the worklist only changes what the officer sees first, never what gets published.

---

## Idea 2: Seasonal/cyclical inactivity inference (cold-start pattern detection)

### The problem this catches that plain evidence-checking misses

Some businesses are genuinely, predictably closed part of the year: an ice-cream parlour (`ijssalon`) shut from November to March, a terrace-dependent café quiet outside summer, a Christmas-market stall that only exists in December. Checked on the "wrong" day, these look identical to a permanently closed business under the plan's existing multi-source checks: no recent Maps activity, no fresh reviews, an unanswered voice call. Without a seasonality-aware layer, the tool risks confidently mis-flagging a normally-closed-right-now business as "likely inactive," which is exactly the kind of false correction that would erode officer trust in criterion 2 rather than build it.

**The honest data constraint (say this plainly, don't paper over it):** the actual starter dataset is a **single point-in-time snapshot**: `source-metadata.json` records one `retrieved_on` date, and `challenge1-plan.md` §6 already notes "the exact underlying federal KBO snapshot date is not stated." There is no 5-years-of-monthly-status time series sitting in the CSV or GeoJSON to mine. A design that assumes rich multi-year history exists would not survive contact with the actual data. So the design has to work well with **zero to low history on day one**, and only get better as real history accumulates, not require it upfront.

### A cold-start-friendly design, cheapest layer first

1. **Sector-level prior (needs zero history for the specific business).** Build a small, hand-curated lookup of NACE/RSZ activity descriptions known to be seasonality-prone (e.g. `Omschrijving_hoofdact_RSZ` containing terms like ijssalon, terraszaak, seizoensgebonden verhuur, kerstmarkt/foorkraam). Where this activity code is present (true for only 81 of 1,000 rows per `source-metadata.json`, the same sparsity limit Idea 1 already accounts for), a business tagged this way gets a seasonal-expectation flag even with zero prior observations of its own. This is explicitly a **heuristic prior curated by the team**, not a learned pattern: label it that way in the pitch, not as "the AI detected a 5-year pattern."
2. **Review-text mining (needs only a handful of reviews, not years of snapshots).** Scan the same Google/Trustpilot review text already being pulled for evidence (per `challenge1-plan.md` §3.2) for explicit seasonal language: Dutch phrases like *"enkel open in de zomer," "gesloten in de winter," "heropent in april."* A single review mentioning this is a usable signal; this needs low volume, not long history, which is exactly the constraint the team named.
3. **Self-accumulating history going forward (the honest long-term answer, not a hackathon deliverable).** The team cannot back-fill five real years of status by 16:30. But the snapshot-diff mechanism proposed in the companion document (`docs/plans/gamechanger-discovery-freshness.md`, Idea 2) already stores a dated observation every time the pipeline runs. Point this out explicitly as the answer to "how would this ever get real historical data": **the tool is designed to start building exactly the history this idea needs from its very first run**, even though it obviously can't have five years of it during the hackathon. That is a stronger, more honest reusability story than claiming the pattern-detection works today.

### How this changes the triage worklist (Idea 1) and the Dutch case-file (Idea 3)

- **Triage worklist:** when either layer 1 or 2 flags a seasonal expectation matching the current month, apply a **dampener**, not a suppression, to that entry's `uncertainty_score` contribution (Idea 1's formula): it still appears in the worklist if genuinely uncertain for other reasons, it just doesn't rank as urgently as an equally-silent non-seasonal business. Never hide the row outright: the officer can still see and override it, preserving the same no-silent-auto-decisions principle as everywhere else in this plan.
- **Dutch case-file:** the generated summary should name the seasonal context when it applies, e.g. *(illustrative only)* "Dit type onderneming is doorgaans gesloten buiten het zomerseizoen; de afwezigheid van recent bewijs kan hiermee samenhangen." This gives the officer the reasoning, not just a dampened score.

### Feasibility

Layer 1 (sector lookup table + a rule that dampens the score) is genuinely cheap: curating ~10–15 seasonal NACE/keyword entries and wiring one conditional into the existing scoring function from Idea 1 is realistically **30–45 minutes**, assuming Idea 1's ranking step already exists. Layer 2 (review-text keyword scan) is a stretch add, maybe another 30–60 minutes if review text is already being fetched. Layer 3 is narrated only; it is not something to build or fake in the hackathon (do not mock five years of fake history and present it as real: that would cross from "illustrative example" into "fabricated evidence," which is a different and worse thing than the honest mocked-data patterns used elsewhere in this plan).

### How this maps to the official criteria

Primarily criterion 1 ("flag potentially inactive entries", this reduces a specific, real false-positive mode rather than adding a new capability) and reinforces criterion 3 alongside the companion document's Idea 2: the "self-accumulating history" framing is a concrete answer to "how does this stay fresh and improve over time," not a narrated aspiration.

---

## Idea 3 (secondary, shorter): AI-generated Dutch case-file paragraph

For each entry surfaced in the triage worklist, generate a short (2–4 sentence) natural-language Dutch summary that synthesizes the per-source evidence into a plain narrative plus one recommended action, instead of asking the officer to parse the evidence-breakdown row cell by cell.

*Illustrative example only, not a claim about real tool output, and not copied from any source document:*

> "Deze vestiging toont geen activiteit sinds [datum]; twee bronnen zwijgen, één bevestigt sluiting. Aanbevolen actie: contact opnemen."

This turns a compliance requirement into a feature. The Submission & Practical FAQ states plainly: "Keep officer-facing answers and interface text in Dutch" (agent.md, Source 6, "Which language do we work in?"). Rather than treating that as a constraint to satisfy with translated table headers, generating the case-file sentence directly in Dutch makes the requirement do useful work: it reduces the officer's reading time versus scanning a raw multi-column evidence row, and it reads like the kind of note an officer would already write for their own file.

**Feasibility.** Cheap if an LLM API is available in the stack the team is already using (e.g. via the OpenAI API partner credit, agent.md Source 8): one short prompt per worklist row, fed the same structured evidence fields already computed for the table (sources, dates, agreement/disagreement, register status). If time or API access runs out, this should degrade gracefully to a **template-based sentence** built from string interpolation over the same fields (e.g. a fixed Dutch sentence template with the last-observed date and disagreeing-source names slotted in); no LLM call is strictly required for this to work, and either version keeps the officer-facing text in Dutch as required.

---

## Idea 4 (stretch, one paragraph): Active learning from officer decisions

One narrated idea, not something to build in the hackathon: over time, the officer's own confirm/reject decisions (already captured as the mandatory approval gate in `challenge1-plan.md`) could in principle feed back into recalibrating how much weight each evidence source gets in the certainty and priority calculations, for example, if a source's silence (say, Trustpilot never having a listing) keeps correlating with the officer confirming "still active" anyway, that source's absence should count for less uncertainty over time, rather than being treated the same as active disagreement. This is explicitly a single narrated slide/idea for the pitch video, not a component to implement on the day.

---

## The winning synthesis

Idea 1 (this document's triage worklist) and the "proactive street sweep" discovery idea developed in the companion document `docs/plans/gamechanger-discovery-freshness.md` (written in parallel; its exact contents are not reproduced or assumed here beyond what its filename signals) are designed to combine into **one screen**: a single prioritized worklist for the officer's chosen street that ranks *both* known-but-uncertain register entries *and* newly-discovered unregistered storefronts together, side by side, by the same impact × uncertainty logic.

**The one sentence a judge could repeat back:** one ranked list tells the officer, for one street, both which existing register entries need a second look and which storefronts aren't in the register at all, ordered by where the next ten minutes matter most, and quietly smart enough not to waste that ranking on a business that's just closed for the season.
