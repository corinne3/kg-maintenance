"""Builds the explorer page: outputs/explorer.html

    python build_explorer.py

Rebuilds the graph (like run_step1.py) and injects the data into
web/explorer_template.html. If LLM results exist (outputs/llm_*.jsonl),
they are added as a third source with their evaluation.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from domains.maintenance_aviation.mapping import MaintenanceMapper  # noqa: E402
from kgcore.graph import build_graph, hubs, neighborhood, typed_paths  # noqa: E402
from kgcore.loader import load_domain, load_records  # noqa: E402
from kgcore.resolver import resolve_by_patterns  # noqa: E402
from kgcore.views import fixed_view, radial_view  # noqa: E402

PUMPS = ["ENGINE_DRIVEN_PUMP", "ELECTRIC_MOTOR_PUMP", "POWER_TRANSFER_UNIT", "RAM_AIR_TURBINE"]


def s(v):
    return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()


def graph_views(mcfg, mfacts, g) -> dict:
    """Bridge view (maintenance + HR) and the HR false-shortcut path."""
    import yaml
    from domains.hr.esco import load
    from domains.hr.mapping import HRMapper, load_tables
    hcfg = yaml.safe_load(open(ROOT / "domains" / "hr" / "config.yaml", encoding="utf-8"))
    esco = load(hcfg)
    t = load_tables()
    hfacts = [f for f in HRMapper(hcfg, esco).facts(t) if not f.attrs.get("sensitive")]
    today = hcfg["certifications"]["today"]
    merged = build_graph(mfacts + hfacts)
    part = "PartType:ENGINE_DRIVEN_PUMP"
    fams = ["AircraftModel:A319", "AircraftModel:A320", "AircraftModel:A321"]

    def out(n, rel):
        return [v for _, v, d in merged.out_edges(n, data=True) if d["relation"] == rel]

    reports, edges = [], []
    for u, _, d in merged.in_edges(part, data=True):
        if d["relation"] == "INVOLVES_PART" and u.startswith("Report:"):
            models = [m for a in out(u, "CONCERNS") for m in out(a, "IS_MODEL") if m in fams]
            if models:
                reports.append(u)
                edges += [(u, part)] + [(u, m) for m in set(models)]
    reports = sorted(set(reports))
    techs = {}
    for u, _, d in merged.in_edges(part, data=True):
        if d["relation"] != "CERTIFIED_FOR":
            continue
        rated = [(m, d2.get("valid_to", "")) for _, m, d2 in merged.out_edges(u, data=True)
                 if d2["relation"] == "TYPE_RATED" and m in fams]
        if rated:
            valid = d.get("valid_to", "") >= today and all(v >= today for _, v in rated)
            techs[u] = valid
            edges += [(u, part)] + [(u, m) for m, _ in rated]
    nodes = [{"id": part, "label": "Engine-driven pump (EDP)", "type": "PartType", "x": 0.5, "y": 0.06, "hub": True}]
    for i, m in enumerate(fams):
        nodes.append({"id": m, "label": m.split(":")[1], "type": "AircraftModel", "x": 0.5, "y": 0.45 + 0.22 * i, "hub": True})

    def grid(items, x0, x1, kind, extra):
        cols = 5
        rows = (len(items) + cols - 1) // cols
        for i, n in enumerate(items):
            r, c = divmod(i, cols)
            nodes.append({"id": n, "label": merged.nodes[n].get("label", n), "type": kind,
                          "x": round(x0 + (x1 - x0) * c / (cols - 1), 4),
                          "y": round(0.22 + 0.76 * r / max(1, rows - 1), 4), **extra(n)})
    grid(reports, 0.02, 0.32, "Report", lambda n: {})
    tech_sorted = sorted(techs, key=lambda n: (not techs[n], n))
    grid(tech_sorted, 0.68, 0.98, "Employee", lambda n: {"expired": not techs[n]})
    bridge = fixed_view(nodes, edges)
    bridge.update({"reports": len(reports), "valid": sum(techs.values()), "expired": sum(1 for v in techs.values() if not v)})

    # HR false shortcut: "worked on a project with someone who worked on a project with an X"
    hg = build_graph(hfacts)
    occ = {f.subject.id: f.object for f in hfacts if f.relation == "HOLDS_OCCUPATION"}
    proj = nx.Graph([(f.subject.id, f.object.id) for f in hfacts if f.relation == "MEMBER_OF"])
    ops = next(e for e, o in sorted(occ.items()) if o.label == "operations manager")
    path = None
    for d_emp in sorted(e for e, o in occ.items() if o.label == "software developer"):
        for f_emp in sorted(e for e, o in occ.items() if o.label == "financial controller"):
            try:
                p1, p2 = nx.shortest_path(proj, d_emp, ops), nx.shortest_path(proj, ops, f_emp)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            if len(p1) == 3 and len(p2) == 3:
                path = p1 + p2[1:] + [occ[f_emp].id]
                break
        if path:
            break
    und = nx.Graph(hg)
    def named(v):
        lab = hg.nodes[v].get("label", "")
        return lab and not re.fullmatch(r"[0-9a-f]{6,}", lab)

    skills = lambda e: sorted(v for _, v, d in hg.out_edges(e, data=True) if d["relation"] == "HAS_SKILL" and named(v))  # noqa: E731
    req = sorted(v for _, v, d in hg.out_edges(path[-1], data=True) if d["relation"] == "REQUIRES" and named(v))
    n = len(path)
    def plabel(x):
        lab = hg.nodes[x].get("label", x)
        return f"{lab} ({occ[x].label})" if x in occ else lab

    pnodes = [{"id": x, "label": plabel(x), "type": hg.nodes[x]["type"],
               "x": round(0.04 + 0.92 * i / (n - 1), 4), "y": 0.5, "hub": x == ops, "onpath": True}
              for i, x in enumerate(path)]
    pedges = list(zip(path, path[1:]))
    for j, s_ in enumerate(skills(path[0])[:4]):
        pnodes.append({"id": "a" + s_, "label": hg.nodes[s_]["label"], "type": "Skill",
                       "x": 0.04, "y": round(0.08 + 0.1 * j, 4)})
        pedges.append((path[0], "a" + s_))
    for j, s_ in enumerate(req[:4]):
        pnodes.append({"id": "b" + s_, "label": hg.nodes[s_]["label"], "type": "Skill",
                       "x": 0.96, "y": round(0.92 - 0.1 * j, 4)})
        pedges.append((path[-1], "b" + s_))
    shared = len(set(skills(path[0])) & set(req))
    shortcut = fixed_view(pnodes, pedges)
    shortcut.update({"shared": shared, "hub_links": und.degree(ops)})
    return {"bridge": bridge, "shortcut": shortcut}


def main():
    cfg = load_domain("maintenance_aviation")
    df = load_records(cfg)
    mapper = MaintenanceMapper(cfg)
    viewer = MaintenanceMapper(cfg)  # second instance, so mapper's counters are not doubled
    labels = {k: v.get("label_en", v["label"]) for k, v in cfg["part_types"].items()}

    facts, reports = [], {}
    for _, row in df.iterrows():
        fs = mapper.facts(row)
        facts.extend(fs)
        rid = row["OperatorControlNumber"]
        text = s(row["Discrepancy"])
        mentions = [{"t": m.canonical, "s": m.start, "e": m.end}
                    for m in viewer.parts.find(text)]
        structured = viewer.part_from_structured(s(row["PartName"]))
        reports[rid] = {
            "date": s(row["DifficultyDate"]),
            "make": cfg["manufacturers"].get(s(row["AircraftMake"]).upper(), s(row["AircraftMake"])),
            "fam": resolve_by_patterns(s(row["AircraftModel"]), cfg["model_families"]) or s(row["AircraftModel"]),
            "op": s(row["OperatorDesignator"]),
            "jasc": s(row["JASCCode"]),
            "pn": s(row["PartName"]),
            "sp": structured,
            "cond": s(row["PartCondition"]).upper(),
            "amm": sorted(set(mapper.amm.findall(text.upper()))),
            "text": text.upper(),
            "m": mentions,
        }

    # LLM (optional)
    llm_model, llm = None, {}
    files = sorted((ROOT / "outputs").glob("llm_*.jsonl"))
    files = [f for f in files if "mock" not in f.name]
    if files:
        llm_model = files[-1].stem.replace("llm_", "")
        for line in files[-1].read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            try:
                out = json.loads(r["raw"])
                llm[r["id"]] = {"faulty": out.get("faulty_parts", []),
                                "mentioned": out.get("mentioned_parts", []),
                                "action": out.get("action", ""), "sec": r["seconds"]}
            except Exception:  # noqa: BLE001
                llm[r["id"]] = {"invalid": True, "raw": r["raw"][:300]}
        for rid, v in llm.items():
            if rid in reports:
                reports[rid]["llm"] = v

    llm_eval = None
    if files:
        from run_step2_llm import summarize
        recs = [json.loads(x) for x in files[-1].read_text(encoding="utf-8").splitlines()]
        llm_eval = summarize(df, MaintenanceMapper(cfg), recs)

    agent_eval = None
    agent_files = [f for f in sorted((ROOT / "outputs").glob("agent_eval_*.json")) if "mock" not in f.name]
    if agent_files:
        agent_eval = json.loads(agent_files[-1].read_text(encoding="utf-8"))

    hr = None
    if (ROOT / "data" / "esco" / "en").exists() and (ROOT / "data" / "hr_synthetic").exists():
        from run_hr import main as run_hr
        hr = run_hr(quiet=True)

    # Part types
    parts = []
    for key in cfg["part_types"]:
        struct_ids = [rid for rid, r in reports.items() if r["sp"] == key]
        text_ids = [rid for rid, r in reports.items() if any(m["t"] == key for m in r["m"])]
        variants = Counter()
        for rid in text_ids:
            r = reports[rid]
            for m in r["m"]:
                if m["t"] == key:
                    variants[r["text"][m["s"]:m["e"]].strip()] += 1
        ids = sorted(set(struct_ids) | set(text_ids))
        if ids:
            parts.append({"key": key, "label": labels[key], "nStruct": len(struct_ids),
                          "nText": len(text_ids), "nAll": len(ids),
                          "variants": variants.most_common(), "ids": ids})
    parts.sort(key=lambda p: -p["nAll"])

    # The pumps
    outcome, ambiguous = Counter(), []
    for rid, r in reports.items():
        if r["sp"] != "HYDRAULIC_PUMP_UNSPECIFIED":
            continue
        found = {m["t"] for m in r["m"]}
        spec = [p for p in PUMPS if p in found]
        if len(spec) == 1:
            outcome[spec[0]] += 1
        elif len(spec) > 1:
            outcome["AMBIGU"] += 1
            ambiguous.append(rid)
        elif "HYDRAULIC_PUMP_UNSPECIFIED" in found:
            outcome["IMPRECIS"] += 1
        else:
            outcome["AUCUNE"] += 1

    # Graph, hubs, traversals
    g = build_graph(facts)
    und = nx.Graph(g)
    total = g.number_of_nodes()
    edp = "PartType:ENGINE_DRIVEN_PUMP"
    hub_set = {n for n, d in und.degree() if d >= 50 and g.nodes[n]["type"] != "Report" and n != edp}
    hops = []
    for h in (1, 2, 3, 4):
        hops.append({"h": h, "naive": len(neighborhood(g, edp, h)),
                     "guarded": len(neighborhood(g, edp, h, blocked=hub_set))})
    typed = (typed_paths(g, edp, [("INVOLVES_PART", "in"), ("HAS_CONDITION", "out")])
             | typed_paths(g, edp, [("INVOLVES_PART", "in"), ("REFERENCES", "out")]))
    nl = lambda n: labels.get(g.nodes[n]["key"], g.nodes[n]["label"]) if g.nodes[n]["type"] == "PartType" else g.nodes[n]["label"]
    top = [{"label": nl(n), "type": t, "deg": d} for n, t, d in hubs(g, top=10)]

    distinct = len({(f.subject.id, f.relation, f.object.id) for f in facts})
    rdf_total = distinct + 2 * total + 7 * len(facts)

    unm = Counter(mapper.unmapped_part_names)
    edp_variants_raw = next(p for p in parts if p["key"] == "ENGINE_DRIVEN_PUMP")["variants"]

    views = {"hub": radial_view(g, edp, max(h["h"] for h in hops))}
    if hr is not None:
        views.update(graph_views(cfg, facts, g))

    data = {
        "nReports": len(reports), "nNodes": total, "nFacts": len(facts),
        "nDistinct": distinct, "rdfTotal": rdf_total,
        "nodeTypes": Counter(d["type"] for _, d in g.nodes(data=True)).most_common(),
        "parts": parts, "reports": reports, "labels": labels,
        "pumpOutcome": dict(outcome), "pumpTotal": sum(outcome.values()),
        "ambiguous": ambiguous, "hops": hops, "typed": len(typed),
        "hubs": top, "hubBlocked": sorted(nl(n) for n in hub_set),
        "unmapped": {"n": len(unm), "reports": sum(unm.values()), "top": unm.most_common(12)},
        "edpVariantsRaw": len(edp_variants_raw),
        "llmModel": llm_model, "nLlm": len(llm),
        "llmEval": llm_eval,
        "hr": hr,
        "agent": agent_eval,
        "views": views,
    }
    tpl = (ROOT / "web" / "explorer_template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = tpl.replace("/*__DATA__*/null", payload)
    out = ROOT / "outputs" / "explorer.html"
    out.write_text(html, encoding="utf-8")
    print(f"Page written: {out} ({len(html) // 1024} KB)")
    site = ROOT / "docs" / "index.html"   # published by GitHub Pages (Settings > Pages > main, /docs)
    site.write_text(html, encoding="utf-8")
    (ROOT / "docs" / ".nojekyll").touch()
    print(f"Site copy:    {site}")


if __name__ == "__main__":
    main()
