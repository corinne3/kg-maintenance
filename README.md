# Where maintenance knowledge graphs break

A case study on **real public data**: the FAA *Service Difficulty Reports* (2025), ATA chapter 29 (hydraulic power), 514 incident reports.

The goal is not a demo that works. It is to **make visible and measurable** the problems teams run into when they build knowledge graphs from industrial maintenance data.

**Interactive explorer:** [link to be added when shared] · **Data:** [FAA SDR download page](https://www.faa.gov/av-info/download_SDR)

## What the data shows

| Pitfall | Measured |
| --- | --- |
| Entity resolution | `PartName` just says "PUMP" in 117 reports. With that field only, **0** reports involve an engine-driven pump (EDP); reading the free text, **147**. The same pump is written **15** different ways. |
| False positives | In "ADD EMP:U349218", EMP is an employee number, not an *Electric Motor Pump*. |
| Wrong source data | 2 "PUMP" reports involve no pump at all; 2 reports describe the same event. |
| Mentioned ≠ failed | 12 "PUMP" reports mention several pumps, some only switched off or replaced as a precaution. |
| LLM extraction | On 19 reference cases: dictionary **10**, local LLM **12**, hybrid **15**. The LLM puts a part type outside the schema in **12%** of answers and altered 2 manual references. |
| Hubs | A naive 3-hop GraphRAG traversal returns **61%** of the graph. A schema-guided query returns only what answers the question. |
| Ontology gaps | "A320 family" means A318/A319/A320/A321. Without a model hierarchy, the guided query finds **24** EDP reports; with it, **51**. |
| Schema vs text | "Reservoir + OVERHEATED" returns **0** reports through `PartCondition`, but **12** reports describe it in the text. The graph only knows what was extracted. |
| Property graph vs RDF | Same facts, same answers. Provenance is an edge property in Cypher; in RDF every fact must be reified: **~10x more triples**. |

Details: [`outputs/step1_report.md`](outputs/step1_report.md) · [`outputs/step2_report_llama3.2_3b.md`](outputs/step2_report_llama3.2_3b.md) · Design decisions: [`DECISIONS.md`](DECISIONS.md) · Cypher vs SPARQL: [`queries/README.md`](queries/README.md)

## The assistant: three ways to answer the same question

`streamlit run app.py` opens a local app. Type a question; it builds three contexts side by side and, optionally, asks the local LLM to answer from each:

| Method | What the LLM receives | Typical result |
| --- | --- | --- |
| Classic RAG | the 8 report texts most similar to the question (TF-IDF) | relevant examples, but no counting or aggregation |
| Naive GraphRAG | every triple within N hops of the entities in the question | overflows the context budget and gets cut |
| Schema-guided GraphRAG | one ontology path (part ← report → condition / manual task / aircraft): counts plus 8 source reports | compact and countable, but only as good as entity linking |

## Architecture: same stack, another domain

```
FAA CSV ──► loader ──► domain mapping ──► FACTS (triple + provenance) ──┬──► NetworkX graph ──► analysis (hubs, paths)
                                                                       ├──► CSV + Cypher ──► Neo4j / FalkorDB
                                                                       └──► Turtle (RDF) ──► SPARQL (rdflib)
```

- `kgcore/`: generic (facts with provenance, entity resolution, graph, Cypher and RDF exports).
- `domains/maintenance_aviation/`: everything specific to the domain (scope, ontology, alias dictionary, mapping).
- Another domain (HR, supply chain…) = another folder under `domains/`. `kgcore/` stays unchanged.

## Stack

Fully open source and local, on a laptop with 8 GB RAM and no GPU: Python, pandas, NetworkX, rdflib (SPARQL), Cypher export for Neo4j / FalkorDB, Ollama (`llama3.2:3b`) for LLM extraction.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# download SDR-2025.csv from the FAA page above into data/
python run_step1.py            # graph, step 1 report, figures, exports
python run_sparql.py           # same answers in SPARQL
ollama pull llama3.2:3b
python run_step2_llm.py --only-pump    # LLM extraction on the 117 "PUMP" reports (~30 min on CPU)
python build_explorer.py       # regenerates outputs/explorer.html
streamlit run app.py           # the assistant
```

## Transparency

Public FAA data. Code written with an AI assistant; framing, design decisions and analysis are mine. The reference annotations in `data/ground_truth.xlsx` were made by a large LLM (Claude), not by a maintenance expert.

— Corinne Bergès
