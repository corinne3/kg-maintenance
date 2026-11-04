"""Graphe en mémoire (NetworkX, modèle « property graph ») et analyses."""
from __future__ import annotations

from collections import Counter

import networkx as nx

from kgcore.facts import Fact


def build_graph(facts: list[Fact]) -> nx.MultiDiGraph:
    """Une arête par fait : on garde la provenance sur l'arête.

    MultiDiGraph = plusieurs arêtes possibles entre deux mêmes nœuds
    (ex. la pièce citée à la fois dans le champ structuré et dans le texte).
    """
    g = nx.MultiDiGraph()
    for f in facts:
        for n in (f.subject, f.object):
            if n.id not in g:
                g.add_node(n.id, type=n.type, key=n.key, label=n.label or n.key)
        g.add_edge(f.subject.id, f.object.id, key=f"{f.relation}|{f.source}",
                   relation=f.relation, source=f.source,
                   record_id=f.record_id, evidence=f.evidence)
    return g


def node_counts(g) -> Counter:
    return Counter(d["type"] for _, d in g.nodes(data=True))


def hubs(g, exclude_types=("Report",), top=12) -> list[tuple[str, str, int]]:
    """Nœuds les plus connectés (hors rapports) : les « hubs »."""
    und = nx.Graph(g)  # on compte les voisins distincts
    rows = [(n, g.nodes[n]["type"], und.degree(n))
            for n in und.nodes if g.nodes[n]["type"] not in exclude_types]
    return sorted(rows, key=lambda r: -r[2])[:top]


def typed_paths(g, start: str, path: list[tuple[str, str]]) -> set[str]:
    """Ce que fait une requête Cypher / SPARQL : suivre le schéma.

    path = suite de (relation, sens) ; sens 'in' = on remonte l'arête.
    Ex. [("INVOLVES_PART", "in"), ("HAS_CONDITION", "out")] :
        pièce <-INVOLVES_PART- rapport -HAS_CONDITION-> état
    """
    frontier, seen = {start}, {start}
    for rel, direction in path:
        nxt = set()
        for n in frontier:
            edges = g.in_edges(n, data=True) if direction == "in" else g.out_edges(n, data=True)
            for u, v, d in edges:
                if d["relation"] == rel:
                    nxt.add(u if direction == "in" else v)
        seen |= nxt
        frontier = nxt
    return seen


def neighborhood(g, start: str, hops: int, blocked: set[str] = frozenset()) -> set[str]:
    """Ce qu'un GraphRAG naïf récupère : tous les nœuds à N sauts.

    `blocked` = nœuds qu'on refuse de traverser (ex. les hubs).
    """
    und = nx.Graph(g)
    seen, frontier = {start}, {start}
    for _ in range(hops):
        nxt = set()
        for n in frontier:
            for nb in und.neighbors(n):
                if nb not in seen:
                    seen.add(nb)
                    if nb not in blocked:
                        nxt.add(nb)
        frontier = nxt
    return seen
