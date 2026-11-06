"""HR domain: synthetic HR rows + ESCO -> a list of facts (same Fact format as maintenance)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from domains.hr.esco import Esco
from kgcore.facts import Fact, Node

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "hr_synthetic"

PART_LABELS = {  # same keys as the maintenance ontology, so both graphs share these nodes
    "ENGINE_DRIVEN_PUMP": "Engine-driven pump (EDP)",
    "ELECTRIC_MOTOR_PUMP": "Electric motor pump (ACMP / EMDP)",
    "POWER_TRANSFER_UNIT": "Power transfer unit (PTU)",
    "HYDRAULIC_LINE": "Hydraulic line (tube, hose)",
    "RESERVOIR": "Hydraulic reservoir",
    "ACCUMULATOR": "Accumulator",
}


def load_tables() -> dict[str, pd.DataFrame]:
    return {n: pd.read_csv(DATA / f"{n}.csv", dtype=str, keep_default_na=False)
            for n in ["employees", "declared_skills", "reporting", "project_members", "certifications"]}


class HRMapper:
    def __init__(self, cfg: dict, esco: Esco):
        self.cfg, self.esco = cfg, esco
        self.occ_label = dict(zip(esco.occ.uri, esco.occ.label_en))
        self.skill_label = esco.all_skill_labels or dict(zip(esco.skills.uri, esco.skills.label_en))
        self.title_links: list[dict] = []
        self.skill_links: list[dict] = []

    def _occ_node(self, uri: str) -> Node:
        label = self.esco.all_occ_labels.get(uri, uri.rsplit("/", 1)[-1][:8])
        return Node("Occupation", uri.rsplit("/", 1)[-1], label)

    def _skill_node(self, uri: str, label: str | None = None) -> Node:
        return Node("Skill", uri.rsplit("/", 1)[-1], label or self.skill_label.get(uri, uri.rsplit("/", 1)[-1][:8]))

    def facts(self, t: dict[str, pd.DataFrame], use_esco: bool = True) -> list[Fact]:
        out: list[Fact] = []
        emp = lambda e: Node("Employee", e, e)  # noqa: E731
        for r in t["employees"].itertuples():
            e = emp(r.employee)
            out.append(Fact(e, "WORKS_AT", Node("Site", r.site, r.site), "structured", r.employee))
            m = self.esco.full_occ_index.lookup(r.job_title)
            self.title_links.append({"employee": r.employee, "title": r.job_title, "site": r.site,
                                     "kind": r.title_kind, "status": m.status, "ids": m.ids,
                                     "true": r.true_occupation})
            if use_esco and m.status == "resolved":
                out.append(Fact(e, "HOLDS_OCCUPATION", self._occ_node(next(iter(m.ids))),
                                "dictionary", r.employee, r.job_title))
            else:
                out.append(Fact(e, "HAS_RAW_TITLE", Node("RawTitle", r.job_title, r.job_title),
                                "structured", r.employee, r.job_title))
            out.append(Fact(e, "IN_SALARY_BAND", Node("SalaryBand", r.salary_band, r.salary_band),
                            "structured", r.employee, attrs={"sensitive": True}))
            if r.long_absence == "True":
                out.append(Fact(e, "HAS_LONG_ABSENCE", Node("Absence", "LONG_ABSENCE", "Long absence"),
                                "structured", r.employee, attrs={"sensitive": True}))

        for r in t["declared_skills"].itertuples():
            e = emp(r.employee)
            m = self.esco.skill_index.lookup(r.skill_text) if use_esco else None
            status = m.status if m else "not linked"
            self.skill_links.append({"employee": r.employee, "text": r.skill_text, "kind": r.kind,
                                     "status": status, "ids": m.ids if m else set(), "true": r.true_skill})
            if m and m.status == "resolved":
                out.append(Fact(e, "HAS_SKILL", self._skill_node(next(iter(m.ids))),
                                "dictionary", r.employee, r.skill_text))
            else:
                out.append(Fact(e, "DECLARES", Node("RawSkill", r.skill_text.lower(), r.skill_text),
                                "structured", r.employee, r.skill_text))

        if use_esco:
            for occ_uri, skills in self.esco.essential.items():
                o = self._occ_node(occ_uri)
                for s in skills:
                    out.append(Fact(o, "REQUIRES", self._skill_node(s), "esco", occ_uri))

        for r in t["project_members"].itertuples():
            out.append(Fact(emp(r.employee), "MEMBER_OF", Node("Project", r.project, r.project),
                            "structured", r.employee))
        for r in t["reporting"].itertuples():
            out.append(Fact(emp(r.employee), "REPORTS_TO", emp(r.manager), "structured", r.employee,
                            attrs={"valid_from": r.valid_from, "valid_to": r.valid_to}))
        for r in t["certifications"].itertuples():
            if r.kind == "part_type":
                obj = Node("PartType", r.value, PART_LABELS.get(r.value, r.value))
                rel = "CERTIFIED_FOR"
            else:
                obj = Node("AircraftModel", r.value, r.value)
                rel = "TYPE_RATED"
            out.append(Fact(emp(r.employee), rel, obj, "structured", r.employee,
                            attrs={"valid_to": r.valid_to}))
        return out
