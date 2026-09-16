# Challenge 2 · Answer Like the Expert: Solution Plan

**For:** a team of up to 5 people, ~6 hours of real build time (10:00–16:30, minus lunch 12:00–13:00) at the PROV-AI Public AI Hackathon, 16 September 2026, AP Hogeschool Campus Spoor Noord, Antwerp.

**Grounded in:** `agent.md`, specifically Source 4 (Challenge 2 brief), Source 5 (Challenge 2 Examples & Technical Guidance), Source 7 (Starter Files & Source Guide), Source 6 (Submission & Practical FAQ), and Source 8 (Partner Credits). Every claim below cites which of these it comes from. Where `agent.md` marks something optional or an example, this plan repeats that framing rather than treating it as a requirement.

---

## 1. Problem restated

Local economy officers in the Province of Antwerp answer entrepreneur questions (permits, market stalls, terraces, opening a shop, signage, inspection letters) by manually searching documents, websites and old emails spread across four levels of government (federal, Flemish, provincial, municipal) plus a shared mailbox of previous replies (Source 5, "Officer context"). A typical reply takes **about forty minutes** of searching across tabs and PDFs (Source 5). When an officer is away or leaves the role, colleagues struggle to recover the same knowledge. One officer put it bluntly: *"That knowledge is in my head."* (Source 5, quoted). Interviews also surfaced explicit concern about **AI-generated errors**: officers need to see the supporting passage, check whether a source applies to their municipality and question, and spot outdated or missing information before they rely on an answer (Source 4, "The problem"; Source 5). This is the problem our workflow must solve: not "build a chatbot," but "help the officer verify, not just receive, an answer."

## 2. Proposed workflow

End-to-end flow, officer-facing text in Dutch throughout (mandatory per Source 6, "Which language do we work in?"):

1. **Officer asks a question in Dutch**, in plain language, in a simple back-office interface (Source 4, "What to build").
2. **The system retrieves relevant passages** from whichever sources the team has configured for the chosen municipality/region; the retrieval mechanism itself is the team's choice; RAG is only **one optional approach** (Source 4, Source 5, Source 7).
3. **The system shows a finding** (a short summary of what the sources support) together with the **exact quoted passage** and a **clickable source link**, ideally deep-linked to the specific page/article: the worked example in Source 5 links directly to `#page=5` of the Schoten market-regulation PDF, with the passage continuing onto page 6. This deep-linking pattern is a *technique* shown in an optional example, not a mandated feature, but it directly serves success criterion 1 (Source 5, "Optional example · A market application").
4. **Uncertainty and applicability are shown alongside the finding**, e.g. a "Toepasselijkheid" field (municipality, type of request, document version/date, what was checked) and an "Onzekerheid" field (missing info, conflicting passages, conditions still to verify), mirroring the structure in Source 5's example briefing.
5. **Optional: an editable reply draft.** The officer can ask for a draft reply that reuses the same quotes and links. This is explicitly "one possible output," not a required format (Source 4, Source 5).
6. **Officer reviews, corrects, and approves before anything leaves the tool.** No automatic sending, ever: this is an explicit rule, stated three times in the source material (Source 1 quick orientation: "automatic sending is not allowed"; Source 4 success criterion 2: "keep human approval and no automatic sending"; Source 5 "Human review": "never send automatically").

## 3. Architecture sketch

Concrete components a team can realistically scope for the day. None of the named technologies below are required: Source 6 ("Do we have to use specific tools...") states plainly: *"No. Choose any stack, model or architecture, local or hosted."*

- **Document ingestion with structural metadata.** Extract text but preserve, per chunk, the document title, issuing authority, legal level, date/"undated", status (in force / guidance / historical), page number, and chapter/article number where present (Source 5, "Optional first 35 minutes," step 2). This metadata is what makes citations and applicability checks possible later; it is more important than the extraction quality itself.
- **Retrieval layer.** Given a question, find candidate passages. RAG (embeddings + vector search) is **one optional approach** explicitly named in the brief (Source 4, Source 5, Source 7); a team could equally use keyword/full-text search over the small document set, a manually curated lookup table for the one chosen question, or an LLM given the full small corpus in context. Given the corpus size (nine PDFs total, Source 7), a lightweight approach is defensible for the day's MVP. Consider restricting retrieval to the active municipality's configured corpus rather than relying only on a prompt instruction (Source 5, "Source boundaries").
- **Citation/grounding mechanism.** Every sentence in a finding or draft that states a rule must point to a specific passage: document, page, article, quoted text (Source 5, "Optional first 35 minutes," step 3; "Grounding"). Flag or refuse claims that aren't backed by a retrieved passage.
- **Source management for officers.** A way for an officer (not an engineer) to add, remove or update a source document, ideally reflected within minutes: this is a "useful design ambition," not a hard requirement (Source 5, "Source updates"; Source 4 success criterion 3). For the hackathon this could be as simple as a folder-drop-and-reindex button with a visible "last updated" timestamp; full self-service tooling is a stretch goal (see Section 5).
- **Audit log.** Log each answer together with its sources and prompt history so it is traceable later (Source 4 success criterion 3; Source 5, "Audit and accessibility").
- **Optional storage/backend: Supabase.** Named in Source 7 (Partner Credits) as a $25-per-participant credit; entirely optional infrastructure choice for storing documents, chunks, logs, or the officer-facing app's data, not mandated by the challenge.
- **Optional model access: OpenAI API credits.** $50 per team member (Source 8): one optional way to get LLM calls for retrieval/generation/drafting; any other model or provider is equally acceptable per Source 6.

## 4. Handling the four legal levels correctly

Source 5 is explicit and should be followed literally: *"Do not model them as an automatic ladder in which one level always overrides another. Show which sources you found at each level and how they relate to the question; when they seem to disagree, show both passages and flag it for the officer."*

Practical implementation for the day:
- Tag every retrieved passage with its legal level (federal / Flemish / provincial / municipal) using the metadata captured at ingestion (Section 3).
- In the finding shown to the officer, group or label passages by level rather than silently merging them into one answer.
- If two passages from different levels (or the same level) appear to say different things, **show both quotes side by side** and add a visible flag (e.g. "Tegenstrijdige bronnen: controleer") rather than picking one automatically.
- Do not attempt to encode a general-purpose legal hierarchy/override engine: the brief frames "representing all four legal levels" as **supporting guidance for extending the approach**, not an additional judged criterion (Source 5, closing note: "The original brief's ambition to represent all four legal levels and scale across provinces... is supporting guidance for extending the approach, not an additional criterion").

## 5. MVP scope for the day vs stretch goals

**Realistic MVP (~6 hours):**
- One well-scoped officer question. The Schoten market-stall question (*"Ik wil een vaste standplaats op de markt in Schoten. Hoe dien ik een aanvraag in?"*) is an **optional example** the starter pack directly supports (Source 4, Source 5); a team may use it as-is or substitute a different question/municipality inside the Province of Antwerp (Source 4: "Choose another question or a location... if it better fits your idea").
- 2–3 source documents relevant to that one question (e.g., for the market example: the Schoten market regulation and the market/fair fee regulation, both listed in Source 7's RAG table).
- A citation-grounded finding: quoted passage + page/article + clickable link, per Section 2.
- Visible uncertainty/applicability fields.
- Manual officer review step in the UI (approve/correct), with no send action wired up.
- A basic audit log entry per answer (question, sources used, timestamp); even a simple append-only record satisfies the spirit of Source 4 success criterion 3.

**Stretch goals (only if MVP is done early):**
- Full coverage of all four legal levels for the chosen question, with the conflict-flagging UI from Section 4.
- Multi-municipality reuse (swap the configured corpus/municipality without code changes).
- Self-service source management UI for non-technical officers (add/remove/update documents).
- Near-real-time reflection of source updates (Source 5's "within minutes" ambition).
- An editable reply-draft generator (Section 2, step 5) if not already built as part of MVP.

## 6. Mapping to the three official success criteria

Per Source 4, judging is against exactly these three criteria:

1. **Accurate source-backed answers**: "answer clearly in Dutch with exact supporting passages and clickable source links, use applicable sources, and acknowledge gaps and uncertainty." → Satisfied by Section 2 (Dutch UI, quoted passage, clickable deep link) and Section 3's citation/grounding mechanism, plus the visible "Onzekerheid"/"Toepasselijkheid" fields.
2. **Officer-controlled workflow**: "help the officer inspect evidence, correct findings and decide what to communicate in a simple interface... keep human approval and no automatic sending." → Satisfied by Section 2's mandatory review/approve step and the explicit absence of any auto-send action; the optional editable draft (step 5) supports this without being required.
3. **Maintainable, traceable knowledge**: "let officers update sources without technical help, keep answer and source history traceable, and make the approach reusable." → Satisfied by Section 3's source-management approach (MVP: simple; stretch: self-service) and the audit log; reusability is supported by keeping legal-level and municipality tagged as metadata rather than hard-coded.

## 7. Data & document caveats to respect

From Source 7's "How to treat this collection" (RAG/ folder, nine PDFs, optional starter material):

- **Mixed types and dates.** The collection mixes legislation (a bylaw, a fee regulation, a royal decree), guidance (VLAIO, FAVV, Omgevingsloket), and undated or historical material. Keep this distinction in metadata and surface it in the answer.
- **HISTORICAL files must never silently answer a current-rules question.** Three files are explicitly marked HISTORICAL (a 2022/2023 FAVV inspection guide, a 2006 royal decree on FAVV approvals, a 2019 Omgevingsloket manual for retail activities): "Historical material is background, not evidence of current rules. Never let a HISTORICAL file answer a question about today without saying so." If a HISTORICAL source is the only match, the UI must flag it, not present it as current.
- **Undated material needs applicability checked.** The Schoten terrace/display regulation is explicitly undated ("applicability to be verified").
- **Extraction can break structure.** Text extraction can lose table formatting, section symbols (§), footnotes, and council-minutes structure; check extractions against the original page (Source 7; also Source 5's suggested 35-minute exercise step 2, comparing extracted text to page 5 of the original PDF).
- **Licences differ per publisher.** The KBO sample's open-data licence does not cover these PDFs; check each publisher's terms before any reuse beyond the hackathon (Source 7).
- **The collection is incomplete.** Three municipal documents from one municipality, one provincial regulation, and a handful of federal/Flemish documents: "most applicable legislation is not here" (Source 7). Do not present the demo's answer as a complete legal picture; say explicitly what was and wasn't checked.
- **Not supplied, do not assume they exist:** a synthetic village corpus, a four-level diagram, and a verified reference-question set were referenced in earlier materials but are not in the 7 September starter pack; their availability is unconfirmed (Source 1, "Additional starter materials"; Source 5).

## 8. Suggested tooling (all optional)

Per Source 6 ("Do we have to use specific tools, models or providers?"): *"No. Choose any stack, model or architecture, local or hosted."* The following partner credits exist and can help, but are optional aids only (Source 8, Source 1 prize/credit tables):

- **Codex**: $100 in credits per team member, for coding assistance.
- **OpenAI API**: $50 in credits per team member, one optional way to call a model for retrieval, generation or drafting.
- **Supabase**: $25 credit per participant, one optional backend/storage option (redeem by 25 January 2027 per Source 8; not a hackathon-day deadline).
- **ElevenLabs**: one free month of Creator per participant. Using ElevenLabs also makes the project eligible for the separate **Best Project Built with ElevenLabs** award track (Source 1, "Awards"; Source 6, "How do the four prize tracks work?"). This is a distinct, additional award category, not part of the Challenge 2 judging criteria, only relevant if the team has a genuine voice/audio use case.

No specific provider, model, or architecture is required for Challenge 2 itself.

## 9. Timeline for the day

Based on the actual programme (Source 1, Source 6):

| Time | Phase |
| --- | --- |
| 09:00–09:30 | Doors open, check-in, kickoff & challenge briefing |
| 10:00 | Team formation & build starts. Confirm the one officer question and municipality/region the team will target; skim the starter RAG documents' dates/status (Section 7) |
| 10:00–12:00 | Ingest 2–3 chosen documents with page/article metadata; stand up a minimal retrieval mechanism; get one end-to-end "question in → cited passage out" path working, even ungrounded/rough |
| 12:00–13:00 | Lunch |
| 13:00–15:00 | Build continues, mentoring available (bring officer-mentors the open questions in Section 10); add uncertainty/applicability display, the review/approve step, and the audit log; polish the Dutch officer-facing copy |
| 15:00–16:00 | Freeze features; test the one full workflow end-to-end; record the 3-minute pitch video (structure per Source 6: problem 0:00–0:30, workflow/evidence 0:30–1:30, how it was built 1:30–2:20, value/limits/reuse 2:20–3:00); upload to YouTube and check it plays in a private browser window without sign-in |
| 16:00–16:30 | Submit the YouTube link via the Google Form; buffer time before the hard 16:30 deadline (late submissions are not accepted, Source 6) |
| 16:30 | Submissions close, judging starts |

## 10. Open questions / what to validate with an officer-mentor

Local economy officers are available as mentors and sit on the jury (Source 4, Source 6). Bring sharp, specific questions rather than general ones:

1. For the chosen question (e.g. the market-stall example), **which of the retrieved passages would you actually trust, and which would you want double-checked before replying to an entrepreneur?**
2. How do you currently decide **whether a document still applies** to a given case (e.g. an undated regulation like the Schoten terrace rules), what cues do you look for?
3. When federal, Flemish, provincial and municipal sources seem to say different things in practice, **what do you currently do**, and does our "show both, flag it" approach (Section 4) match how you'd want to see that surfaced?
4. If you had to **add or correct a source document yourself**, what would make that easy enough to actually do without asking IT for help?
5. Would an **editable reply draft** actually save you time over your current workflow, or would you rather just get the finding + citations and write the reply yourself?
