"""Step 1 — Build the graph and measure the first pitfalls.

    python run_step1.py

Writes to outputs/:
  - step1_report.md          : the numbers and what they show
  - fig_pumps.png            : entity resolution (the "PUMP" case)
  - fig_hubs.png             : hubs
  - property_graph/*.csv     : nodes and edges, to load into Neo4j / FalkorDB
  - graph.ttl                : the same graph in RDF (Turtle)
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from domains.maintenance_aviation.mapping import MaintenanceMapper  # noqa: E402
from kgcore.export import cypher_import_script, export_property_graph, export_turtle  # noqa: E402
from kgcore.graph import build_graph, hubs, neighborhood, node_counts, typed_paths  # noqa: E402
from kgcore.loader import load_domain, load_records  # noqa: E402

OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
INK, MUTED, BLUE, GREY = "#1f2328", "#6e7781", "#2f6fb3", "#c9ced6"

PUMPS = ["ENGINE_DRIVEN_PUMP", "ELECTRIC_MOTOR_PUMP", "POWER_TRANSFER_UNIT", "RAM_AIR_TURBINE"]


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "-"


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GREY)
    ax.spines["bottom"].set_color(GREY)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.xaxis.grid(True, color="#eef0f3", linewidth=0.8)
    ax.set_axisbelow(True)


def main():
    cfg = load_domain("maintenance_aviation")
    df = load_records(cfg)
    mapper = MaintenanceMapper(cfg)

    facts, per_report = [], {}
    for _, row in df.iterrows():
        fs = mapper.facts(row)
        facts.extend(fs)
        per_report[row["OperatorControlNumber"]] = fs

    g = build_graph(facts)
    n_reports = len(df)
    labels = mapper.parts.labels

    # ------------------------------------------------------------ pitfall: entity resolution
    structured_values = Counter(df["PartName"].fillna("").str.upper().str.strip())
    surfaces = defaultdict(Counter)            # canonical type -> spellings found
    for f in facts:
        if f.relation == "INVOLVES_PART" and f.source == "dictionary":
            surfaces[f.object.key][f.evidence] += 1

    def parts_of(fs, source):
        return {f.object.key for f in fs if f.relation == "INVOLVES_PART" and f.source == source}

    # The pump case: the structured field only says "PUMP"
    pump_reports = [rid for rid, fs in per_report.items()
                    if "HYDRAULIC_PUMP_UNSPECIFIED" in parts_of(fs, "structured")]
    outcome = Counter()
    conflicts = []
    for rid in pump_reports:
        txt = parts_of(per_report[rid], "dictionary")
        specific = [p for p in PUMPS if p in txt]
        if len(specific) == 1:
            outcome[specific[0]] += 1
        elif len(specific) > 1:
            outcome["AMBIGUOUS"] += 1
            conflicts.append((rid, specific))
        elif "HYDRAULIC_PUMP_UNSPECIFIED" in txt:
            outcome["STILL_VAGUE"] += 1
        else:
            outcome["NO_PUMP_IN_TEXT"] += 1

    # How many reports involve an EDP, depending on the source used?
    def count_reports(part, sources):
        return sum(1 for fs in per_report.values()
                   if any(f.relation == "INVOLVES_PART" and f.object.key == part
                          and f.source in sources for f in fs))
    edp_struct = count_reports("ENGINE_DRIVEN_PUMP", {"structured"})
    edp_text = count_reports("ENGINE_DRIVEN_PUMP", {"structured", "dictionary"})
    emp_struct = count_reports("ELECTRIC_MOTOR_PUMP", {"structured"})
    emp_text = count_reports("ELECTRIC_MOTOR_PUMP", {"structured", "dictionary"})

    no_part = sum(1 for fs in per_report.values()
                  if not any(f.relation == "INVOLVES_PART" for f in fs))

    # ------------------------------------------------------------ pitfall: hubs
    top_hubs = hubs(g, top=12)
    edp = "PartType:ENGINE_DRIVEN_PUMP"
    total_nodes = g.number_of_nodes()
    hub_threshold = 50
    und_deg = {n: d for n, d in __import__("networkx").Graph(g).degree()}
    hub_set = {n for n, d in und_deg.items()
               if d >= hub_threshold and g.nodes[n]["type"] != "Report" and n != edp}
    rag = []
    for hops in (1, 2, 3, 4):
        naive = neighborhood(g, edp, hops)
        guarded = neighborhood(g, edp, hops, blocked=hub_set)
        rag.append((hops, len(naive), len(guarded)))
    # Schema-guided query: part <- report -> condition / AMM task
    typed = (typed_paths(g, edp, [("INVOLVES_PART", "in"), ("HAS_CONDITION", "out")])
             | typed_paths(g, edp, [("INVOLVES_PART", "in"), ("REFERENCES", "out")]))
    typed_cond = Counter()
    for u, v, d in g.in_edges(edp, data=True):
        if d["relation"] == "INVOLVES_PART":
            for _, c, d2 in g.out_edges(u, data=True):
                if d2["relation"] == "HAS_CONDITION":
                    typed_cond[g.nodes[c]["label"]] += 1

    # ------------------------------------------------------------ exports
    export_property_graph(facts, OUT / "property_graph")
    export_turtle(facts, OUT / "graph.ttl")
    cypher_import_script(cfg["ontology"], OUT / "property_graph" / "import_neo4j.cypher")
    n_triples_unique = len({(f.subject.id, f.relation, f.object.id) for f in facts})
    rdf_total = n_triples_unique + 2 * total_nodes + 7 * len(facts)

    # ------------------------------------------------------------ figures
    order = ["ENGINE_DRIVEN_PUMP", "ELECTRIC_MOTOR_PUMP", "POWER_TRANSFER_UNIT",
             "RAM_AIR_TURBINE", "AMBIGUOUS", "STILL_VAGUE", "NO_PUMP_IN_TEXT"]
    names = {"ENGINE_DRIVEN_PUMP": "Engine-driven pump (EDP)",
             "ELECTRIC_MOTOR_PUMP": "Electric motor pump (ACMP/EMDP)",
             "POWER_TRANSFER_UNIT": "PTU", "RAM_AIR_TURBINE": "RAT",
             "AMBIGUOUS": "Several pumps mentioned (ambiguous)",
             "STILL_VAGUE": "Text just as vague (\u201cHYD PUMP\u201d)",
             "NO_PUMP_IN_TEXT": "No pump found in the text"}
    vals = [outcome.get(k, 0) for k in order]
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    colors = [BLUE] * 4 + [GREY] * 3
    bars = ax.barh([names[k] for k in order][::-1], vals[::-1], color=colors[::-1], height=0.6)
    for b, v in zip(bars, vals[::-1]):
        ax.text(b.get_width() + 0.8, b.get_y() + b.get_height() / 2, str(v),
                va="center", fontsize=9, color=INK)
    style(ax)
    ax.set_title(f"The structured field says \u201cPUMP\u201d ({len(pump_reports)} reports). "
                 "What does the text say?", loc="left", fontsize=11, color=INK)
    ax.set_xlabel("Number of reports (FAA SDR 2025, ATA 29)", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_pumps.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.8), dpi=150)
    hl = [f"{g.nodes[n]['label']}  ({t})" for n, t, _ in top_hubs][::-1]
    hv = [d for _, _, d in top_hubs][::-1]
    bars = ax.barh(hl, hv, color=BLUE, height=0.6)
    for b, v in zip(bars, hv):
        ax.text(b.get_width() + 3, b.get_y() + b.get_height() / 2, str(v),
                va="center", fontsize=9, color=INK)
    style(ax)
    ax.set_title("Most connected nodes (excluding reports)", loc="left", fontsize=11, color=INK)
    ax.set_xlabel("Number of distinct neighbours", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_hubs.png")
    plt.close(fig)

    # ------------------------------------------------------------ report
    nc = node_counts(g)
    L = ["# Step 1 — Results", "",
         f"Scope: **{n_reports} reports**, FAA SDR 2025, ATA chapter 29 (hydraulic power).", "",
         "## The graph", "", "| Node type | Count |", "| --- | ---: |"]
    L += [f"| {t} | {c} |" for t, c in nc.most_common()]
    L += ["", f"- {len(facts)} facts extracted, each with its provenance; "
              f"{n_triples_unique} distinct triples once duplicates are merged.",
          f"- Reports with no recognised part: {no_part} ({pct(no_part, n_reports)}).", ""]

    L += ["## Pitfall 1 — Entity resolution: the pump case", "",
          f"- The structured field `PartName` is just \"PUMP\" in **{len(pump_reports)} reports**.",
          "- That field does not say which pump. The free text often does:", "",
          "![pumps](fig_pumps.png)", "",
          "| Question | Structured field only | Structured + text |", "| --- | ---: | ---: |",
          f"| Reports involving an engine-driven pump (EDP) | {edp_struct} | {edp_text} |",
          f"| Reports involving an electric motor pump | {emp_struct} | {emp_text} |", "",
          f"- **{outcome.get('AMBIGUOUS', 0)} reports mention several pumps.** A dictionary finds "
          "the words, not which pump failed. That is the job of step 2 (LLM extraction).",
          "- **False positive found by checking by hand:** in \"ADD EMP:U349218\", EMP is an "
          "employee number, not an Electric Motor Pump. All 5 occurrences of \"EMP\" in scope were "
          "employees. Rule fixed. Lesson: validate a dictionary on real examples, not only at design time.", ""]
    if conflicts:
        L += ["Examples of ambiguous reports:", ""]
        texts = df.set_index("OperatorControlNumber")["Discrepancy"]
        for rid, sp in conflicts[:3]:
            L += [f"- `{rid}` ({', '.join(sp)}): \"{str(texts[rid])[:260]}…\""]
        L += [""]
    L += ["### Spellings found in the text (top 8 types)", "",
          "| Canonical type | Distinct spellings | Examples |", "| --- | ---: | --- |"]
    for key, cnt in sorted(surfaces.items(), key=lambda kv: -sum(kv[1].values()))[:8]:
        ex = ", ".join(f"`{s}` ({n})" for s, n in cnt.most_common(5))
        L += [f"| {labels[key]} | {len(cnt)} | {ex} |"]
    L += ["", "Distinct spellings include engine numbers and plurals (`ENG 1 PUMP`, `ENG 2 PUMP`). "
          "Without them, \"engine-driven pump\" is still written 15 different ways.", ""]
    unm = Counter(mapper.unmapped_part_names)
    L += [f"### Unrecognised `PartName` values: {len(unm)} values, {sum(unm.values())} reports", "",
          ", ".join(f"`{k}` ({v})" for k, v in unm.most_common(15)), "",
          "Each unrecognised value is an ontology decision: add it, group it, or ignore it.", ""]

    L += ["## Pitfall 2 — Hubs", "", "![hubs](fig_hubs.png)", "",
          "A naive GraphRAG starts from the entity in the question and retrieves everything within "
          "N hops. Test question: *\"What problems affect engine-driven pumps (EDP)?\"*", "",
          f"| Hops | Nodes retrieved (naive) | % of graph | Refusing to traverse hubs (>= {hub_threshold} neighbours) |",
          "| ---: | ---: | ---: | ---: |"]
    for hops, a, b in rag:
        L += [f"| {hops} | {a} | {pct(a, total_nodes)} | {b} |"]
    L += ["", f"- Blocked hubs: {', '.join(sorted(g.nodes[n]['label'] for n in hub_set))}.",
          "- At 3 hops, the naive traversal goes through hubs (JASC code, \"LEAKING\" condition, "
          "manufacturer…) and returns most of the graph: the LLM is flooded.",
          "- Blocking hubs barely reduces the noise and can cut useful paths. "
          "The threshold is a decision ([D6] in DECISIONS.md).",
          "- **What works: querying through the schema.** The path "
          "`part <- report -> condition / AMM task` (one Cypher or SPARQL query) returns "
          f"**{len(typed)} nodes**, each linked to the question by a meaningful relation. "
          "Most frequent conditions for EDPs: "
          + ", ".join(f"{k} ({v})" for k, v in typed_cond.most_common(4)) + ".",
          "- Limit: `PartCondition` describes the part in the structured field. If a report is about "
          "an EDP but the structured field names a hose, the condition is not necessarily the EDP's.",
          "- Conclusion: the graph adds value when it is traversed through its ontology, "
          "not when it is pulled in \"N hops at a time\".", ""]

    L += ["## Pitfall 4 — Property graph vs RDF", "",
          "- `property_graph/nodes.csv`, `edges.csv`: provenance (source, report, supporting text) "
          "is simply a **property of the edge**.",
          f"- `graph.ttl` (RDF): {n_triples_unique} distinct triples. An RDF triple cannot carry "
          f"properties, so each of the {len(facts)} facts is **reified** as an `rdf:Statement`. "
          f"Total: **{rdf_total:,} triples**, about {rdf_total / n_triples_unique:.0f}x more for the same information.",
          "- Both models give the same answers (checked: identical condition counts for EDPs in "
          "NetworkX and in SPARQL, see `run_sparql.py`).", ""]
    (OUT / "step1_report.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
