# Challenge 1 · Find the Real Businesses: Solution Plan

**Event:** PROV-AI Public AI Hackathon, 16 Sept 2026, AP Hogeschool Campus Spoor Noord, Antwerp
**Team size assumed:** up to 5 people
**Build time assumed:** ~6 real hours (10:00–16:30, minus the 12:00–13:00 lunch break)
**Grounded in:** `agent.md` (Challenge 1 brief, its Examples & Technical Guidance page, the Starter Files & Source Guide, and the Submission & Practical FAQ; all quoted/paraphrased sections cited inline below), cross-checked against the live challenge page at https://ap.ns2agi.com/challenges/challenge-1-right-service-first-time, which matches agent.md's Challenge 1 content.

**Data now in hand:** the Schoten KBO sample referenced throughout this plan is no longer hypothetical. The actual files are checked into the repo root: `schoten-kbo-1000-2026-09-07.csv`, `schoten-kbo-1000-2026-09-07.geojson`, and `source-metadata.json`. Row counts and stats quoted below (1,000 rows, 457 legal entities, 543 establishments) come from these real files, not an estimate.

This is an internal planning document for the team. It is written in English throughout. It does not itself contain officer-facing UI copy; see the note on language in Section 9.

---

## 1. Problem restated

Local economy officers cannot get a reliable picture of which businesses are actually trading in their area from the federal business register (KBO) alone. The register mixes long-dormant companies with genuinely active ones, misses shops that are visibly open on the street, and buries real local activity under side registrations: one municipality of about 20,000 residents counted roughly 33,000 register entries (agent.md, Examples & Technical Guidance, "Officer context"). Officers currently fill this gap manually: the fictional persona "Marleen" cross-checks records by hand in Excel between emails, where outreach can miss new shops or reach businesses that have already closed; "Tom," another fictional persona, pays a commercial data broker to fill the gap and wants to compare public sources and see how the tool reached its conclusion (agent.md, "Officer context" / "People"; both are fictional composite profiles, not named attendees). The register also conflates two different kinds of records: the enterprise (legal entity, `onderneming`) and the establishment unit (`vestigingseenheid`, a physical location), which are linked but distinct, and whose registered seat may sit in a completely different municipality (agent.md, "Enterprise or establishment?"). Officers need a way to see, per address, what the register says, what public evidence supports or contradicts it, how confident that evidence is, and a chance to correct the record, without the tool silently publishing anything it isn't sure of.

## 2. Proposed workflow

End-to-end, officer-facing flow:

1. **Officer picks a street or small area.** In the optional Schoten sample, Paalstraat has the most records (35) and is the suggested starting point (agent.md, "A suggested first 35 minutes"), but the team may choose any street, municipality or region inside the Province of Antwerp (agent.md, Challenge 1 brief, "Choose your own municipality").
2. **System loads the register records for that area** and cross-checks each one against **multiple** public evidence sources in parallel (the team's chosen set: Google Maps listing + photos, Google reviews, OpenStreetMap, Trustpilot, see Section 3), instead of a single source.
3. **System presents one row per address, with a per-source breakdown, not one opaque score.** This is the direct answer to what agent.md's own persona "Tom" says he wants: *"compare public sources and see how the tool reached its conclusion"* (agent.md, "Officer context"). Sketch, extending the worked-example table from the Examples & Technical Guidance page:

   | Address | Enterprise / establishment | Register status | Google Maps | OSM | Trustpilot | Voice check | Certainty | Proposed action |
   |---|---|---|---|---|---|---|---|---|
   | Example St 12 | Bakery Example (establishment) | Active | Open, photos <30d old | Present, tagged open | 3 reviews in last month | not needed | High | No action |
   | Example St 14 | Advisory Bureau Example (establishment, seat elsewhere) | Active | "Permanently closed" | Present, no recent edits | No reviews | Called, no answer (2 attempts) | Low | For review: possibly no longer active |
   | Example St 20 | Hair Salon Example (not in register at this address) | n/a | Listed, open | Not tagged | Recent reviews cite this address | Called, confirmed open | Medium | For review: establishment missing or wrong address |

   Clicking any cell should reveal what was actually observed and when, not just the icon. When sources disagree (row 2: Maps says closed, OSM shows no recent edit either way), **show the conflict explicitly** rather than silently averaging into one number; that disagreement is itself useful information for the officer. This table is a template to adapt, not a fixed schema; the team's actual source set may differ.
4. **Officer inspects the evidence** behind any row (source link/API response, what was observed, observation date) before deciding anything, including reading or listening to any voice-check transcript (Section 3.2).
5. **Officer ticks confirm or reject per row.** Only confirmed changes leave the tool and get applied/exported; nothing is auto-published (agent.md: "The officer ticks *bevestigen* or *afwijzen* per row; only confirmed changes leave the tool"). This applies equally to a voice-call outcome: a call transcript is evidence to review, not an automatic verdict.
6. **Optional: contact finder.** When the officer opens a business, the tool can show any available phone/email, whether it belongs to the local establishment or the central office (which may be based outside the municipality), a clickable source, and the date it was checked. If nothing is known, show that plainly (agent.md's example uses *"contactgegevens onbekend"*) rather than inventing a contact. No specific contact fields are mandatory (agent.md, "Optional contact view").

This flow is explicitly one option, not the only correct design: the team should adapt the columns, the sources, and the area to whatever they can build and defend in 6 hours.

## 3. Architecture sketch

Four concrete components. Note that no external API keys are supplied with the starter pack (agent.md, "Optional external sources ... none are supplied with the pack"): Google Maps Platform, Trustpilot's Business API and any voice-calling provider all need the team's own account/key, and each has its own terms of use to respect when scraping vs. calling an official API.

1. **Data ingestion**
   - Load the CSV with registry numbers (`Ondernemingsnr`, `Ondernemingsnr_maatsch_zetel`) imported **as text**, since they have leading zeros that spreadsheets/parsers can silently strip (agent.md, "Import registry identifiers as text").
   - Split rows into two sets: legal entities (`Rechtsvorm`/`Rechtstoestand` filled) and establishment units (`Ondernemingsnr_maatsch_zetel` filled). In the Schoten sample this is 457 legal entities and 543 establishments.
   - Link an establishment to its parent enterprise via `Ondernemingsnr_maatsch_zetel`. Be aware that most parents are not present in the sample (only 28 of 543 establishments have a parent among the 1,000 rows), so the tool should degrade gracefully (show "parent enterprise not in sample") rather than fail.
   - Group by address/street for the officer's chosen area.

2. **Multi-source enrichment / verification step (the team's chosen approach)**
   - Query several sources per address in parallel rather than one: **Google Maps** (listing status, photo recency, opening hours), **Google reviews** (recency and content as an activity signal), **OpenStreetMap** (tag presence/recency via Overpass API, free, no key needed, unlike the others), and **Trustpilot** (review presence/recency). This goes beyond agent.md's suggested single-source "20–35 min" step; the brief only requires *a* public source, not several (agent.md, Challenge 1 brief: "You are free to choose your own data sources and tools").
   - **Use the real Google Maps and Trustpilot APIs, not scraping**: both providers' terms of service restrict scraping their pages directly; the official APIs (Google Places API, Trustpilot Business API) avoid that risk and are more defensible in front of judges. **For the hackathon build, key/account provisioning is the actual blocker, not the approach**: plan to mock the API responses (fixed JSON per test address) so the review UI and confidence logic can be built and demoed even before/without live credentials, and swap in the real calls opportunistically as time and account access allow. Say exactly this split (which addresses use mocked vs. live responses) in the video, per the FAQ's explicit "clearly label anything that is mocked or unfinished."
   - **AI voice-agent call as an escalation step, not a default.** Only trigger a call when the scraped/API sources disagree or are all silent (row 2 in the Section 2 example); calling every business is unnecessary cost and time. Record the call as evidence: transcript (and/or recording) plus outcome, attributed to "AI voice check" as its own source column, reviewable by the officer exactly like any other source before it affects certainty (Section 2, point 4). This double-checks as the escalation the brief itself gestures at doing manually ("a suggested first 35 minutes" step assumes a human does the checking); you're automating the last-mile confirmation step, not the officer's approval.
   - **Wrong-number fallback: turn a dead end into a lead, not just a failed check.** If whoever answers says the registered number doesn't belong to the business at all (wrong number, different current occupant, "we've never heard of them"), the agent's script should have one follow-up branch: ask whether the person has any updated contact details for that business, a current phone number or email, rather than simply logging "no answer" and moving on. Any answer given is logged as its own evidence row (source: "AI voice check: contact update via wrong-number call", what was said, date) and is explicitly a **lead to verify, not a confirmed correction**; it goes through the same confirm/reject flow as everything else before the register's contact info is touched. This costs nothing extra to build once the base call flow exists (one more script branch and one more evidence-row type), and it means a failed call can still produce something useful instead of a dead end.
   - Combine per-source results into a certainty marker (e.g. High/Medium/Low, mirroring the worked example's "Zekerheid" column) computed from source agreement, not from any single source alone (e.g. two independent sources agreeing beats one confident-sounding one).
   - Flag conflicts explicitly: sources disagree with each other or with the register; evidence found at an address with no matching register entry; establishment present but parent enterprise/registered seat elsewhere.

3. **Review/approval UI**
   - A reviewable table/list showing the per-source breakdown (Section 2, point 3), overall certainty and proposed correction per address, with a confirm/reject action per row.
   - No change is treated as final or "published" until the officer confirms it; this is the core trust mechanism the officer criterion depends on.
   - Optional: a per-business contact panel (Section 2, point 6).

4. **Persistence layer**
   - Store raw register data, enrichment findings and officer decisions somewhere queryable: a local database, a spreadsheet, or a hosted option. **Supabase is available as a partner-credit option ($25 credit per participant, agent.md Source 8) but is not required**; any storage the team is comfortable standing up in the time available is fine (agent.md, Submission FAQ: "No specific tools, models or providers" are required).
   - Keep provenance fields (source, date, who confirmed) so the trail is inspectable later; this supports both the "trustworthy" and the "reusable" success criteria (Section 5).

## 4. MVP scope for the day vs stretch goals

**MVP (achievable in ~6 hours):**
- One street (e.g. Paalstraat in the optional Schoten sample, or any street the team picks), 5–10 records.
- CSV loaded correctly (text-safe registry numbers), split into enterprises/establishments, linked where possible.
- Multi-source checks (Google Maps, OpenStreetMap, Trustpilot) for those 5–10 records: **mocked responses are acceptable and expected for the MVP**; wire in real Google/Trustpilot API calls only as far as credentials and time allow, and say clearly in the video which addresses used live vs. mocked data.
- A review table with the per-source breakdown, overall certainty, and proposed action per address (Section 2, point 3), not a single opaque score.
- A working confirm/reject interaction, even if it's just a checkbox that updates a local file or database: the point is that unconfirmed proposals never look "final."
- **At least one demonstrated AI voice-agent call** (even against a mocked/test phone number if a real one can't be safely dialled in time), shown end-to-end: triggered on a conflicting/silent case, transcript captured, and surfaced to the officer as one more reviewable evidence row; this is the concrete differentiator beyond source-scraping alone.
- **A second small dataset re-run to demonstrate reusability**, and show it working on camera. Since ingestion is already meant to be generic (CSV import, enterprise/establishment split via the registry-number column), point the same pipeline at a second, different input: a hand-made few-row CSV for a different fictional or real municipality, or the same pipeline run with a config flag/parameter changed, and show at least one record flowing through end-to-end. This is a minutes-not-hours addition given the ingestion step is already municipality-agnostic, and it turns "fresh and reusable" from a narrated claim into an actual demonstrated result (see Section 5, criterion 3).
- A short explanation, in the pitch video, of what's real vs mocked (required per the Submission FAQ video structure).

**Stretch goals (only if time allows):**
- Swapping every mocked source call for the real, live Google Maps / Trustpilot API responses across all demoed records.
- Live (not test-number) voice-agent calls to real businesses, scaled beyond the single demonstrated case.
- The optional contact-finder feature (local vs central contact, source, checked-date).
- Multiple streets or the whole municipality.
- Automated periodic re-checks against the public source ("freshness").
- A fuller multi-municipality config (more than the single second-dataset demo already in the MVP), e.g. a proper settings file per municipality.
- A written note on licence/attribution handling if reused beyond the hackathon.
- **A working demo the jury can try**: a live link, a test account, or a laptop at the team's table. This is explicitly an optional bonus, not a success criterion (agent.md, Source 6: "A working demo the jury can try is a bonus"); the video submission is what's required regardless.

Be explicit in the video about which of these are done vs aspirational: the FAQ explicitly rewards labelling mocked/unfinished parts clearly rather than overclaiming ("Clearly label anything that is mocked or unfinished," Submission & Practical FAQ).

## 5. Mapping to the three official success criteria

Challenge 1 is judged only on these three criteria (agent.md, Challenge 1 brief, "Three success criteria"):

1. **Reliable business data**: find missing or inaccurate records, flag potentially inactive entries, enrich with evidence and confidence.
   → Satisfied by the multi-source enrichment step (Section 3.2) and the per-source breakdown in the review table (Section 2.3): certainty comes from **agreement across independent sources** (Maps, OSM, Trustpilot, and an AI voice check as escalation), not a single unverified claim, directly answering persona "Tom"'s stated wish to see how the tool reached its conclusion.

2. **Useful and trustworthy for officers**: easy to find, inspect and correct records, with officer approval before publication.
   → Satisfied by the review/approval UI (Section 3.3) and the confirm/reject step (Section 2.5): nothing leaves the tool unconfirmed, and every claim is traceable to its source and date.

3. **Fresh and reusable**: show how data stays up to date, and how the approach adapts to another municipality/province.
   → Satisfied within the MVP itself, not just claimed: recording observation dates makes staleness visible, and the MVP now includes actually re-running the same ingestion/split pipeline against a second small dataset (Section 4) and showing at least one record flow through end-to-end on camera: real evidence of reusability rather than a narrated aspiration. Full automated "freshness" (scheduled re-checks) and a fuller multi-municipality config remain stretch goals (Section 4).

## 6. Data & licence caveats to respect

From the Starter Files & Source Guide (agent.md, Source 7), confirmed against the actual `source-metadata.json` now in the repo; all apply only if the team uses the Schoten KBO sample:

- It is a **partial sample, confirmed paged**: `source-metadata.json` records `"complete_municipality": false` and includes a live `next_page_url` for records 1000+: Schoten has more than 1,000 register entries in total; this file is the first page only, not the complete register and not a list of 1,000 verified active businesses.
- It **mixes 457 legal entities and 543 establishment units** in one table; only establishments carry `Ondernemingsnr_maatsch_zetel`, and legal status is recorded on legal entities only.
- **Registry identifiers must be imported as text**: leading zeros are lost otherwise.
- **Activity fields are sparse**: the VAT activity code (`NACE_hoofdact_BTW`) is empty for every row (`source-metadata.json`: `missing_vat_activity_code_rows: 1000`); an RSZ activity code exists for only 81 rows (`missing_rsz_activity_code_rows: 919`).
- **Most parent enterprises are outside the sample**: only 28 of 543 establishments have their parent among the 1,000 rows.
- **Some coordinates need validation**: a few points fall well outside Schoten.
- **Placeholder dates** in the GeoJSON: `1900-01-01` and `9999-12-31` mean "not set" / "open-ended," not real dates; do not treat them as real.
- **The exact underlying federal KBO snapshot date is not stated**; the publisher notes a lag of one to three days behind the federal register.
- **Licence and attribution (KBO sample only):** published under the Flemish Modellicentie Gratis Hergebruik v1.0; if used, the required attribution text is: *"publieke KBO gegevens, verrijkt met adressen uit het Vlaamse Adressenregister."* This licence covers the KBO sample only, not any other document.
- **Optional external sources** (maps, listings, permit records, websites) are not supplied with the pack and may need their own account, key or agreement; pick sources the team can actually reach today.
- **Scraping vs. official APIs**: Google Maps and Trustpilot's own terms of service restrict scraping their pages directly. Use the official Google Places API and Trustpilot Business API instead: both need the team's own account/key (not supplied), which is exactly why the plan mocks these responses for the parts not yet wired to live credentials (Section 3.2, Section 4).
- **AI voice-agent calls raise a consent/framing question**, not just a technical one. For the hackathon demo this is fine, but the video should frame it as a municipality-initiated verification call (not an anonymous cold call), and in a real deployment this would need an explicit opt-in/consent framing per business.
- Two items sometimes mentioned informally are **not actually in the starter pack** and should not be assumed available: a synthetic village corpus and a verified reference-question set (agent.md, "Additional starter materials").

## 7. Suggested tooling

The hackathon requires no specific stack, model or provider (agent.md, Submission & Practical FAQ: "Do we have to use specific tools, models or providers? No."). The following partner credits are available per team member as optional aids only, not requirements:

- **Codex**: $100 in Codex credits per team member, useful for pairing on ingestion/enrichment code.
- **OpenAI API**: $50 in API credits per team member, useful if the team wants a model to help summarize evidence or normalize matches.
- **Supabase**: $25 credit per participant, a possible (not required) place to persist register + enrichment + decision data (redeem by 25 Jan 2027).
- **ElevenLabs**: one free month of Creator per participant. Directly relevant here beyond the pitch-video narration: it's a plausible fit for the AI voice-agent confirmation-call feature (Section 3.2) as well, and using it there (not just for narration) is what would make the project eligible for the "Best Project Built with ElevenLabs" award track.
- **OpenStreetMap / Overpass API**: free, no account or key required, unlike Google Maps Platform or Trustpilot's Business API; the one source in the team's chosen set with zero credential risk on the day.

Redemption details, codes and account setup are covered in the Partner Credits page (agent.md, Source 8) and are delivered by email; this plan does not confirm any credit has actually been issued or redeemed.

## 8. Timeline for the day

Mapped to the actual programme (agent.md, Source 1 / Source 6):

| Time | Programme | Suggested team focus |
|---|---|---|
| 09:00–09:30 | Doors, check-in, kickoff | Form team, pick challenge and municipality/street |
| 10:00–10:35 | Build starts | Follow (or adapt) the suggested first-35-minutes flow: load CSV as text, split enterprises/establishments, pick one street, list its records |
| 10:35–12:00 | Build | Compare 5–10 records against one public source; start the review-table UI; sketch the confirm/reject interaction |
| 12:00–13:00 | Lunch | n/a |
| 13:00–14:30 | Build resumes, mentoring | Finish MVP: working confirm/reject, evidence panel, at least one full row end-to-end, second-dataset re-run (see §4); grab an officer-mentor for the Section 9 questions |
| 14:30–15:00 | Build | Stretch goals only if the MVP (including the second-dataset check) is already solid; otherwise keep polishing/fixing the MVP |
| ~15:00–15:15 | Feature freeze | Stop building. Freeze the prototype; label what's real vs mocked; do not start anything new after this point |
| 15:15–15:30 | Final check | Do one clean run-through of the demo path you'll record |
| 15:30–16:00 | Record, upload, verify | Record the 3-minute video against the FAQ's own segment timing (agent.md, Source 6, "Suggested video structure"): 0:00–0:30 the officer's problem, 0:30–1:30 workflow/evidence screen recording, 1:30–2:20 architecture/tools/what's real vs mocked, 2:20–3:00 value/limits/reuse; record in **Dutch or English**; upload to YouTube; **complete the private-window playback check** (it must play without sign-in or an access request) |
| by 16:00–16:15 | Submit | Submit the YouTube link via the Google Form, leaving genuine buffer before the hard 16:30 cutoff |

**Do not start recording after 15:30.** Late submissions are not accepted at 16:30 (agent.md, Source 6), and an unplayable or still-processing video at the deadline scores zero regardless of build quality: YouTube upload/processing time and the required private-window playback check both need real buffer, not a 30-minute squeeze. Upload and the playback check must be fully complete with time to spare before 16:30, not still in progress at it.

## 9. Open questions / what to validate with an officer-mentor

Officers are present as mentors and are represented on the jury throughout the day (agent.md, "People" and Challenge 1 brief). Bring these:

1. When the register says "active" but we find no public evidence, what threshold of evidence would make you, as an officer, actually flag it for follow-up rather than ignore it?
2. For an establishment whose parent enterprise/registered seat is elsewhere, what do you actually need to see about the enterprise (beyond the establishment address) to act on it?
3. If contact information is unknown, is "contactgegevens onbekend" (or an equivalent plain statement) actually useful to you, or do you need a next-step suggestion instead?
4. How would you want a confirmed correction to actually reach your workflow: exported to a file, pushed to your own system, or just visible in this tool?
5. What would "reusable for another municipality" concretely mean for your own service: same street-level workflow with different data, or something else entirely?

Note on language (updated): the Submission & Practical FAQ (agent.md, Source 6, "Which language do we work in?") sits on the general practical page, not under either challenge's own brief, and states plainly: *"Your pitch video must be in Dutch or English. Keep officer-facing answers and interface text in Dutch. Team discussions and technical documentation can be in Dutch or English."* Because this question is asked and answered at the whole-hackathon level (the same page that covers submission format, judging and the programme for both challenges), it applies to Challenge 1 as much as Challenge 2, not only to the challenge whose own brief happens to repeat it. Treat this as settled, not open: **the pitch video itself may be in Dutch or English, but any officer-facing screen text/UI copy in the prototype should be in Dutch.** This plan (an internal team document) stays in English by design; only the demoed interface text is affected.
