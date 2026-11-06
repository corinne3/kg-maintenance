"""Generate the SYNTHETIC HR data of a fictional aerospace company.

    python -m domains.hr.generate

No real person. Names are ids (E001...). Job titles and skills are written
the way people type them in an HR system: ESCO labels, synonyms, French or
English depending on the site, company-specific titles and vague skills.
The true occupation is kept in a separate column so that entity linking can
be scored; it is never used to build the graph.
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd
import yaml

from domains.hr.esco import load
from kgcore.lexicon import gendered_variants

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "hr_synthetic"


def _labels(row, lang: str) -> tuple[str, list[str]]:
    pref = row[f"label_{lang}"]
    alts = row[f"alt_{lang}"]
    alt_list = [a for a in alts.split("\n") if a.strip()] if isinstance(alts, str) else []
    return pref, alt_list


def _readable(label: str, rnd: random.Random) -> str:
    """'ingénieur/ingénieure de données' -> one gendered form, as a person would type it."""
    forms = gendered_variants(label)
    forms = [f for f in forms[1:] if len(f.split()) > 1] or [label]
    return rnd.choice(forms)


def main():
    cfg = yaml.safe_load(open(ROOT / "domains" / "hr" / "config.yaml", encoding="utf-8"))
    rnd = random.Random(cfg["seed"])
    esco = load(cfg)
    occ_by_label = {r.label_en.lower(): r for r in esco.occ.itertuples()}
    skill_by_uri = {r.uri: r for r in esco.skills.itertuples()}
    sites = list(cfg["sites"])
    shares = [cfg["sites"][s]["share"] for s in sites]

    employees, declared = [], []
    n = 0
    for occ_label, count in cfg["occupations"].items():
        occ = occ_by_label[occ_label.lower()]
        for _ in range(count):
            n += 1
            eid = f"E{n:03d}"
            site = "Toulouse" if occ_label == "operations manager" else rnd.choices(sites, shares)[0]
            lang = cfg["sites"][site]["language"]
            pref, alts = _labels(occ._asdict(), lang)
            r = rnd.random()
            company = cfg["company_titles"].get(occ_label, {}).get(lang, [])
            if r < cfg["company_title_rate"] and company:
                title, title_kind = rnd.choice(company), "company"
            elif r < cfg["company_title_rate"] + cfg["alt_label_rate"] and alts:
                title, title_kind = _readable(rnd.choice(alts), rnd), "esco_alt"
            else:
                title, title_kind = _readable(pref, rnd), "esco_pref"
            employees.append({"employee": eid, "site": site, "job_title": title,
                              "title_kind": title_kind, "true_occupation": occ.uri,
                              "salary_band": cfg["salary_bands"][occ_label],
                              "long_absence": rnd.random() < cfg["long_absence_rate"],
                              "synthetic": True})
            ess = [s for s in esco.essential[occ.uri] if s in skill_by_uri]
            for s in rnd.sample(ess, min(cfg["skills_per_employee"], len(ess))):
                srow = skill_by_uri[s]._asdict()
                p, a = _labels(srow, lang)
                text = _readable(rnd.choice(a), rnd) if (a and rnd.random() < cfg["alt_label_rate"]) else _readable(p, rnd)
                declared.append({"employee": eid, "skill_text": text, "true_skill": s, "kind": "esco", "synthetic": True})
            for v in rnd.sample(cfg["vague_skills"][lang], cfg["vague_per_employee"]):
                declared.append({"employee": eid, "skill_text": v, "true_skill": "", "kind": "vague", "synthetic": True})

    emp = pd.DataFrame(employees)
    occ_label_of = {r.uri: r.label_en for r in esco.occ.itertuples()}
    ops = emp[emp.true_occupation.map(occ_label_of) == "operations manager"].employee.iloc[0]

    # Teams: per occupation and site, at most 8 people; first member = team manager.
    reporting = []
    reorg = cfg["reorg"]
    for (occ_uri, site), grp in emp.groupby(["true_occupation", "site"], sort=True):
        ids = list(grp.employee)
        if occ_uri == emp.loc[emp.employee == ops, "true_occupation"].iloc[0]:
            continue
        for i in range(0, len(ids), 8):
            team = ids[i:i + 8]
            lead, members = team[0], team[1:]
            reporting.append({"employee": lead, "manager": ops, "valid_from": "2024-01-01", "valid_to": ""})
            is_reorg = occ_label_of[occ_uri] == reorg["occupation"] and site == reorg["site"] and len(members) >= 4
            for j, m in enumerate(members):
                if is_reorg and j >= len(members) // 2:
                    new_lead = members[len(members) // 2]
                    reporting.append({"employee": m, "manager": lead, "valid_from": "2024-01-01",
                                      "valid_to": "2026-06-30"})
                    if m != new_lead:
                        reporting.append({"employee": m, "manager": new_lead,
                                          "valid_from": reorg["date"], "valid_to": ""})
                    else:
                        reporting.append({"employee": m, "manager": ops, "valid_from": reorg["date"], "valid_to": ""})
                else:
                    reporting.append({"employee": m, "manager": lead, "valid_from": "2024-01-01", "valid_to": ""})

    # Projects, with the operations manager on most of them (the human hub).
    others = [e for e in emp.employee if e != ops]
    members = []
    for p in range(1, cfg["projects"] + 1):
        pid = f"P{p:02d}"
        k = rnd.randint(*cfg["project_size"])
        for e in rnd.sample(others, k):
            members.append({"project": pid, "employee": e})
        if p <= cfg["hub_projects"]:
            members.append({"project": pid, "employee": ops})

    # Certifications: Part-66 style type ratings and part types (bridge to maintenance).
    c = cfg["certifications"]
    cert_occ = {occ_by_label[o.lower()].uri for o in c["occupations"]}
    certs = []
    for e in emp[emp.true_occupation.isin(cert_occ)].itertuples():
        expired = rnd.random() < c["expired_rate"]
        valid_to = f"2025-{rnd.randint(1, 12):02d}-28" if expired else f"{rnd.choice([2027, 2028])}-{rnd.randint(1, 12):02d}-28"
        for tr in rnd.sample(c["type_ratings"][e.site], rnd.randint(1, 2)):
            certs.append({"employee": e.employee, "kind": "type_rating", "value": tr,
                          "valid_to": valid_to, "synthetic": True})
        for pt in rnd.sample(c["part_types"], rnd.randint(2, 4)):
            certs.append({"employee": e.employee, "kind": "part_type", "value": pt,
                          "valid_to": valid_to, "synthetic": True})

    OUT.mkdir(parents=True, exist_ok=True)
    emp.to_csv(OUT / "employees.csv", index=False)
    pd.DataFrame(declared).to_csv(OUT / "declared_skills.csv", index=False)
    pd.DataFrame(reporting).assign(synthetic=True).to_csv(OUT / "reporting.csv", index=False)
    pd.DataFrame(members).assign(synthetic=True).to_csv(OUT / "project_members.csv", index=False)
    pd.DataFrame(certs).to_csv(OUT / "certifications.csv", index=False)
    (OUT / "README.md").write_text(
        "# Synthetic HR data\n\nGenerated by `python -m domains.hr.generate` (seed in `domains/hr/config.yaml`).\n"
        "No real person. A fictional aerospace company used to test the knowledge graph stack.\n",
        encoding="utf-8")
    print(f"{len(emp)} employees, {len(declared)} declared skills, {len(reporting)} reporting lines, "
          f"{len(members)} project memberships, {len(certs)} certifications -> {OUT}")


if __name__ == "__main__":
    main()
