# Choosing Your Challenge: Quick Comparison

**Use this before 10:00 on 16 September 2026.** Teams pick one challenge at team formation, the same moment build time starts (agent.md, Source 1: "Programme"). Don't spend build time re-reading both full plans; this page exists so you don't have to. Full detail lives in [`challenge1-plan.md`](./challenge1-plan.md) and [`challenge2-plan.md`](./challenge2-plan.md); this page only surfaces the differences that should actually drive your choice.

## The three axes that matter

### 1. External dependency risk

- **Challenge 2's MVP corpus is fully self-contained.** The nine RAG PDFs are in the starter ZIP already (agent.md, Source 7), so you can build and test entirely offline once downloaded. No external API keys are needed or supplied.
- **Challenge 1's core "reliable data" criterion requires checking register records against a *live* public source** (a map service, business listings, a website): agent.md is explicit that no external API keys are supplied with the pack, and any such source "may need their own account, key or agreement" (Source 7). This is workable (manual checking is explicitly acceptable, see `challenge1-plan.md` §3.2), but it's real extra labour and carries scraping/rate-limit/venue-Wi-Fi risk that Challenge 2 mostly avoids.

**If your team wants to minimize infrastructure/connectivity risk on the day, Challenge 2 has the edge.**

### 2. Depth of Dutch required

Both challenges require Dutch officer-facing UI text. The general Submission & Practical FAQ ("Which language do we work in?", agent.md Source 6) is a whole-hackathon page, not scoped to one challenge: *"Keep officer-facing answers and interface text in Dutch."* (The pitch **video** itself may be in Dutch or English either way.) So presence-of-Dutch isn't a differentiator any more, but *how demanding* the Dutch is still differs:

- **Challenge 2 needs close reading of Dutch legal/regulatory source text**, precise enough to quote it exactly: misquoting a legal passage is a real failure mode there (agent.md, Source 4: "answer clearly in Dutch").
- **Challenge 1 needs Dutch for UI labels/status text** (e.g. "confirm"/"reject", certainty levels, "contact unknown"): comfortably translatable short phrases, not close legal reading.

**A confident Dutch reader helps on either challenge; a team whose Dutch is more "conversational than legal-precise" carries less risk on Challenge 1 than Challenge 2.**

### 3. Team skill fit

Straight from agent.md's own framing (Source 1, "Choose your challenge"):

- **Challenge 1**: *"Good fit if you like data matching, maps, verification and interface design."* Core work is record linkage (enterprise ↔ establishment ↔ evidence), confidence scoring, and a review UI.
- **Challenge 2**: *"Good fit if you like language models, document search, legal text and interface design."* Core work is document ingestion with structural metadata, retrieval/citation, and careful legal-text handling.

## Quick decision guide

| If your team... | Lean toward |
|---|---|
| Has strong data-wrangling/matching instincts, is comfortable with ambiguous "is this still open?" judgment calls, and wants to avoid depending on external sites during the event | **Challenge 1** |
| Has LLM/retrieval experience, at least one confident Dutch reader, and wants a self-contained, offline-buildable dataset | **Challenge 2** |
| Wants Dutch limited to short UI labels, not close legal reading | **Challenge 1** |
| Wants the lowest infrastructure/connectivity risk | **Challenge 2** (corpus is fully supplied; no external site dependency) |

Neither challenge is "easier": both plans size their MVP to ~6 real build hours and both are judged on exactly three published success criteria for that challenge (agent.md, Source 2 and Source 4). Pick based on which risk profile and skill set your team actually has, not on perceived prestige of either track; a team can win only one award regardless of which challenge it chooses (agent.md, Source 1: "Each team can win only one award across all four tracks").

Once you've picked, go straight to the matching plan: [`challenge1-plan.md`](./challenge1-plan.md) or [`challenge2-plan.md`](./challenge2-plan.md).
