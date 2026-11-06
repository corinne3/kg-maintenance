"""The agent's tools: each one has a schema, allowed values from the ontology, and allowed roles."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

ROLES = ["employee", "manager", "hr"]


@dataclass
class Tool:
    name: str
    description: str
    params: dict            # name -> {"type": "enum"|"str"|"employee", "values": [...], "required": bool}
    run: Callable
    roles: list = field(default_factory=lambda: list(ROLES))
    sensitive: bool = False

    def spec(self) -> dict:
        p = {}
        for k, v in self.params.items():
            d = {"type": "string", "required": v.get("required", False)}
            if v["type"] == "enum":
                d["one_of"] = v["values"]
            if v["type"] == "employee":
                d["format"] = "E followed by 3 digits, e.g. E120"
            p[k] = d
        return {"name": self.name, "description": self.description, "parameters": p}


def build_tools(kb, hr=None) -> dict[str, Tool]:
    """kb: maintenance KnowledgeBase; hr: HRBase (optional, needs ESCO files)."""
    parts = list(kb.cfg["part_types"])
    groups = {g: [str(m) for m in ms] for g, ms in kb.cfg.get("model_groups", {}).items()}
    families = sorted(groups) + ["737", "757", "767", "777", "A330", "ERJ"]
    conditions = ["LEAKING", "FAILED", "FAULTED", "CRACKED", "CORRODED", "DAMAGED", "INOPERATIVE", "OVERHEATED"]

    def expand(fam):
        if not fam:
            return []
        return groups.get(fam, [fam])

    def maintenance_stats(part_type, aircraft_family=None, condition=None):
        return kb.guided_query(part_type, expand(aircraft_family), [condition] if condition else [])

    def report_search(query):
        return kb.text_rag(query)

    tools = {
        "maintenance_stats": Tool(
            "maintenance_stats",
            "Counts and aggregates FAA hydraulic incident reports for one part type: conditions, "
            "maintenance manual tasks, aircraft families, operators. Use for 'how many', 'which', 'most'.",
            {"part_type": {"type": "enum", "values": parts, "required": True},
             "aircraft_family": {"type": "enum", "values": families},
             "condition": {"type": "enum", "values": conditions}},
            maintenance_stats),
        "report_search": Tool(
            "report_search",
            "Finds the incident report texts most similar to a free-text description. Use when the "
            "question describes a symptom or situation rather than a part type.",
            {"query": {"type": "str", "required": True}},
            report_search),
    }
    if hr is not None:
        hr_parts = sorted({r.value for r in hr.t["certifications"].itertuples() if r.kind == "part_type"})
        tools["qualified_technicians"] = Tool(
            "qualified_technicians",
            "Lists technicians with a VALID certification for a part type and a type rating on an aircraft "
            "family (synthetic HR data).",
            {"part_type": {"type": "enum", "values": hr_parts, "required": True},
             "aircraft_family": {"type": "enum", "values": families}},
            lambda part_type, aircraft_family=None: hr.qualified(part_type, expand(aircraft_family)))
        tools["internal_mobility"] = Tool(
            "internal_mobility",
            "Suggests internal moves for one employee, from their skills vs the skills each job requires (ESCO).",
            {"employee_id": {"type": "employee", "required": True}},
            lambda employee_id: hr.mobility(employee_id))
        tools["team_aggregate"] = Tool(
            "team_aggregate",
            "Aggregates a sensitive attribute (salary band or long absences) over a manager's team. "
            "HR role only; refused for teams under the k-anonymity threshold.",
            {"manager_id": {"type": "employee", "required": True},
             "attribute": {"type": "enum", "values": ["salary_band", "long_absence"], "required": True}},
            lambda manager_id, attribute: hr.team_aggregate(manager_id, attribute),
            roles=["hr"], sensitive=True)
    return tools


def validate(tool: Tool, args: dict, repair: Callable | None = None) -> tuple[dict, list[str]]:
    """Check arguments against the schema. Returns (clean args, problems). Tries to repair enum values."""
    clean, problems = {}, []
    for k, v in (args or {}).items():
        if k not in tool.params:
            problems.append(f"unknown argument '{k}' dropped")
            continue
        spec = tool.params[k]
        if v in (None, "", "null"):
            continue
        v = str(v).strip()
        if spec["type"] == "enum":
            match = next((x for x in spec["values"] if x.upper() == v.upper()), None)
            if match is None and repair:
                fixed = repair(k, v)
                if fixed in spec["values"]:
                    problems.append(f"'{v}' repaired to '{fixed}'")
                    match = fixed
            if match is None:
                problems.append(f"'{v}' is not an allowed value for {k}")
                continue
            clean[k] = match
        elif spec["type"] == "employee":
            if not re.fullmatch(r"E\d{3}", v.upper()):
                problems.append(f"'{v}' is not an employee id")
                continue
            clean[k] = v.upper()
        else:
            clean[k] = v
    for k, spec in tool.params.items():
        if spec.get("required") and k not in clean:
            problems.append(f"missing required argument '{k}'")
    return clean, problems
