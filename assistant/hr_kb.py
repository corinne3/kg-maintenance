"""HR side of the agent: queries on the HR graph (synthetic company + ESCO)."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml

from domains.hr.esco import load
from domains.hr.mapping import HRMapper, load_tables

ROOT = Path(__file__).resolve().parents[1]


class HRBase:
    def __init__(self):
        self.cfg = yaml.safe_load(open(ROOT / "domains" / "hr" / "config.yaml", encoding="utf-8"))
        self.esco = load(self.cfg)
        self.t = load_tables()
        self.facts = HRMapper(self.cfg, self.esco).facts(self.t)
        self.today = self.cfg["certifications"]["today"]
        self.site = dict(zip(self.t["employees"].employee, self.t["employees"].site))
        self.occ = {f.subject.key: (f.object.id, f.object.label) for f in self.facts if f.relation == "HOLDS_OCCUPATION"}
        self.skills = defaultdict(set)
        self.req = defaultdict(set)
        self.occ_label = {}
        for f in self.facts:
            if f.relation == "HAS_SKILL":
                self.skills[f.subject.key].add(f.object.id)
            if f.relation == "REQUIRES":
                self.req[f.subject.id].add(f.object.id)
                self.occ_label[f.subject.id] = f.subject.label

    def qualified(self, part_type: str, families: list[str]) -> dict:
        certs = self.t["certifications"]
        by_emp = defaultdict(list)
        for r in certs.itertuples():
            by_emp[r.employee].append(r)
        valid, expired = [], []
        for e, rows in by_emp.items():
            parts = [r for r in rows if r.kind == "part_type" and r.value == part_type]
            ratings = [r for r in rows if r.kind == "type_rating" and (not families or r.value in families)]
            if not parts or not ratings:
                continue
            ok = all(r.valid_to >= self.today for r in parts + ratings)
            (valid if ok else expired).append(e)
        return {"valid": sorted(valid), "expired": sorted(expired),
                "by_site": {s: sum(1 for e in valid if self.site[e] == s) for s in sorted(set(self.site.values()))}}

    def mobility(self, employee: str, top: int = 3) -> dict:
        if employee not in self.site:
            return {"error": f"unknown employee {employee}"}
        if employee not in self.occ:
            return {"error": f"the job title of {employee} could not be linked to ESCO"}
        own = self.occ[employee][0]
        s = self.skills[employee]
        scored = sorted(((self.occ_label[o], len(s & r) / len(r)) for o, r in self.req.items()
                         if o != own and s & r), key=lambda x: -x[1])
        return {"current": self.occ[employee][1], "suggestions": scored[:top],
                "note": "" if scored else "no job shares any declared skill: no suggestion"}

    def team_aggregate(self, manager: str, attribute: str) -> dict:
        rep = self.t["reporting"]
        current = rep[rep.valid_to == ""]
        team = sorted(current[current.manager == manager].employee.unique())
        k = self.cfg["k_anonymity"]
        if len(team) < k:
            return {"refused": f"team of {len(team)} people, below the k-anonymity threshold of {k}"}
        emp = self.t["employees"].set_index("employee").loc[team]
        if attribute == "salary_band":
            return {"team_size": len(team), "salary_bands": emp.salary_band.value_counts().to_dict()}
        return {"team_size": len(team), "long_absences": int((emp.long_absence == "True").sum())}
