"""A small agent over the two knowledge graphs.

Loop: plan -> validate -> check access -> run -> check the result -> (retry / escalate) -> answer.
Every decision is written to a trace, so a person can see why the agent did what it did.

Routing modes:
  rules   : deterministic rules only (no LLM)
  llm     : the LLM chooses tools and arguments
  hybrid  : rules first; the LLM only when no rule applies (same idea as the extraction hybrid)
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass, field

from assistant.tools import Tool, validate

MAX_STEPS = 3

PLAN_PROMPT = """You route questions about aircraft hydraulic maintenance (FAA incident reports) and about
the HR data of a fictional aerospace company to tools. Choose the tools needed and their arguments.

Tools (JSON):
{tools}

Rules:
- Use ONLY the tools above and ONLY the allowed values.
- A question may need two tools (for example incidents AND qualified people).
- If no tool can answer, return no steps and reason "out_of_scope".
Return ONLY JSON: {{"steps": [{{"tool": "...", "args": {{...}}}}], "reason": "..."}}

Question: {question}"""

ANSWER_PROMPT = """Answer the question using ONLY the tool results below. Cite report or employee ids in
square brackets when you use them. Say clearly when a result was refused, relaxed or empty. 4 sentences max.

Tool results:
{results}

Question: {question}
Answer:"""


@dataclass
class Step:
    what: str
    detail: str
    by: str = ""
    seconds: float = 0.0


@dataclass
class Run:
    question: str
    role: str
    mode: str
    plan: list = field(default_factory=list)       # [(tool, args)]
    outcome: str = ""                              # answered | refused | escalated
    results: list = field(default_factory=list)    # [(tool, args, result)]
    trace: list = field(default_factory=list)
    answer: str = ""

    def log(self, what, detail, by="", seconds=0.0):
        self.trace.append(Step(what, detail, by, round(seconds, 1)))


class Agent:
    def __init__(self, kb, tools: dict[str, Tool], llm=None):
        self.kb, self.tools, self.llm = kb, tools, llm

    # ------------------------------------------------------------ planning
    def rules_plan(self, q: str) -> list | None:
        ql = q.lower()
        linked = self.kb.link(q)
        part = linked["parts"][0] if linked["parts"] else None
        fam = "A320 FAMILY" if "a320 family" in ql else (linked["families"][0] if linked["families"] else None)
        cond = linked["conditions"][0] if linked["conditions"] else None
        emp = re.search(r"\bE\d{3}\b", q.upper())
        if re.search(r"\b(salary|salaries|pay|absence|absent|sick)\b", ql):
            return [("team_aggregate", {"manager_id": emp.group(0) if emp else "",
                                        "attribute": "salary_band" if re.search(r"salar|pay", ql) else "long_absence"})]
        if emp and re.search(r"\b(move|mobility|career|suit|next job)\b", ql):
            return [("internal_mobility", {"employee_id": emp.group(0)})]
        steps = []
        if part and re.search(r"\bwho\b.*\b(qualified|certified|can work|work on|authori[sz]ed)\b", ql):
            steps.append(("qualified_technicians", {"part_type": part, "aircraft_family": fam}))
        if part and re.search(r"\b(how many|which|what problems|tasks|operators|most|incidents)\b", ql):
            steps.append(("maintenance_stats", {"part_type": part, "aircraft_family": fam, "condition": cond}))
        if steps:
            return steps
        if re.search(r"\b(hydraulic|pump|leak|reservoir|pressure|fluid|cavitat|smell|noise)\w*", ql):
            return [("report_search", {"query": q})]
        return None

    def llm_plan(self, q: str) -> tuple[list | None, str]:
        specs = json.dumps([t.spec() for t in self.tools.values()], ensure_ascii=False)
        raw = self.llm(PLAN_PROMPT.format(tools=specs, question=q), json_mode=True)
        try:
            out = json.loads(raw)
            steps = [(s.get("tool", ""), s.get("args", {}) or {}) for s in out.get("steps", [])]
            return (steps or None), out.get("reason", "")
        except Exception:  # noqa: BLE001
            return None, f"invalid JSON from the LLM: {raw[:120]}"

    def plan(self, q: str, mode: str, run: Run) -> list | None:
        if mode in ("rules", "hybrid"):
            t0 = time.time()
            steps = self.rules_plan(q)
            if steps:
                run.log("plan", ", ".join(s for s, _ in steps), "rules", time.time() - t0)
                return steps
            if mode == "rules":
                run.log("plan", "no rule matches the question", "rules")
                return None
            run.log("plan", "no rule matches: asking the LLM", "rules")
        if self.llm is None:
            run.log("plan", "no LLM available", "llm")
            return None
        t0 = time.time()
        steps, reason = self.llm_plan(q)
        run.log("plan", (", ".join(s for s, _ in steps) if steps else f"no tool ({reason or 'no reason'})"),
                "llm", time.time() - t0)
        return steps

    # ------------------------------------------------------------ repair of arguments
    def repair(self, key: str, value: str) -> str | None:
        if key == "part_type":
            m = self.kb.mapper.parts.find(value.replace("_", " "))
            return m[0].canonical if m else None
        if key == "aircraft_family" and "320" in value:
            return "A320 FAMILY"
        if key == "condition":
            return next((c for w, c in [("LEAK", "LEAKING"), ("FAIL", "FAILED"), ("OVERHEAT", "OVERHEATED"),
                                        ("CRACK", "CRACKED"), ("FAULT", "FAULTED")] if w in value.upper()), None)
        return None

    # ------------------------------------------------------------ the loop
    def run(self, q: str, role: str = "employee", mode: str = "hybrid", answer: bool = False) -> Run:
        run = Run(q, role, mode)
        steps = self.plan(q, mode, run)
        if not steps:
            run.outcome = "escalated"
            run.log("escalate", "no tool can answer: handed over to a person, nothing invented")
            run.answer = "I cannot answer this from the maintenance or HR data. Escalated to a person."
            return run
        for name, args in steps[:MAX_STEPS]:
            tool = self.tools.get(name)
            if tool is None:
                run.log("validate", f"unknown tool '{name}' rejected")
                continue
            clean, problems = validate(tool, args, self.repair)
            for p in problems:
                run.log("validate", f"{name}: {p}")
            if any(p.startswith("missing") for p in problems):
                run.log("skip", f"{name} not run: required argument missing")
                continue
            if role not in tool.roles:
                run.log("access", f"{name} refused for role '{role}' (sensitive data, roles allowed: {', '.join(tool.roles)})")
                run.plan.append((name, clean))
                run.results.append((name, clean, {"refused": f"not allowed for role {role}"}))
                continue
            run.plan.append((name, clean))
            t0 = time.time()
            result = tool.run(**clean)
            run.log("run", f"{name}({', '.join(f'{k}={v}' for k, v in clean.items())})", "", time.time() - t0)
            text = getattr(result, "text", None)
            if text is not None and "Matching reports: 0" in text and name == "maintenance_stats":
                run.log("check", "0 matching reports: falling back to a text search")
                result = self.tools["report_search"].run(query=q)
                run.plan.append(("report_search", {"query": q}))
            if text is not None and "Filter relaxed" in text:
                run.log("check", "strict filter found nothing: relaxed to the free text, and said so in the result")
            if isinstance(result, dict) and "refused" in result:
                run.log("check", f"refused by the data layer: {result['refused']}")
            if isinstance(result, dict) and "error" in result:
                run.log("check", f"tool could not answer: {result['error']}")
            run.results.append((name, clean, result))
        def kind(r):
            return ("refused" if isinstance(r, dict) and "refused" in r else
                    "error" if isinstance(r, dict) and "error" in r else "ok")
        kinds = [kind(r) for _, _, r in run.results]
        if not kinds or all(k == "error" for k in kinds):
            run.outcome = "escalated"
            run.log("escalate", "no usable result: handed over to a person")
        elif all(k == "refused" for k in kinds):
            run.outcome = "refused"
        else:
            run.outcome = "answered"
        if answer and self.llm and run.outcome == "answered":
            t0 = time.time()
            run.answer = self.llm(ANSWER_PROMPT.format(results=self.render(run), question=q))
            run.log("answer", "written by the LLM from the tool results only", "llm", time.time() - t0)
        else:
            run.answer = self.render(run)
        return run

    @staticmethod
    def render(run: Run) -> str:
        out = []
        for name, args, res in run.results:
            body = res.text if hasattr(res, "text") else json.dumps(res, ensure_ascii=False, default=str)
            out.append(f"[{name}] {body[:1500]}")
        return "\n\n".join(out)


def ollama(model: str = "llama3.2:3b", host: str = "http://localhost:11434"):
    def call(prompt: str, json_mode: bool = False) -> str:
        body = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False,
                "keep_alive": "60m", "options": {"temperature": 0, "num_ctx": 4096}}
        if json_mode:
            body["format"] = "json"
        req = urllib.request.Request(f"{host}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())["message"]["content"]
    return call
