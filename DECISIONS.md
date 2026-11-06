# Design decisions

Each decision lists the options, the choice and the rationale. The code only applies these decisions.

## Decided

### D1 — Scope: ATA chapter 29 (hydraulic power), FAA SDR 2025
- Options: ATA 29 only (514 reports) · ATA 29 + 32 landing gear (~3x more) · A320 family, all chapters.
- **Choice: ATA 29 only.**
- Rationale: small enough for an LLM on a laptop CPU; Airbus and Boeing comparable (200 / 190 reports); contains the "PUMP" case.

### D2 — Part granularity: normalised part type
- Options: normalised type · part number · both.
- **Choice: normalised type** (e.g. "Engine-driven pump" groups EDP, ENG PUMP, ENGINE DRIVEN PUMP…).
- Rationale: the part number is missing in 59% of reports; entity resolution is what this case study is about.

### D3 — Graph model: property graph AND RDF, compared
- **Choice: both**, built from the same facts (`kgcore/facts.py`).
- Rationale: show the concrete difference (provenance, size, interoperability) instead of describing it.

### D9 — Use the LLM only where the dictionary fails
- Observation: on 19 reference cases, dictionary 10/19, LLM 12/19, and they fail on different reports.
- **Choice: hybrid rule.** Trust the dictionary when it finds 0 or 1 pump; ask the LLM only when it finds several. Result: 15/19.
- Rationale: on CPU the LLM costs ~16 s per report and invents types outside the schema in 12% of answers. It is worth its cost only on ambiguous cases, and its output must be validated against the ontology before it becomes a fact.

### D10 — Reference annotations made by a large LLM
- Options: maintenance expert · myself · a large LLM as reference.
- **Choice: a large LLM (Claude) annotated 20 "PUMP" reports** (`data/ground_truth.xlsx`, each row labelled).
- Rationale: fast, and it gives a consistent reference to compare the dictionary and the small local LLM. Limit: an LLM judging an LLM. In a real project, a sample would be validated by maintenance engineers.

### D11 — A model hierarchy in the ontology
- Observation: "A320 family" in a question matched only the A320 model: 24 EDP reports instead of 51 with A319 and A321.
- **Choice: `model_groups` in the config** ("A320 FAMILY" = A318, A319, A320, A321), used by entity linking. It can be switched off in the assistant to show the difference.

### D12 — When a schema filter returns nothing, relax it and say so
- Observation: "reservoir + overheat" gives 0 reports through `PartCondition`, 12 through the free text.
- **Choice:** the guided query falls back to the text and writes the fallback into the context, so the LLM and the user both see it.

### D13 — A second domain: HR, on real ESCO + a synthetic company
- Why: the maintenance graph is star-shaped around reports, so it cannot show transitivity bias, isolated islands, access control or change over time. People graphs can.
- Options: public CV datasets (real text, unclear licences and personal data) · real ESCO + synthetic employees.
- **Choice: real ESCO (English + French) + a synthetic company of 161 employees** (`domains/hr/generate.py`, fixed seed). Every synthetic file carries `synthetic=True`.
- Limit: the pitfalls are realistic but their size depends on how the synthetic data was generated (for example the 15% company-specific titles). The ESCO findings (ambiguous labels) are real.

### D14 — Sensitive data and time live on the edge
- **Choice:** facts carry attributes. `sensitive=True` for salary band and long absence; `valid_from` / `valid_to` for reporting lines and certifications.
- Rule: no aggregate on fewer than 5 people (k-anonymity), enforced in the query layer.

### D15 — An agent with narrow tools rather than free text-to-query
- Options: let the LLM write Cypher/SPARQL (text-to-query) · give it a few typed tools with allowed values.
- **Choice: five typed tools** whose arguments are checked against the ontology before they run; access rights per tool; no aggregate under 5 people; escalation to a person when no tool fits or no result is usable; a trace of every decision.
- Routing: same hybrid idea as extraction (D9): rules first, LLM only when no rule applies. Measured on 16 questions, 3 of them paraphrases the rules were not written for.
- Rationale: a 3B model on CPU is unreliable at writing queries; typed tools turn its mistakes into catchable validation errors instead of wrong answers.

## Open questions

### D4 — ACMP (Boeing, Bombardier) and EMDP / ELEC PUMP: one type or two?
- Current default: one type, "electric motor pump" (same function, keeps Airbus/Boeing comparable).
- Alternative: two types, closer to manufacturer vocabulary.

### D5 — Canadair (CNDAIR) and Bombardier (BOMBDR): merge?
- Current default: keep both FAA codes, and document the link.
- Alternative: merge under Bombardier (better for analysis, loses the trace of the source code).

### D6 — Hubs: how should GraphRAG traverse the graph?
- Observation: a naive 3-hop traversal from "EDP" returns 61% of the graph; blocking hubs only brings it to ~55%.
- Options: schema-guided queries (what works in step 1) · block hubs above a threshold · weight nodes by rarity.

### D7 — "The report mentions a part" is not "the part failed"
- Current: one relation, `INVOLVES_PART`.
- Proposal: two relations, `HAS_FAULTY_PART` and `MENTIONS_PART`, filled by the hybrid rule (D9).

### D8 — 55 unrecognised `PartName` values (101 reports)
- Examples: `ELEC CONNECTOR`, `MODULE`, `VALVE`, `FUSE`, `SWITCH`, `INDICATOR`…
- Add them to the ontology, group them ("electrical component"), or ignore them?

## Log

- 2026-11-04 — First LLM test: 110 s per report. Once the model stays loaded in memory: 16 s per report.
- 2026-11-04 — Two "PUMP" reports involve no pump (ELAC computer, brake line): the structured field can be wrong, not only vague.
- 2026-11-04 — Two reports describe the same event (SWAA2025102728412, SWAA2025102729004): duplicates in the source data.
- 2026-11-06 — Agent routing on 16 questions: rules 13, LLM 14 (10.5 s each), hybrid 15 (0.9 s each). Hybrid miss: an over-broad "pump → text search" rule pre-empted the LLM.
- 2026-11-06 — ESCO: 1,539 occupation labels (3%) point to more than one occupation; "technicien en" vs "technicien de" maintenance aéronautique are two occupations.
- 2026-11-06 — HR raw graph: Toulouse and Bristol connected only by "Excel" and "communication".
- 2026-11-06 — "Colleague of a colleague" mobility: 72% of suggestions share no skill with the target job.
- 2026-11-05 — "A320 family" query: 24 reports without the model hierarchy, 51 with it.
- 2026-11-05 — "Reservoir overheat": 0 reports through PartCondition, 12 through the text.
- 2026-11-04 — The LLM altered two maintenance manual references into plausible but wrong ones (29-11-51 for 29-11-11).
