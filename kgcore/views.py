"""Small, drawable views of a graph: positions are computed here, the page only draws them."""
from __future__ import annotations

import math

import networkx as nx


def _norm(pos: dict) -> dict:
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sx, sy = (x1 - x0) or 1, (y1 - y0) or 1
    return {n: (round((p[0] - x0) / sx, 4), round((p[1] - y0) / sy, 4)) for n, p in pos.items()}


def layered_view(g, start: str, hops: int, hub_threshold: int = 50, seed: int = 7) -> dict:
    """Everything within `hops` of `start`, with the hop at which each node is reached.

    The layout is computed once on the largest view, so the smaller views are subsets of it.
    """
    und = nx.Graph(g)
    dist = nx.single_source_shortest_path_length(und, start, cutoff=hops)
    sub = und.subgraph(dist)
    pos = _norm(nx.spring_layout(sub, seed=seed, iterations=80, k=0.6 / max(1, len(sub)) ** 0.5))
    index = {n: i for i, n in enumerate(sub)}
    nodes = []
    for n in sub:
        d = g.nodes[n]
        deg = und.degree(n)
        nodes.append({"label": d.get("label", n), "type": d.get("type", ""), "hop": dist[n],
                      "deg": deg, "hub": deg >= hub_threshold and n != start,
                      "x": pos[n][0], "y": pos[n][1]})
    edges = [[index[u], index[v]] for u, v in sub.edges()]
    return {"nodes": nodes, "edges": edges, "start": index[start], "total": und.number_of_nodes()}


def radial_view(g, start: str, hops: int, hub_threshold: int = 50) -> dict:
    """Rings around `start`: ring k holds the nodes first reached at hop k.

    Each node is placed at the average angle of its neighbours on the previous ring, then the ring is spread
    evenly in that order, so branches stay together and the explosion at each hop is visible.
    """
    und = nx.Graph(g)
    dist = nx.single_source_shortest_path_length(und, start, cutoff=hops)
    ring = {k: [n for n, d in dist.items() if d == k] for k in range(1, hops + 1)}
    angle = {start: 0.0}
    for k in range(1, hops + 1):
        def target(n):
            if k == 1:
                d = g.nodes[n]
                return (d.get("type", ""), d.get("label", n))
            prev = [angle[m] for m in und[n] if dist.get(m) == k - 1]
            a = math.atan2(sum(map(math.sin, prev)), sum(map(math.cos, prev))) % (2 * math.pi)
            return (a, n)
        nodes = sorted(ring[k], key=target)
        for i, n in enumerate(nodes):
            angle[n] = 2 * math.pi * i / max(1, len(nodes))
    nodes, index = [], {}
    for n, d in sorted(dist.items(), key=lambda x: x[1]):
        index[n] = len(nodes)
        r = 0.5 * d / hops
        deg = und.degree(n)
        a = g.nodes[n]
        nodes.append({"label": a.get("label", n), "type": a.get("type", ""), "hop": d, "deg": deg,
                      "hub": deg >= hub_threshold and n != start,
                      "x": round(0.5 + r * math.cos(angle[n]), 4), "y": round(0.5 + r * math.sin(angle[n]), 4)})
    edges = [[index[u], index[v]] for u, v in und.subgraph(dist).edges()]
    return {"nodes": nodes, "edges": edges, "start": index[start], "total": und.number_of_nodes()}


def fixed_view(nodes: list[dict], edges: list[tuple[str, str]]) -> dict:
    """Nodes already carry x, y (0..1) and an 'id'; edges reference ids."""
    index = {n["id"]: i for i, n in enumerate(nodes)}
    return {"nodes": [{k: v for k, v in n.items() if k != "id"} for n in nodes],
            "edges": [[index[a], index[b]] for a, b in edges if a in index and b in index]}
