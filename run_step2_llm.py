"""Step 2 — Extraction with a local LLM (Ollama), then evaluation.

Run on your machine (Ollama installed and running):

    ollama pull llama3.2:3b
    python run_step2_llm.py --limit 30            # quick test
    python run_step2_llm.py --only-pump           # the 117 "PUMP" reports (the real question)
    python run_step2_llm.py                        # all 514 reports (hours on CPU)
    python run_step2_llm.py --evaluate-only        # rebuild the report without calling the LLM

The script resumes where it stopped (results are appended to
outputs/llm_<model>.jsonl as they come). You can stop it with Ctrl+C.

What is measured (reliability of extraction):
  - invalid JSON outputs;
  - part types invented outside the closed list;
  - maintenance manual (AMM) references not found in the text;
  - on the "PUMP" reports: which pump the LLM says failed, compared with
    the dictionary and with the reference (data/ground_truth.xlsx).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from domains.maintenance_aviation.mapping import MaintenanceMapper  # noqa: E402
from kgcore.loader import load_domain, load_records  # noqa: E402

OUT = ROOT / "outputs"
ACTIONS = ["REPLACED", "REPAIRED", "SERVICED", "INSPECTED_OK", "DEFERRED", "UNKNOWN"]
PUMPS = ["ENGINE_DRIVEN_PUMP", "ELECTRIC_MOTOR_PUMP", "POWER_TRANSFER_UNIT", "RAM_AIR_TURBINE"]

PROMPT = """You extract facts from an aircraft hydraulic maintenance report.

Allowed part types (use ONLY these keys):
{types}

Return ONLY a JSON object with exactly these keys:
- "faulty_parts": list of part type keys that were defective, failed, leaking or replaced because of a defect
- "mentioned_parts": list of other part type keys that are only mentioned (checked, shut off, inspected OK)
- "action": one of {actions}
- "amm_tasks": list of AMM task references written in the text, format "29-11-51" (empty list if none)

Report:
\"\"\"{text}\"\"\"
"""


def call_ollama(model: str, prompt: str, host: str) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
        "keep_alive": "60m",  # keep the model in memory between reports
        "options": {"temperature": 0, "num_ctx": 2048},
    }).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["message"]["content"]


def mock_llm(mapper: MaintenanceMapper):
    """Fake LLM (the dictionary) to test the pipeline without Ollama."""
    def run(text: str) -> str:
        found = list(dict.fromkeys(m.canonical for m in mapper.parts.find(text)))
        return json.dumps({"faulty_parts": found[:1], "mentioned_parts": found[1:],
                           "action": "UNKNOWN",
                           "amm_tasks": sorted(set(mapper.amm.findall(text.upper())))})
    return run


def extract(args, df, mapper, path: Path):
    done = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            done.add(json.loads(line)["id"])
    types = "\n".join(f"- {k}: {v['label']}" for k, v in mapper.cfg["part_types"].items())
    llm = mock_llm(mapper) if args.mock else None
    rows = [r for _, r in df.iterrows()]
    if args.only_pump:
        rows = [r for r in rows
                if mapper.part_from_structured(str(r["PartName"])) == "HYDRAULIC_PUMP_UNSPECIFIED"]
    todo = [r for r in rows if r["OperatorControlNumber"] not in done]
    if args.limit:
        todo = todo[: max(0, args.limit - len(done))]
    print(f"{len(done)} already done, {len(todo)} to do with {args.model}")
    with open(path, "a", encoding="utf-8") as fh:
        for i, r in enumerate(todo, 1):
            text = str(r["Discrepancy"])
            t0 = time.time()
            try:
                if llm:
                    raw = llm(text)
                else:
                    raw = call_ollama(args.model, PROMPT.format(
                        types=types, actions=ACTIONS, text=text[:3000]), args.host)
                err = ""
            except Exception as e:  # noqa: BLE001
                raw, err = "", repr(e)
            rec = {"id": r["OperatorControlNumber"], "raw": raw, "error": err,
                   "seconds": round(time.time() - t0, 1)}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  [{i}/{len(todo)}] {rec['id']} {rec['seconds']} s {'ERROR' if err else ''}")


def as_list(v):
    if isinstance(v, list):
        return [str(x).strip().upper() for x in v]
    if isinstance(v, str) and v.strip():
        return [v.strip().upper()]
    return []


def to_label(pumps: list[str]) -> str:
    """List of part types -> one label comparable to the reference."""
    pumps = [p for p in PUMPS if p in pumps]
    if not pumps:
        return "NO_PUMP_FAILED"
    return pumps[0] if len(pumps) == 1 else "SEVERAL"


def load_reference() -> tuple[dict, str]:
    path = ROOT / "data" / "ground_truth.xlsx"
    if not path.exists():
        return {}, ""
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    ref = {r[0]: {"gold": r[4], "comment": r[6] or ""} for r in rows if r[0] and r[4]}
    annot = {r[7] for r in rows if len(r) > 7 and r[7]}
    return ref, ", ".join(sorted(annot))


def summarize(df, mapper, recs: list[dict]) -> dict:
    """All step-2 metrics, used by the Markdown report and by the explorer page."""
    allowed = set(mapper.cfg["part_types"])
    by_id = df.set_index("OperatorControlNumber")
    invalid, invented, resp_invented = 0, Counter(), 0
    amm_total, amm_bad = 0, []
    pump_llm, pump_dico = Counter(), Counter()
    llm_label = {}
    for r in recs:
        text = str(by_id.loc[r["id"], "Discrepancy"]).upper()
        try:
            out = json.loads(r["raw"])
            assert isinstance(out, dict)
        except Exception:  # noqa: BLE001
            invalid += 1
            llm_label[r["id"]] = "INVALID"
            continue
        faulty = as_list(out.get("faulty_parts"))
        mentioned = as_list(out.get("mentioned_parts"))
        bad = [p for p in faulty + mentioned if p not in allowed]
        invented.update(bad)
        resp_invented += bool(bad)
        for t in as_list(out.get("amm_tasks")):
            amm_total += 1
            t = t.replace("AMM", "").strip()
            if t not in text:
                amm_bad.append({"id": r["id"], "llm": t,
                                "text": [x for x in re.findall(r"\d\d-\d\d-\d\d[\w-]*", text)
                                         if x[:5] == t[:5]][:2]})
        llm_label[r["id"]] = to_label(faulty)
        if mapper.part_from_structured(str(by_id.loc[r["id"], "PartName"])) == "HYDRAULIC_PUMP_UNSPECIFIED":
            pump_llm[llm_label[r["id"]]] += 1
            pump_dico[to_label([m.canonical for m in mapper.parts.find(text)])] += 1
    pump_secs = [r["seconds"] for r in recs if not r["error"] and r["id"] in by_id.index
                 and mapper.part_from_structured(str(by_id.loc[r["id"], "PartName"])) == "HYDRAULIC_PUMP_UNSPECIFIED"]

    ref, annotator = load_reference()
    rows, score = [], Counter()
    for rid, v in ref.items():
        if rid not in by_id.index:
            continue
        dico = to_label([m.canonical for m in mapper.parts.find(str(by_id.loc[rid, "Discrepancy"]))])
        llm = llm_label.get(rid, "-")
        # Hybrid rule: trust the dictionary when it finds 0 or 1 pump, ask the LLM otherwise.
        hybrid = llm if dico == "SEVERAL" and llm not in ("-", "INVALID") else dico
        scored = v["gold"] != "CANNOT_TELL"
        if scored:
            score["n"] += 1
            score["dico"] += dico == v["gold"]
            score["llm"] += llm == v["gold"]
            score["hybrid"] += hybrid == v["gold"]
            score["llm_seen"] += llm != "-"
        rows.append({"id": rid, "gold": v["gold"], "comment": v["comment"], "dico": dico,
                     "llm": llm, "hybrid": hybrid, "scored": scored})
    return {
        "n": len(recs), "invalid": invalid,
        "pump_seconds": round(sum(pump_secs) / len(pump_secs), 1) if pump_secs else None,
        "n_pump": len(pump_secs),
        "invented": invented.most_common(), "resp_invented": resp_invented,
        "amm_total": amm_total, "amm_bad": amm_bad,
        "pump_llm": dict(pump_llm), "pump_dico": dict(pump_dico),
        "reference": rows, "annotator": annotator, "score": dict(score),
    }


def evaluate(df, mapper, path: Path, model: str) -> str:
    recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    s = summarize(df, mapper, recs)
    sc = s["score"]
    L = [f"# Step 2 — LLM extraction ({model})", "",
         f"- Reports processed: **{s['n']}** (of which {s['n_pump']} \"PUMP\" reports)",
         f"- Average time per \"PUMP\" report: **{s['pump_seconds']} s** (CPU only, 8 GB RAM)" if s["pump_seconds"] else "",
         f"- Invalid JSON outputs: **{s['invalid']}**",
         f"- Responses with at least one part type outside the allowed list: **{s['resp_invented']} / {s['n']}** "
         f"({100 * s['resp_invented'] / max(1, s['n']):.0f}%). Examples: "
         + ", ".join(f"`{k}` ×{v}" for k, v in s["invented"][:6]),
         f"- Maintenance manual (AMM) references not found in the text: **{len(s['amm_bad'])} / {s['amm_total']}**. "
         "They are near-copies of real references, which makes them hard to spot:"]
    L += [f"    - `{a['id']}`: LLM wrote `{a['llm']}`, text says {', '.join(f'`{x}`' for x in a['text']) or '(nothing close)'}"
          for a in s["amm_bad"]]
    L += ["", "## \"PUMP\" reports: which pump failed?", "",
          "| Answer | Dictionary | LLM |", "| --- | ---: | ---: |"]
    for k in PUMPS + ["SEVERAL", "NO_PUMP_FAILED"]:
        name = "NO_PUMP_FAILED (dictionary: no specific pump found)" if k == "NO_PUMP_FAILED" else k
        L.append(f"| {name} | {s['pump_dico'].get(k, 0)} | {s['pump_llm'].get(k, 0)} |")
    if s["reference"]:
        L += ["", f"## Comparison with the reference ({len(s['reference'])} \"PUMP\" reports)", "",
              f"Reference: `data/ground_truth.xlsx`, annotator: {s['annotator'] or '?'}.", "",
              "| Report | Reference | Dictionary | LLM | Hybrid |", "| --- | --- | --- | --- | --- |"]
        for r in s["reference"]:
            m = lambda x: f"**{x}**" if r["scored"] and x == r["gold"] else x  # noqa: E731
            L.append(f"| `{r['id']}` | {r['gold']} | {m(r['dico'])} | {m(r['llm'])} | {m(r['hybrid'])} |")
        L += ["", f"- Dictionary: **{sc.get('dico', 0)} / {sc.get('n', 0)}**",
              f"- LLM: **{sc.get('llm', 0)} / {sc.get('n', 0)}**",
              f"- Hybrid (dictionary when it finds 0 or 1 pump, LLM when it finds several): "
              f"**{sc.get('hybrid', 0)} / {sc.get('n', 0)}**",
              "- `CANNOT_TELL` in the reference is not scored. Bold = matches the reference.",
              "- Limits: 19 scored cases, 12 of them chosen because they are ambiguous; the reference "
              "is an LLM (Claude), not a maintenance expert. Trends, not proof.", ""]
    return "\n".join(x for x in L if x is not None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2:3b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--mock", action="store_true", help="test without Ollama")
    ap.add_argument("--only-pump", action="store_true",
                    help="only the 117 reports whose structured field says PUMP")
    ap.add_argument("--evaluate-only", action="store_true")
    args = ap.parse_args()

    cfg = load_domain("maintenance_aviation")
    df = load_records(cfg)
    mapper = MaintenanceMapper(cfg)
    tag = "mock" if args.mock else args.model.replace(":", "_").replace("/", "_")
    path = OUT / f"llm_{tag}.jsonl"
    OUT.mkdir(exist_ok=True)
    if not args.evaluate_only and not args.mock:
        try:
            urllib.request.urlopen(f"{args.host}/api/tags", timeout=5)
        except Exception:  # noqa: BLE001
            sys.exit(f"Ollama is not answering on {args.host}. Start the Ollama app "
                     f"(or `ollama serve`), then `ollama pull {args.model}`.")
    if not args.evaluate_only:
        extract(args, df, mapper, path)
    report = evaluate(df, mapper, path, "dictionary (mock)" if args.mock else args.model)
    (OUT / f"step2_report_{tag}.md").write_text(report, encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    main()
