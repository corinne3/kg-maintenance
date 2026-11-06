# Where enterprise knowledge graphs break: maintenance and HR

Two domains, one stack:

- **Maintenance**: real public data, the FAA *Service Difficulty Reports* (2025), ATA chapter 29 (hydraulic power), 514 incident reports.
- **HR**: the real **ESCO** skills and occupations taxonomy (European Commission, v1.2.1, English and French) and a **synthetic** aerospace company of 161 employees. No real person.

The goal is not a demo that works. It is to **make visible and measurable** the problems teams run into when they build knowledge graphs from enterprise data, and to show which fixes work.

**Interactive explorer:** https://corinne3.github.io/kg-maintenance/ · **Data:** [FAA SDR](https://www.faa.gov/av-info/download_SDR) · [ESCO](https://esco.ec.europa.eu/en/use-esco/download)

## Maintenance: what the data shows

| Pitfall | Measured |
| --- | --- |
| Entity resolution | `PartName` just says "PUMP" in 117 reports. With that field only, **0** reports involve an engine-driven pump (EDP); reading the free text, **147**. The same pump is written **15** different ways. |
| False positives | In "ADD EMP:U349218", EMP is an employee number, not an *Electric Motor Pump*. |
| Wrong source data | 2 "PUMP" reports involve no pump at all; 2 reports describe the same event. |
| Mentioned ≠ failed | 12 "PUMP" reports mention several pumps, some only switched off or replaced as a precaution. |
| LLM extraction | On 19 reference cases: dictionary **10**, local LLM **12**, hybrid **15**. The LLM puts a part type outside the schema in **12%** of answers and altered 2 manual references. |
| Hubs | A naive 3-hop GraphRAG traversal returns **61%** of the graph. A schema-guided query returns only what answers the question. |
| Ontology gaps | "A320 family" means A318/A319/A320/A321. Without a model hierarchy, the guided query finds **24** EDP reports; with it, **51**. |
| Schema vs text | "Reservoir + OVERHEATED" returns **0** reports through `PartCondition`, but **12** reports describe it in the text. |
| Property graph vs RDF | Same facts, same answers. Provenance is an edge property in Cypher; in RDF every fact must be reified: **~10x more triples**. |

Details: [`outputs/step1_report.md`](outputs/step1_report.md) · [`outputs/step2_report_llama3.2_3b.md`](outputs/step2_report_llama3.2_3b.md)

## HR: the pitfalls maintenance could not show

| Pitfall | Measured |
| --- | --- |
| The reference is ambiguous too | 1,539 ESCO occupation labels (3%) point to more than one occupation. "Technicien **en** maintenance aéronautique" and "technicien **de** maintenance aéronautique" are two different ESCO occupations. |
| Linking to a taxonomy | 14 of 161 job titles are ambiguous even when copied from ESCO ("data scientist", "mechanical engineer"); company titles ("HRBP", "Mécano avion") are never found. |
| Garbage nodes hold the graph together | In the raw graph, Toulouse (French) and Bristol (English) are connected **only** by "Excel" and "communication". Remove them: **12 islands**, none spanning both sites. Linked to ESCO: 120 real shared skills. |
| Transitivity bias | "Worked on a project with an X, so could become an X": **72%** of suggestions share no skill with the target job; **80%** through the human hub. Schema-guided: 0%, and it can say "no suggestion". |
| Access control and inference | Hiding salary edges is not enough: **13 of 30 teams** have fewer than 5 people, so a per-team average reveals 27 individuals. Rule: k-anonymity in the query layer. |
| Change over time | Without validity dates, a reorganisation gives **4 employees two managers**; **12 people** hold an expired certification that a naive graph would still count. |
| One graph, two domains | Shared `PartType` and `AircraftModel` nodes: "EDP on the A320 family" → **51 FAA incidents** and **23 technicians** with a valid certification (5 more if expiry is ignored). |

Details: [`outputs/hr_report.md`](outputs/hr_report.md)

## Coverage: what the two cases show, and what they do not

| Pitfall | Covered | Where |
| --- | --- | --- |
| Synonyms / entity resolution | Yes | Maintenance (15 spellings) and HR (multilingual, gendered labels) |
| Vague "garbage" nodes | Yes | "PUMP" (maintenance); "Excel", "communication" (HR) |
| Legitimate hubs | Yes | "LEAKING", JASC 2910 (maintenance); the operations manager (HR) |
| Extraction hallucinations | Yes | 12% of LLM answers outside the schema; altered manual references |
| Source grounding (the remedy) | Yes | Every fact keeps its source and supporting text |
| Ambiguous reference data | Yes | ESCO labels shared by several concepts |
| Transitivity bias | Yes | HR internal mobility |
| Isolated islands | Yes | HR, French vs English sites |
| Access control and privacy | Yes | HR, sensitive edges and k-anonymity |
| Change over time | Yes | HR reorganisation and expired certifications (validity dates on edges) |
| Agentic retrieval with guardrails | Yes | Tool choice, argument validation, access control, escalation, decision trace |
| Inconsistent relation names | Partly | Relations imposed by a closed list; only the LLM's out-of-list answers show it |
| Global synthesis (community summaries, Microsoft GraphRAG) | **No** | Not implemented |
| Incremental updates at scale | **No** | Small, static files |

## The assistant: three ways to answer the same question

`streamlit run app.py` opens a local app on the maintenance graph. Type a question; it builds three contexts side by side and, optionally, asks the local LLM to answer from each:

| Method | What the LLM receives | Typical result |
| --- | --- | --- |
| Classic RAG | the 8 report texts most similar to the question (TF-IDF) | relevant examples, but no counting or aggregation |
| Naive GraphRAG | every triple within N hops of the entities in the question | overflows the context budget and gets cut |
| Schema-guided GraphRAG | one ontology path (part ← report → condition / manual task / aircraft): counts plus 8 source reports | compact and countable, but only as good as entity linking |

## The agent: choosing its own tools, inside guardrails

The assistant's second tab is an agent over **both** graphs. For each question it plans which tools to call, checks every argument against the ontology, checks the role's access rights, runs the tools, checks the results, and escalates to a person when it cannot answer. Every decision is written to a trace.

| Tool | What it does | Who may use it |
| --- | --- | --- |
| `maintenance_stats` | Schema-guided query on FAA reports (part, aircraft family, condition) | everyone |
| `report_search` | Text search on report narratives | everyone |
| `qualified_technicians` | People with a **valid** certification for a part type and aircraft family | everyone |
| `internal_mobility` | Moves supported by the person's skills vs the job's required skills | everyone |
| `team_aggregate` | Salary band or long absences over a team, refused under 5 people | HR only |

Routing is measured on 16 questions (`python eval_agent.py`): **rules** only, **LLM** only, or **hybrid** (rules first, LLM only when no rule applies). | Routing | Correct (of 16) | Time per question (laptop CPU) |
| --- | ---: | ---: |
| Rules only | 13 | 0.0 s |
| LLM only (`llama3.2:3b`) | 14 | 10.5 s |
| **Hybrid**: rules first, LLM only when no rule applies | **15** | 0.9 s |

- The rules were written while looking at the first 13 questions, so their score there is optimistic; they miss all 3 paraphrases.
- The LLM alone called one tool out of two on a two-part question (multi-step planning), and gave up on a question it could answer (it escalated rather than invent).
- The hybrid's only miss: a broad rule ("pump" → text search) fired on a paraphrase, so the LLM was never asked. Rules fail silently when they are too sure of themselves.

Details: [`outputs/agent_report_llama3.2_3b.md`](outputs/agent_report_llama3.2_3b.md)

Guardrails tested with a deliberately wrong LLM: unknown tool rejected ("delete_database"), invalid JSON escalated, "leaks" repaired to `LEAKING`, sensitive tool refused for the `employee` role even when the LLM picks it.

## Architecture: same stack, two domains

```
source data ──► domain mapping ──► FACTS (triple + provenance + validity / sensitivity) ──┬──► NetworkX graph ──► analysis
                                                                                        ├──► CSV + Cypher ──► Neo4j / FalkorDB
                                                                                        └──► Turtle (RDF) ──► SPARQL (rdflib)
```

- `kgcore/`: generic (facts, entity resolution, label linking to a taxonomy, graph, Cypher and RDF exports).
- `domains/maintenance_aviation/` and `domains/hr/`: everything specific to each domain (scope, ontology, dictionaries, mapping, synthetic generator).
- Adding HR reused `kgcore/` and added one generic module (`kgcore/lexicon.py`) plus edge attributes (validity dates, sensitivity).

Design decisions: [`DECISIONS.md`](DECISIONS.md) · Cypher vs SPARQL: [`queries/README.md`](queries/README.md)

## Stack

Fully open source and local, on a laptop with 8 GB RAM and no GPU: Python, pandas, NetworkX, rdflib (SPARQL), Cypher export for Neo4j / FalkorDB, Ollama (`llama3.2:3b`) for LLM extraction, Streamlit.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# maintenance: download SDR-2025.csv from the FAA page into data/
python run_step1.py            # graph, step 1 report, figures, exports
python run_sparql.py           # same answers in SPARQL
ollama pull llama3.2:3b
python run_step2_llm.py --only-pump    # LLM extraction on the 117 "PUMP" reports (~30 min on CPU)
# HR: download ESCO v1.2.1 classification CSV (en + fr) into data/esco/en and data/esco/fr
python -m domains.hr.generate  # synthetic company (already in data/hr_synthetic/)
python run_hr.py               # HR report and figures
python build_explorer.py       # regenerates outputs/explorer.html and docs/index.html (the published page)
python eval_agent.py           # agent routing: rules vs LLM vs hybrid (~10 min on CPU)
streamlit run app.py           # the assistant: compare retrieval + agent
```

## Transparency

Public FAA and ESCO data; HR employees are synthetic. Code written with an AI assistant; framing, design decisions and analysis are mine. The reference annotations in `data/ground_truth.xlsx` were made by a large LLM (Claude), not by a maintenance expert.

— Corinne Bergès
