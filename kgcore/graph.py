"""In-memory graph (NetworkX, property graph model) and analyses."""
from __future__ import annotations

from collections import Counter

import networkx as nx

from kgcore.facts import Fact


def build_graph(facts: list[Fact]) -> nx.MultiDiGraph:
    """One edge per fact: provenance is kept on the edge.

    MultiDiGraph = several edges allowed between the same two nodes
    (e.g. a part cited both in the structured field and in the text).
    """
    g = nx.MultiDiGraph()
    for f in facts:
        for n in (f.subject, f.object):
            if n.id not in g:
                g.add_node(n.id, type=n.type, key=n.key, label=n.label or n.key)
        g.add_edge(f.subject.id, f.object.id, key=f"{f.relation}|{f.source}|{f.attrs.get('valid_from', '')}",
                   relation=f.relation, source=f.source,
                   record_id=f.record_id, evidence=f.evidence, **f.attrs)
    return g


def node_counts(g) -> Counter:
    return Counter(d["type"] for _, d in g.nodes(data=True))


def hubs(g, exclude_types=("Report",), top=12) -> list[tuple[str, str, int]]:
    """Most connected nodes (excluding reports): the hubs."""
    und = nx.Graph(g)  # count distinct neighbours
    rows = [(n, g.nodes[n]["type"], und.degree(n))
            for n in und.nodes if g.nodes[n]["type"] not in exclude_types]
    return sorted(rows, key=lambda r: -r[2])[:top]


def typed_paths(g, start: str, path: list[tuple[str, str]]) -> set[str]:
    """What a Cypher / SPARQL query does: follow the schema.

    path = sequence of (relation, direction); 'in' = walk the edge backwards.
    E.g. [("INVOLVES_PART", "in"), ("HAS_CONDITION", "out")]:
        part <-INVOLVES_PART- report -HAS_CONDITION-> condition
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
    """What a naive GraphRAG retrieves: every node within N hops.

    `blocked` = nodes we refuse to traverse (e.g. hubs).
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
