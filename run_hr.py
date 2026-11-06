"""HR domain — measure the knowledge graph pitfalls the maintenance case cannot show.

    python -m domains.hr.generate     # once: synthetic company (needs ESCO in data/esco/)
    python run_hr.py

Writes outputs/hr_report.md, outputs/fig_hr_linking.png, outputs/fig_hr_mobility.png.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from domains.hr.esco import load  # noqa: E402
from domains.hr.mapping import HRMapper, load_tables  # noqa: E402
from domains.maintenance_aviation.mapping import MaintenanceMapper  # noqa: E402
from kgcore.graph import build_graph  # noqa: E402
from kgcore.loader import load_domain, load_records  # noqa: E402

OUT = ROOT / "outputs"
INK, MUTED, BLUE, GREY = "#1f2328", "#6e7781", "#2f6fb3", "#c9ced6"


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "-"


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GREY)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.xaxis.grid(True, color="#eef0f3", linewidth=0.8)
    ax.set_axisbelow(True)


def main(quiet: bool = False) -> dict:
    cfg = yaml.safe_load(open(ROOT / "domains" / "hr" / "config.yaml", encoding="utf-8"))
    esco = load(cfg)
    t = load_tables()
    emp = t["employees"]
    today = cfg["certifications"]["today"]
    L = ["# HR domain — Results", "",
         f"Scope: a **synthetic** aerospace company of {len(emp)} employees (Toulouse in French, "
         "Bristol in English), linked to the real **ESCO v1.2.1** taxonomy (European Commission). "
         "No real person. Same `kgcore/` as the maintenance case.", ""]

    # ------------------------------------------------------------ 1. reference data is ambiguous too
    amb_occ = esco.full_occ_index.ambiguous_labels()
    amb_sk = esco.skill_index.ambiguous_labels()
    n_occ_labels, n_sk_labels = len(esco.full_occ_index.by_label), len(esco.skill_index.by_label)
    L += ["## 1. The reference taxonomy is ambiguous too", "",
          f"- ESCO occupation labels (English + French, preferred + alternative): **{n_occ_labels:,}**, "
          f"of which **{len(amb_occ):,} ({pct(len(amb_occ), n_occ_labels)})** point to more than one occupation.",
          f"- ESCO skill labels: **{n_sk_labels:,}**, of which **{len(amb_sk):,}** point to more than one skill.",
          "- Examples: \"responsable des ressources humaines\" is the French preferred label of *human resources "
          "officer* and an alternative label of *human resources manager*. \"Technicien **en** maintenance "
          "aéronautique\" and \"technicien **de** maintenance aéronautique\" are two different ESCO occupations.",
          "- French gendered labels (\"ingénieur/ingénieure de données\") must be split and rebuilt before "
          "matching: a person types one form, the taxonomy stores both in one string.", ""]

    # ------------------------------------------------------------ 2. linking titles and skills
    mapper = HRMapper(cfg, esco)
    facts = mapper.facts(t)
    tl = pd.DataFrame(mapper.title_links)
    sl = pd.DataFrame(mapper.skill_links)
    tl_counts = tl.status.value_counts()
    tl_ok = tl[tl.status == "resolved"].apply(lambda r: r["true"] in r["ids"], axis=1).mean()
    amb_titles = sorted(tl[tl.status == "ambiguous"].title.unique())
    unres_titles = sorted(tl[tl.status == "unresolved"].title.unique())
    sk_e = sl[sl.kind == "esco"].status.value_counts()
    sk_v = sl[sl.kind == "vague"].status.value_counts()
    vague_resolved = sl[(sl.kind == "vague") & (sl.status == "resolved")].text.value_counts()
    L += ["## 2. Linking job titles and skills to the taxonomy", "",
          "| Item | Linked to one concept | Ambiguous | Not found |", "| --- | ---: | ---: | ---: |",
          f"| Job titles ({len(tl)}) | {tl_counts.get('resolved', 0)} | {tl_counts.get('ambiguous', 0)} | {tl_counts.get('unresolved', 0)} |",
          f"| Skills written from ESCO labels ({int(sk_e.sum())}) | {sk_e.get('resolved', 0)} | {sk_e.get('ambiguous', 0)} | {sk_e.get('unresolved', 0)} |",
          f"| Vague skills (\"teamwork\", \"IT\"…) ({int(sk_v.sum())}) | {sk_v.get('resolved', 0)} | {sk_v.get('ambiguous', 0)} | {sk_v.get('unresolved', 0)} |",
          "",
          f"- Linked titles are right {tl_ok:.0%} of the time, but **{tl_counts.get('ambiguous', 0)} titles are ambiguous** "
          f"even when copied from ESCO: {', '.join(f'`{x}`' for x in amb_titles)}.",
          f"- Company-specific titles are never found: {', '.join(f'`{x}`' for x in unres_titles)}. "
          "They need a company mapping table, owned by HR.",
          "- Vague skills that *do* match an ESCO label: "
          + ", ".join(f"`{k}` ({v})" for k, v in vague_resolved.head(4).items())
          + ". They link, but to very generic concepts: the match is right and useless.", ""]

    fig, ax = plt.subplots(figsize=(8, 3.0), dpi=150)
    rows = [("Job titles", tl_counts), ("Skills from ESCO labels", sk_e), ("Vague skills", sk_v)]
    left = [0] * 3
    for status, color in (("resolved", BLUE), ("ambiguous", "#9aa8bf"), ("unresolved", GREY)):
        vals = [100 * c.get(status, 0) / c.sum() for _, c in rows]
        ax.barh([r[0] for r in rows][::-1], vals[::-1], left=left[::-1], color=color, height=0.55,
                label={"resolved": "linked to one concept", "ambiguous": "ambiguous",
                       "unresolved": "not found"}[status], edgecolor="white", linewidth=1.5)
        left = [a + b for a, b in zip(left, vals)]
    style(ax)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of items", color=MUTED, fontsize=9)
    ax.set_title("Linking HR data to ESCO", loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=8, loc="lower right", bbox_to_anchor=(1.0, 1.02), ncol=3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_hr_linking.png")
    plt.close(fig)

    # ------------------------------------------------------------ 3. garbage nodes and islands
    site = dict(zip(emp.employee, emp.site))
    vague_words = {v.lower() for lang in cfg["vague_skills"].values() for v in lang}

    def islands(fs):
        by_skill = defaultdict(set)
        for f in fs:
            if f.relation in ("HAS_SKILL", "DECLARES"):
                by_skill[(f.object.id, f.evidence.lower() in vague_words)].add(f.subject.key)
        cross_vague = sorted({fid for (fid, vg), ps in by_skill.items() if vg and len({site[p] for p in ps}) > 1})
        cross_real = sum(1 for (fid, vg), ps in by_skill.items() if not vg and len({site[p] for p in ps}) > 1)
        g = nx.Graph()
        g.add_nodes_from(emp.employee)
        for (fid, vg), ps in by_skill.items():
            if vg:
                continue
            ps = sorted(ps)
            g.add_edges_from((ps[0], q) for q in ps[1:])
        comps = list(nx.connected_components(g))
        mixed = sum(1 for c in comps if len({site[p] for p in c}) > 1)
        return cross_vague, cross_real, comps, mixed

    raw_mapper = HRMapper(cfg, esco)
    raw_facts = raw_mapper.facts(t, use_esco=False)
    raw_deg = Counter(f.object.label for f in raw_facts if f.relation == "DECLARES")
    rv, rr, rc, rm = islands(raw_facts)
    ev, er, ec, em = islands(facts)
    L += ["## 3. Garbage nodes and isolated islands", "",
          "Skills built naively from the raw text (one node per string typed), then linked to ESCO:", "",
          "| | Raw text only | With ESCO linking |", "| --- | ---: | ---: |",
          f"| Skill nodes shared by Toulouse and Bristol: meaningful skills | {rr} | {er} |",
          f"| Skill nodes shared by Toulouse and Bristol: vague skills | {len(rv)} | {len(ev)} |",
          f"| Islands of employees, ignoring vague skills | {len(rc)} | {len(ec)} |",
          f"| Islands that mix both sites | {rm} | {em} |",
          "",
          "- In the raw graph, the only things connecting the French and English sites are vague words that "
          "happen to be spelled the same in both languages (\"Excel\", \"communication\"). The graph *looks* "
          "connected; it is held together by garbage nodes.",
          f"- Remove them and the raw graph falls apart into {len(rc)} islands, none spanning both sites. "
          "Linking to ESCO, which carries French and English labels for the same concept, reconnects the sites "
          f"through {er} real skills.",
          "- Most connected raw skill nodes: "
          + ", ".join(f"`{k}` ({v} employees)" for k, v in raw_deg.most_common(3)) + ".", ""]

    # ------------------------------------------------------------ 4. human hub and transitivity
    g = build_graph([f for f in facts if not f.attrs.get("sensitive")])
    und = nx.Graph(g)
    ops = emp[emp.true_occupation.map(esco.all_occ_labels) == "operations manager"].employee.iloc[0]
    deg_emp = sorted(((n, und.degree(n)) for n in und if n.startswith("Employee:")), key=lambda x: -x[1])
    occ_of = {f.subject.key: f.object.id for f in facts if f.relation == "HOLDS_OCCUPATION"}
    skills = defaultdict(set)
    req = defaultdict(set)
    for f in facts:
        if f.relation == "HAS_SKILL":
            skills[f.subject.key].add(f.object.id)
        if f.relation == "REQUIRES":
            req[f.subject.id].add(f.object.id)
    proj = defaultdict(set)
    for r in t["project_members"].itertuples():
        proj[r.project].add(r.employee)

    def overlap(a, o):
        return len(skills[a] & req[o]) / len(req[o])

    people = [a for a in occ_of if a != ops]
    together = {(a, b) for ms in proj.values() for a in ms for b in ms if a != b}
    colleague = {(a, occ_of[b]) for a, b in together
                 if a in occ_of and b in occ_of and ops not in (a, b) and occ_of[a] != occ_of[b]}
    hub_projects = [p for p, ms in proj.items() if ops in ms]
    via_hub = {(a, occ_of[b]) for p in hub_projects for q in hub_projects if p != q
               for a in proj[p] for b in proj[q]
               if ops not in (a, b) and a in occ_of and b in occ_of and occ_of[a] != occ_of[b]
               and (a, b) not in together}
    typed = {}
    for a in people:
        o, v = max(((o, overlap(a, o)) for o in req if o != occ_of[a]), key=lambda z: z[1])
        typed[a] = (o, v)
    abstain = sum(1 for o, v in typed.values() if v == 0)
    rows = [
        ("Colleague of a colleague: \"worked on a project with an X, so could become an X\"", colleague),
        ("Same, through the human hub only (both on projects with the operations manager)", via_hub),
    ]
    L += ["## 4. Human hubs and transitivity bias", "",
          f"- The operations manager sits on {cfg['hub_projects']} of {cfg['projects']} projects and manages every "
          f"team lead: **{deg_emp[0][1]} direct links**, the most connected person in the graph.",
          "- Task: suggest internal moves. A suggestion is *absurd* if the person has **none** of the skills "
          "the target job requires (ESCO essential skills).", "",
          "| Inference | Suggestions (person, job) | Absurd |", "| --- | ---: | ---: |"]
    absurd_share = {}
    for name, pairs in rows:
        z = sum(1 for a, o in pairs if overlap(a, o) == 0)
        absurd_share[name] = 100 * z / len(pairs)
        L.append(f"| {name} | {len(pairs):,} | {z:,} ({pct(z, len(pairs))}) |")
    L.append(f"| Schema-guided: best match between the person's skills and each job's required skills | "
             f"{len(people) - abstain} | 0 (no suggestion for {abstain} people with no matching skill) |")
    L += ["",
          "- Following links between people transfers *who you know* into *what you can do*. The longer the chain "
          "and the more it goes through a hub, the worse it gets.",
          "- The schema-guided path (person → skill ← required by → job) only suggests what the skills support, "
          "and it can say \"no suggestion\". Matches stay partial "
          f"(on average {sum(v for _, v in typed.values()) / len(typed):.0%} of the required skills), "
          "because each synthetic employee declares only "
          f"{cfg['skills_per_employee']} skills: incomplete profiles are a pitfall of their own.", ""]

    fig, ax = plt.subplots(figsize=(8, 2.6), dpi=150)
    names = ["Colleague of a colleague", "Through the human hub", "Schema-guided"]
    vals = list(absurd_share.values()) + [0]
    bars = ax.barh(names[::-1], vals[::-1], color=[GREY, GREY, BLUE][::-1], height=0.55)
    for b, v in zip(bars, vals[::-1]):
        ax.text(b.get_width() + 1, b.get_y() + b.get_height() / 2, f"{v:.0f}%", va="center", fontsize=9, color=INK)
    style(ax)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of internal-move suggestions with zero matching skills", color=MUTED, fontsize=9)
    ax.set_title("Transitivity bias in internal mobility", loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_hr_mobility.png")
    plt.close(fig)

    # ------------------------------------------------------------ 5. access control and inference
    roles = cfg["roles"]
    edges_by_role = {r: sum(1 for f in facts if f.relation in rels) for r, rels in roles.items()}
    rep = t["reporting"]
    current = rep[rep.valid_to == ""]
    team_size = current.groupby("manager").employee.nunique()
    k = cfg["k_anonymity"]
    small_teams = team_size[team_size < k]
    exposed = int(small_teams.sum())
    absent = emp[emp.long_absence == "True"]
    absent_small = absent[absent.employee.isin(current[current.manager.isin(small_teams.index)].employee)]
    L += ["## 5. Access control and inference (sensitive data)", "",
          "Salary band and long absence are marked `sensitive` on the edge. Edges visible per role:", "",
          "| Role | Visible edges |", "| --- | ---: |"]
    L += [f"| {r} | {n:,} |" for r, n in edges_by_role.items()]
    L += ["",
          f"- Hiding sensitive edges is not enough. An \"anonymous\" aggregate such as *average salary band per "
          f"team* reveals individuals when a team is small: **{len(small_teams)} of {len(team_size)} teams** have "
          f"fewer than {k} people, covering **{exposed} employees**.",
          f"- The same goes for *number of long absences per team*: {len(absent_small)} of the {len(absent)} "
          "employees on long absence sit in a team small enough to be identified.",
          f"- Rule applied: no aggregate on fewer than {k} people (k-anonymity), enforced in the query layer, "
          "not left to each user.", ""]

    # ------------------------------------------------------------ 6. time
    naive_mgr = rep.groupby("employee").manager.nunique()
    two = int((naive_mgr > 1).sum())
    asof = rep[(rep.valid_from <= today) & ((rep.valid_to == "") | (rep.valid_to >= today))]
    asof_two = int((asof.groupby("employee").manager.nunique() > 1).sum())
    certs = t["certifications"]
    expired = certs[certs.valid_to < today].employee.nunique()
    L += ["## 6. Change over time", "",
          f"- A reorganisation on {cfg['reorg']['date']} moved part of a team to a new manager. Without dates on "
          f"the `REPORTS_TO` edge, **{two} employees have two managers**. With validity dates and an "
          f"\"as of {today}\" filter: {asof_two}.",
          f"- Certifications expire: **{expired} certified people** hold at least one expired certification. "
          "A graph that does not store validity would still call them qualified.", ""]

    # ------------------------------------------------------------ 7. bridge with maintenance
    mcfg = load_domain("maintenance_aviation")
    mdf = load_records(mcfg)
    mm = MaintenanceMapper(mcfg)
    mfacts = [f for _, r in mdf.iterrows() for f in mm.facts(r)]
    merged = build_graph(mfacts + [f for f in facts if not f.attrs.get("sensitive")])
    part = "PartType:ENGINE_DRIVEN_PUMP"
    fam = {"AircraftModel:A319", "AircraftModel:A320", "AircraftModel:A321", "AircraftModel:A318"}
    reports = set()
    for u, _, d in merged.in_edges(part, data=True):
        if d["relation"] == "INVOLVES_PART" and u.startswith("Report:"):
            for _, a, d2 in merged.out_edges(u, data=True):
                if d2["relation"] == "CONCERNS":
                    if any(m in fam for _, m, d3 in merged.out_edges(a, data=True) if d3["relation"] == "IS_MODEL"):
                        reports.add(u)

    def qualified(valid_only: bool):
        people = set()
        for u, _, d in merged.in_edges(part, data=True):
            if d["relation"] != "CERTIFIED_FOR" or (valid_only and d.get("valid_to", "") < today):
                continue
            rated = [m for _, m, d2 in merged.out_edges(u, data=True)
                     if d2["relation"] == "TYPE_RATED" and m in fam and (not valid_only or d2.get("valid_to", "") >= today)]
            if rated:
                people.add(u)
        return people
    q_all, q_valid = qualified(False), qualified(True)
    sites = Counter(emp.set_index("employee").loc[p.split(":")[1], "site"] for p in q_valid)
    L += ["## 7. One graph, two domains", "",
          "HR certifications and FAA maintenance reports share the same `PartType` and `AircraftModel` nodes, so "
          "one query crosses both domains:", "",
          "> *For engine-driven pumps on the A320 family: how many incidents, and who is qualified to work on them?*", "",
          f"- Maintenance side (real FAA data): **{len(reports)} incident reports** in 2025.",
          f"- HR side (synthetic): **{len(q_valid)} qualified technicians** with a valid certification "
          f"({', '.join(f'{s}: {n}' for s, n in sites.most_common())}); **{len(q_all) - len(q_valid)} more** "
          "would be counted if expiry dates were ignored.",
          "- Same `kgcore/` (facts, graph, exports). The HR domain added one generic module, "
          "`kgcore/lexicon.py` (label-based linking to a reference taxonomy), and edge attributes "
          "(validity dates, sensitivity).", ""]

    (OUT / "hr_report.md").write_text("\n".join(L), encoding="utf-8")
    if not quiet:
        print("\n".join(L))
    return {
        "employees": len(emp), "occ_labels": n_occ_labels, "occ_amb": len(amb_occ),
        "titles": {k: int(tl_counts.get(k, 0)) for k in ("resolved", "ambiguous", "unresolved")},
        "amb_titles": amb_titles, "company_titles": unres_titles,
        "vague": {k: int(sk_v.get(k, 0)) for k in ("resolved", "ambiguous", "unresolved")},
        "raw_cross_real": rr, "raw_cross_vague": [next(f.object.label for f in raw_facts if f.object.id == x) for x in rv], "esco_cross_real": er,
        "raw_islands": len(rc), "raw_mixed": rm, "esco_islands": len(ec), "esco_mixed": em,
        "hub_links": deg_emp[0][1],
        "mobility": [{"name": n, "pairs": len(ps), "absurd": sum(1 for a, o in ps if overlap(a, o) == 0)}
                     for n, ps in rows],
        "typed_suggestions": len(people) - abstain, "typed_abstain": abstain,
        "teams": len(team_size), "small_teams": len(small_teams), "exposed": exposed, "k": k,
        "two_managers": two, "expired_people": expired,
        "bridge_reports": len(reports), "bridge_valid": len(q_valid), "bridge_ignored_expiry": len(q_all) - len(q_valid),
    }


if __name__ == "__main__":
    main()
