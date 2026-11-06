"""Free exploration of the whole graph (maintenance + HR): search a node, see its neighbourhood, move on.

Positions are computed here (NetworkX); `render_html` returns a self-contained page that only draws them,
with no JavaScript library, so it works offline.
"""
from __future__ import annotations

import json

import networkx as nx

from kgcore.graph import build_graph

HUB = 50  # same threshold as the hub analysis

COLORS = {  # light, dark
    "PartType": ("#6a3fb5", "#a98bea"), "Report": ("#a9a5b8", "#6d6880"), "Condition": ("#2f6584", "#82b2cf"),
    "JascCode": ("#2f6584", "#82b2cf"), "Operator": ("#2f6584", "#82b2cf"), "AircraftModel": ("#1f8a70", "#5fd0b0"),
    "AmmTask": ("#9a5b00", "#e2a650"), "Aircraft": ("#5f5b6e", "#a6a2b6"), "Manufacturer": ("#2f6584", "#82b2cf"),
    "Employee": ("#c2185b", "#f48fb1"), "Skill": ("#9a5b00", "#e2a650"), "RawSkill": ("#a4362a", "#f08a7c"),
    "Occupation": ("#4f2c8f", "#c8b4f3"), "Project": ("#2f6584", "#82b2cf"), "Site": ("#1f8a70", "#5fd0b0"),
    "RawTitle": ("#a4362a", "#f08a7c"),
}


def full_graph(kb, hr=None) -> nx.MultiDiGraph:
    """Maintenance facts + HR facts. Sensitive facts (salary band, long absence) are left out of the explorer."""
    facts = list(kb.facts)
    if hr is not None:
        facts += [f for f in hr.facts if not f.attrs.get("sensitive")]
    return build_graph(facts)


def search(g, text: str, limit: int = 30) -> list[tuple[str, str]]:
    """(node id, display) for nodes whose label or id contains the text, best matches first."""
    t = text.strip().lower()
    if not t:
        return []
    und_deg = dict(nx.Graph(g).degree())
    hits = []
    for n, d in g.nodes(data=True):
        lab = str(d.get("label", n)).lower()
        if t in lab or t in n.lower():
            rank = 0 if lab == t else 1 if lab.startswith(t) else 2
            hits.append((rank, -und_deg[n], n))
    hits.sort()
    return [(n, f"{g.nodes[n].get('label', n)}  ·  {g.nodes[n]['type']}  ·  {-deg} links") for _, deg, n in hits[:limit]]


def neighbours(g, center: str, today: str = "") -> list[dict]:
    """One row per edge touching the node, with direction, provenance and validity."""
    rows = []
    for direction, edges in (("→", g.out_edges(center, data=True)), ("←", g.in_edges(center, data=True))):
        for u, v, d in edges:
            other = v if direction == "→" else u
            vt = d.get("valid_to", "")
            rows.append({"relation": d["relation"], "dir": direction, "node": g.nodes[other].get("label", other),
                         "type": g.nodes[other]["type"], "source": d.get("source", ""),
                         "valid until": (vt + (" (expired)" if today and vt and vt < today else "")) if vt else "",
                         "id": other})
    rows.sort(key=lambda r: (r["relation"], r["node"]))
    return rows


def ego_view(g, center: str, depth: int = 1, relations: set[str] | None = None, max_nodes: int = 150) -> dict:
    """Nodes within `depth` hops of `center`, following only `relations`, capped at `max_nodes`.

    When the cap is hit, the nodes kept are the closest, then the most connected.
    """
    sub = nx.Graph()
    sub.add_node(center)
    for u, v, d in g.edges(data=True):
        if relations is None or d["relation"] in relations:
            if sub.has_edge(u, v):
                sub[u][v]["rel"].add(d["relation"])
            else:
                sub.add_edge(u, v, rel={d["relation"]})
    dist = nx.single_source_shortest_path_length(sub, center, cutoff=depth)
    deg = dict(nx.Graph(g).degree())
    ranked = sorted(dist, key=lambda n: (dist[n], -deg.get(n, 0), n))
    keep = ranked[:max_nodes]
    view = sub.subgraph(keep)
    pos = nx.spring_layout(view, seed=3, iterations=100, k=1.4 / max(1, len(view)) ** 0.5)
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    index = {n: i for i, n in enumerate(keep)}
    nodes = [{"label": str(g.nodes[n].get("label", n)), "type": g.nodes[n]["type"], "hop": dist[n],
              "deg": deg.get(n, 0), "hub": deg.get(n, 0) >= HUB,
              "x": round((pos[n][0] - x0) / ((x1 - x0) or 1), 4), "y": round((pos[n][1] - y0) / ((y1 - y0) or 1), 4)}
             for n in keep]
    edges = [[index[u], index[v], "/".join(sorted(d["rel"]))] for u, v, d in view.edges(data=True)]
    by_hop = {h: sum(1 for x in dist.values() if x == h) for h in range(depth + 1)}
    return {"nodes": nodes, "edges": edges, "start": 0, "reached": len(dist), "shown": len(keep),
            "by_hop": by_hop, "total": g.number_of_nodes()}


def render_html(view: dict, height: int = 560) -> str:
    """Self-contained page drawing the view on a canvas: hover a node to see it and its relations."""
    data = json.dumps(view, ensure_ascii=False).replace("</", "<\\/")
    colors = json.dumps(COLORS)
    return f"""<!doctype html><meta charset="utf-8">
<style>
:root {{ --bg:#f5f5f8; --ink:#1d1b26; --muted:#5f5b6e; --line:#c4c0d2; --surface:#fff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#131219; --ink:#ecebf2; --muted:#a6a2b6; --line:#4a4659; --surface:#1c1a25; }} }}
html,body {{ margin:0; background:var(--bg); font-family: "Source Sans Pro", system-ui, sans-serif; }}
#w {{ position:relative; }} canvas {{ display:block; width:100%; }}
#tip {{ position:absolute; pointer-events:none; background:var(--surface); color:var(--ink); border:1px solid var(--line);
  border-radius:4px; padding:4px 8px; font-size:12px; max-width:280px; }}
#leg {{ display:flex; flex-wrap:wrap; gap:4px 14px; font-size:12px; color:var(--muted); padding:6px 4px; }}
#leg i {{ width:10px; height:10px; border-radius:50%; display:inline-block; margin-right:5px; vertical-align:-1px; }}
</style>
<div id="w"><canvas id="c"></canvas><div id="tip" hidden></div></div><div id="leg"></div>
<script>
const V = {data}, C = {colors}, H = {height};
const dark = matchMedia("(prefers-color-scheme: dark)").matches;
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const col = (t) => (C[t] || ["#888", "#999"])[dark ? 1 : 0];
const cv = document.getElementById("c"), tip = document.getElementById("tip");
let pts = [], hl = -1;
const adj = V.nodes.map(() => []);
V.edges.forEach(([a, b, r], k) => {{ adj[a].push(k); adj[b].push(k); }});
const rad = (n, i) => i === V.start ? 9 : n.hub ? 4 + Math.min(6, Math.sqrt(n.deg) / 2.5) : 3.5;
function draw() {{
  const W = cv.clientWidth, dpr = devicePixelRatio || 1; if (!W) return;
  cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + "px";
  const c = cv.getContext("2d"); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, W, H);
  const pad = 40, s = Math.min(W - 2 * pad, H - 2 * pad), ox = (W - s) / 2, oy = (H - s) / 2;
  pts = V.nodes.map((n) => [ox + n.x * s, oy + n.y * s]);
  const near = new Set(hl >= 0 ? adj[hl].flatMap((k) => V.edges[k].slice(0, 2)) : []);
  c.lineWidth = 0.7; c.strokeStyle = css("--line"); c.globalAlpha = hl >= 0 ? 0.15 : 0.5; c.beginPath();
  V.edges.forEach(([a, b]) => {{ c.moveTo(...pts[a]); c.lineTo(...pts[b]); }}); c.stroke(); c.globalAlpha = 1;
  c.font = "11px system-ui, sans-serif"; c.textAlign = "center"; c.textBaseline = "middle";
  if (hl >= 0) {{
    c.lineWidth = 1.6; c.strokeStyle = css("--muted"); c.beginPath();
    adj[hl].forEach((k) => {{ const [a, b] = V.edges[k]; c.moveTo(...pts[a]); c.lineTo(...pts[b]); }}); c.stroke();
    if (adj[hl].length <= 40) adj[hl].forEach((k) => {{
      const [a, b, r] = V.edges[k], x = (pts[a][0] + pts[b][0]) / 2, y = (pts[a][1] + pts[b][1]) / 2;
      c.lineWidth = 3; c.strokeStyle = css("--bg"); c.strokeText(r, x, y); c.fillStyle = css("--muted"); c.fillText(r, x, y);
    }});
  }}
  V.nodes.forEach((n, i) => {{
    c.globalAlpha = hl < 0 || i === hl || near.has(i) ? 1 : 0.3;
    c.beginPath(); c.arc(...pts[i], rad(n, i), 0, 2 * Math.PI); c.fillStyle = col(n.type); c.fill();
    if (i === V.start || n.hub) {{ c.lineWidth = 1.5; c.strokeStyle = css("--ink"); c.stroke(); }}
  }});
  c.globalAlpha = 1; c.font = "500 12px system-ui, sans-serif"; c.textAlign = "left";
  const taken = [], few = V.nodes.length <= 25;
  const order = V.nodes.map((_, i) => i).sort((a, b) => (b === V.start) - (a === V.start) || (b === hl) - (a === hl) || V.nodes[b].deg - V.nodes[a].deg);
  for (const i of order) {{
    const n = V.nodes[i];
    if (!(i === V.start || i === hl || n.hub || few || (hl >= 0 && near.has(i) && adj[hl].length <= 25))) continue;
    const t = n.label.length > 30 ? n.label.slice(0, 28) + "…" : n.label, w = c.measureText(t).width, r = rad(n, i);
    let x = pts[i][0] + r + 4; if (x + w > W - 4) x = pts[i][0] - r - 4 - w;
    const y = pts[i][1], box = [x - 2, y - 8, x + w + 2, y + 8];
    if (i !== hl && taken.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1])) continue;
    taken.push(box); c.lineWidth = 3; c.strokeStyle = css("--bg"); c.strokeText(t, x, y); c.fillStyle = css("--ink"); c.fillText(t, x, y);
  }}
}}
cv.addEventListener("pointermove", (e) => {{
  const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
  let best = -1, bd = 144;
  pts.forEach(([x, y], i) => {{ const d = (x - mx) ** 2 + (y - my) ** 2; if (d < bd) {{ bd = d; best = i; }} }});
  if (best !== hl) {{ hl = best; draw(); }}
  if (best < 0) {{ tip.hidden = true; return; }}
  const n = V.nodes[best];
  tip.innerHTML = `<b>${{n.label.replace(/</g, "&lt;")}}</b><br>${{n.type}} · ${{n.deg}} links${{n.hub ? " · hub" : ""}} · hop ${{n.hop}}`;
  tip.hidden = false; tip.style.left = Math.min(mx + 12, cv.clientWidth - 290) + "px"; tip.style.top = (my + 12) + "px";
}});
cv.addEventListener("pointerleave", () => {{ hl = -1; tip.hidden = true; draw(); }});
const types = [...new Set(V.nodes.map((n) => n.type))];
document.getElementById("leg").innerHTML = types.map((t) => `<span><i style="background:${{col(t)}}"></i>${{t}}</span>`).join("");
new ResizeObserver(draw).observe(cv);
</script>"""
