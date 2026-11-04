"""Étape 1 — Construire le graphe et mesurer les deux premiers « os ».

    python run_step1.py

Produit, dans outputs/ :
  - etape1_rapport.md        : les chiffres et ce qu'ils montrent
  - fig_pompes.png           : os n°1, entity resolution (le cas des pompes)
  - fig_hubs.png             : os n°6, les hubs
  - property_graph/*.csv     : nœuds et arêtes, à charger dans Neo4j / FalkorDB
  - graphe.ttl               : le même graphe en RDF (Turtle)
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
    return f"{100 * a / b:.0f} %" if b else "-"


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

    # ------------------------------------------------------------ os n°1 : pièces
    structured_values = Counter(df["PartName"].fillna("").str.upper().str.strip())
    surfaces = defaultdict(Counter)            # type canonique -> variantes écrites
    for f in facts:
        if f.relation == "INVOLVES_PART" and f.source == "dictionary":
            surfaces[f.object.key][f.evidence] += 1

    def parts_of(fs, source):
        return {f.object.key for f in fs if f.relation == "INVOLVES_PART" and f.source == source}

    # Le cas des pompes : le champ structuré dit « PUMP »
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
            outcome["AMBIGU"] += 1
            conflicts.append((rid, specific))
        elif "HYDRAULIC_PUMP_UNSPECIFIED" in txt:
            outcome["TOUJOURS_IMPRECIS"] += 1
        else:
            outcome["PAS_DE_POMPE_DANS_LE_TEXTE"] += 1

    # Combien de rapports parlent d'une EDP ? selon la source utilisée
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

    # ------------------------------------------------------------ os n°6 : hubs
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
    # Requête guidée par le schéma : pièce <- rapport -> état / tâche AMM
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
    export_turtle(facts, OUT / "graphe.ttl")
    cypher_import_script(cfg["ontology"], OUT / "property_graph" / "import_neo4j.cypher")
    n_triples_unique = len({(f.subject.id, f.relation, f.object.id) for f in facts})

    # ------------------------------------------------------------ figures
    order = ["ENGINE_DRIVEN_PUMP", "ELECTRIC_MOTOR_PUMP", "POWER_TRANSFER_UNIT",
             "RAM_AIR_TURBINE", "AMBIGU", "TOUJOURS_IMPRECIS", "PAS_DE_POMPE_DANS_LE_TEXTE"]
    names = {"ENGINE_DRIVEN_PUMP": "Pompe moteur (EDP)",
             "ELECTRIC_MOTOR_PUMP": "Pompe électrique (ACMP/EMDP)",
             "POWER_TRANSFER_UNIT": "PTU", "RAM_AIR_TURBINE": "RAT",
             "AMBIGU": "Plusieurs pompes citées (ambigu)",
             "TOUJOURS_IMPRECIS": "Texte aussi imprécis (« HYD PUMP »)",
             "PAS_DE_POMPE_DANS_LE_TEXTE": "Aucune pompe trouvée dans le texte"}
    vals = [outcome.get(k, 0) for k in order]
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    colors = [BLUE] * 4 + [GREY] * 3
    bars = ax.barh([names[k] for k in order][::-1], vals[::-1], color=colors[::-1], height=0.6)
    for b, v in zip(bars, vals[::-1]):
        ax.text(b.get_width() + 0.8, b.get_y() + b.get_height() / 2, str(v),
                va="center", fontsize=9, color=INK)
    style(ax)
    ax.set_title(f"Le champ structuré dit « PUMP » ({len(pump_reports)} rapports). "
                 "Que dit le texte ?", loc="left", fontsize=11, color=INK)
    ax.set_xlabel("Nombre de rapports (FAA SDR 2025, ATA 29)", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_pompes.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.8), dpi=150)
    hl = [f"{g.nodes[n]['label']}  ({t})" for n, t, _ in top_hubs][::-1]
    hv = [d for _, _, d in top_hubs][::-1]
    bars = ax.barh(hl, hv, color=BLUE, height=0.6)
    for b, v in zip(bars, hv):
        ax.text(b.get_width() + 3, b.get_y() + b.get_height() / 2, str(v),
                va="center", fontsize=9, color=INK)
    style(ax)
    ax.set_title("Les nœuds les plus connectés (hors rapports)", loc="left",
                 fontsize=11, color=INK)
    ax.set_xlabel("Nombre de voisins distincts", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "fig_hubs.png")
    plt.close(fig)

    # ------------------------------------------------------------ rapport
    nc = node_counts(g)
    L = []
    L += ["# Étape 1 — Résultats", "",
          f"Périmètre : **{n_reports} rapports** FAA SDR 2025, chapitre ATA 29 (hydraulique).", "",
          "## Le graphe", "",
          "| Type de nœud | Nombre |", "| --- | ---: |"]
    L += [f"| {t} | {c} |" for t, c in nc.most_common()]
    L += ["", f"- {len(facts)} faits extraits (chacun avec sa provenance), "
              f"{n_triples_unique} triplets distincts une fois les doublons fusionnés.",
          f"- Rapports sans aucune pièce reconnue : {no_part} ({pct(no_part, n_reports)}).", ""]

    L += ["## Os n°1 — Entity resolution : le cas des pompes", "",
          f"- Le champ structuré `PartName` vaut « PUMP » dans **{len(pump_reports)} rapports**.",
          "- Ce champ ne dit pas de quelle pompe il s'agit. Le texte libre, lui, le dit souvent :", "",
          "![pompes](fig_pompes.png)", "",
          "| Question | Champ structuré seul | Structuré + texte |",
          "| --- | ---: | ---: |",
          f"| Rapports qui concernent une pompe moteur (EDP) | {edp_struct} | {edp_text} |",
          f"| Rapports qui concernent une pompe électrique | {emp_struct} | {emp_text} |", "",
          f"- **{outcome.get('AMBIGU', 0)} rapports citent plusieurs pompes.** "
          "Un dictionnaire trouve les mots, pas laquelle est en panne. "
          "C'est le travail de l'étape 2 (extraction par LLM).",
          "- **Faux positif trouvé en vérifiant à la main** : « ADD EMP:U349218 » est un "
          "numéro d'employé, pas une « Electric Motor Pump » (EMP). Les 5 occurrences de "
          "« EMP » dans le périmètre étaient toutes des employés. Règle corrigée. "
          "Leçon : un dictionnaire se valide sur des exemples réels, pas seulement à la conception.", ""]
    if conflicts:
        L += ["Exemples de rapports ambigus :", ""]
        texts = df.set_index("OperatorControlNumber")["Discrepancy"]
        for rid, sp in conflicts[:3]:
            L += [f"- `{rid}` ({', '.join(sp)}) : « {str(texts[rid])[:260]}… »"]
        L += [""]
    L += ["### Variantes d'écriture trouvées dans le texte (top 8 types)", "",
          "| Type canonique | Variantes distinctes | Exemples |", "| --- | ---: | --- |"]
    for key, cnt in sorted(surfaces.items(), key=lambda kv: -sum(kv[1].values()))[:8]:
        ex = ", ".join(f"`{s}` ({n})" for s, n in cnt.most_common(5))
        L += [f"| {labels[key]} | {len(cnt)} | {ex} |"]
    unm = Counter(mapper.unmapped_part_names)
    L += ["", f"### Valeurs de `PartName` non reconnues : {len(unm)} valeurs, "
              f"{sum(unm.values())} rapports", "",
          ", ".join(f"`{k}` ({v})" for k, v in unm.most_common(15)), "",
          "Chaque valeur non reconnue = une décision d'ontologie à prendre "
          "(l'ajouter, la regrouper, ou l'ignorer).", ""]

    L += ["## Os n°6 — Les hubs", "",
          "![hubs](fig_hubs.png)", "",
          "Un GraphRAG naïf part de l'entité de la question et récupère tout ce qui est "
          "à N sauts. Question test : *« Quels problèmes touchent les pompes moteur (EDP) ? »*", "",
          f"| Sauts | Nœuds récupérés (naïf) | % du graphe | En refusant de traverser les hubs (≥ {hub_threshold} voisins) |",
          "| ---: | ---: | ---: | ---: |"]
    for hops, a, b in rag:
        L += [f"| {hops} | {a} | {pct(a, total_nodes)} | {b} |"]
    L += ["", f"- Hubs bloqués : {', '.join(sorted(g.nodes[n]['label'] for n in hub_set))}.",
          "- À 3 sauts, la version naïve passe par les hubs (code JASC, état « LEAKING », "
          "constructeur…) et ramène une grande partie du graphe : le LLM est noyé.",
          "- Bloquer les hubs réduit peu le bruit (et peut couper des chemins utiles). "
          "Le seuil est une décision ([D6] dans DECISIONS.md).",
          f"- **Ce qui marche : interroger par le schéma.** Le chemin "
          "`pièce <- rapport -> état / tâche AMM` (une requête Cypher ou SPARQL) ramène "
          f"**{len(typed)} nœuds**, chacun relié à la question par une relation qui a un sens. "
          "États les plus fréquents pour les EDP : "
          + ", ".join(f"{k} ({v})" for k, v in typed_cond.most_common(4)) + ".",
          "- Limite honnête : l'état (`PartCondition`) est celui de la pièce du champ structuré. "
          "Si le rapport parle d'une EDP mais que le champ structuré vise un flexible, l'état "
          "n'est pas forcément celui de l'EDP. Encore un cas pour l'étape 2.",
          "- Conclusion : le graphe apporte de la valeur quand on le parcourt avec son "
          "ontologie, pas quand on l'aspire « à N sauts ».", ""]

    L += ["## Exports", "",
          "- `property_graph/nodes.csv`, `edges.csv` : la provenance (source, rapport, "
          "texte justificatif) est une **propriété de l'arête**.",
          f"- `graphe.ttl` (RDF) : {n_triples_unique} triplets distincts. En RDF, un triplet "
          "ne porte pas de propriétés : pour garder la provenance, chaque fait est "
          f"**réifié** ({len(facts)} nœuds `rdf:Statement`). Même information, "
          "modèle beaucoup plus verbeux. C'est une vraie différence entre les deux mondes.", ""]
    (OUT / "etape1_rapport.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
