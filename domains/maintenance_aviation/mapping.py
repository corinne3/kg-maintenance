"""Domaine maintenance : une ligne FAA -> une liste de faits.

C'est la seule partie du code qui connaît les colonnes du fichier FAA.
"""
from __future__ import annotations

import re

import pandas as pd

from kgcore.facts import Fact, Node
from kgcore.resolver import AliasResolver, resolve_by_patterns


def _clean(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


class MaintenanceMapper:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.parts = AliasResolver(cfg["part_types"])
        self.amm = re.compile(cfg["amm_pattern"])
        self.ignore = set(cfg.get("part_name_ignore", []))
        self.unmapped_part_names: dict[str, int] = {}

    def part_from_structured(self, part_name: str) -> str | None:
        name = part_name.upper()
        if not name or name in self.ignore:
            return None
        canonical = self.parts.resolve_value(name)
        if canonical is None:
            self.unmapped_part_names[name] = self.unmapped_part_names.get(name, 0) + 1
        return canonical

    def facts(self, row: pd.Series, use_text: bool = True) -> list[Fact]:
        rid = _clean(row["OperatorControlNumber"])
        report = Node("Report", rid, rid)
        out: list[Fact] = []

        def add(rel, obj, source="structured", evidence=""):
            out.append(Fact(report, rel, obj, source, rid, evidence))

        # --- Avion, modèle, constructeur
        reg = _clean(row["RegistryNNumber"])
        make_code = _clean(row["AircraftMake"]).upper()
        make = self.cfg["manufacturers"].get(make_code, make_code or "INCONNU")
        family = resolve_by_patterns(_clean(row["AircraftModel"]),
                                     self.cfg["model_families"]) or _clean(row["AircraftModel"])
        if reg:
            aircraft = Node("Aircraft", reg, reg)
            add("CONCERNS", aircraft)
            if family:
                model = Node("AircraftModel", family, family)
                out.append(Fact(aircraft, "IS_MODEL", model, "structured", rid))
                out.append(Fact(model, "MADE_BY", Node("Manufacturer", make, make),
                                "structured", rid, evidence=make_code))

        # --- Opérateur, code JASC, état de la pièce
        op = _clean(row["OperatorDesignator"])
        if op:
            add("REPORTED_BY", Node("Operator", op, op))
        jasc = _clean(row["JASCCode"])
        if jasc:
            add("CLASSIFIED_AS", Node("JascCode", jasc, jasc))
        cond = _clean(row["PartCondition"]).upper()
        if cond:
            add("HAS_CONDITION", Node("Condition", cond, cond))

        # --- Pièce : champ structuré
        pn = _clean(row["PartName"])
        canonical = self.part_from_structured(pn)
        if canonical:
            add("INVOLVES_PART",
                Node("PartType", canonical, self.parts.labels[canonical]),
                "structured", pn)

        # --- Pièce et tâches AMM : texte libre (dictionnaire)
        if use_text:
            text = _clean(row["Discrepancy"])
            seen = set()
            for m in self.parts.find(text):
                if m.canonical in seen:
                    continue
                seen.add(m.canonical)
                add("INVOLVES_PART",
                    Node("PartType", m.canonical, self.parts.labels[m.canonical]),
                    "dictionary", m.surface)
            for task in sorted(set(self.amm.findall(text.upper()))):
                add("REFERENCES", Node("AmmTask", task, f"AMM {task}"),
                    "dictionary", f"AMM {task}")
        return out
