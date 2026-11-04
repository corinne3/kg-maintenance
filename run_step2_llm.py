"""Étape 2 — Extraction par LLM local (Ollama), puis évaluation.

À lancer sur ton PC (Ollama installé et démarré) :

    ollama pull llama3.2:3b
    python run_step2_llm.py --limit 30            # essai rapide
    python run_step2_llm.py --only-pump           # les 117 rapports « PUMP » (la vraie question)
    python run_step2_llm.py                        # les 514 rapports (plusieurs heures sur CPU)
    python run_step2_llm.py --evaluate-only        # recalculer le rapport sans relancer le LLM

Le script reprend là où il s'est arrêté (les résultats sont ajoutés au fil de l'eau
dans outputs/llm_<modèle>.jsonl). Tu peux l'interrompre avec Ctrl+C.

Ce qu'on mesure (os n°2 : la fiabilité de l'extraction) :
  - sorties JSON invalides ;
  - types de pièces inventés (hors de la liste fermée) ;
  - tâches AMM inventées (absentes du texte) ;
  - accord avec le champ structuré quand celui-ci est précis ;
  - sur les 117 rapports « PUMP » : quelle pompe le LLM désigne comme en panne.
"""
from __future__ import annotations

import argparse
import json
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
        "keep_alive": "60m",  # garder le modèle en mémoire entre deux rapports
        "options": {"temperature": 0, "num_ctx": 2048},
    }).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["message"]["content"]


def mock_llm(mapper: MaintenanceMapper):
    """Faux LLM (le dictionnaire) pour tester le pipeline sans Ollama."""
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
    print(f"{len(done)} déjà faits, {len(todo)} à faire avec {args.model}")
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
            print(f"  [{i}/{len(todo)}] {rec['id']} {rec['seconds']} s {'ERREUR' if err else ''}")


def as_list(v):
    if isinstance(v, list):
        return [str(x).strip().upper() for x in v]
    if isinstance(v, str) and v.strip():
        return [v.strip().upper()]
    return []


def evaluate(df, mapper, path: Path, model: str) -> str:
    allowed = set(mapper.cfg["part_types"])
    by_id = df.set_index("OperatorControlNumber")
    recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    n = len(recs)
    invalid, invented_types, invented_amm, amm_total = 0, Counter(), 0, 0
    agree = disagree = 0
    pump_llm = Counter()
    secs = [r["seconds"] for r in recs if not r["error"]]
    examples = []
    for r in recs:
        row = by_id.loc[r["id"]]
        text = str(row["Discrepancy"]).upper()
        try:
            out = json.loads(r["raw"])
            assert isinstance(out, dict)
        except Exception:  # noqa: BLE001
            invalid += 1
            continue
        faulty = as_list(out.get("faulty_parts"))
        mentioned = as_list(out.get("mentioned_parts"))
        for p in faulty + mentioned:
            if p not in allowed:
                invented_types[p] += 1
        for t in as_list(out.get("amm_tasks")):
            amm_total += 1
            if t.replace("AMM", "").strip() not in text:
                invented_amm += 1
                if len(examples) < 3:
                    examples.append((r["id"], t))
        structured = mapper.part_from_structured(str(row["PartName"]))
        if structured and structured not in ("HYDRAULIC_PUMP_UNSPECIFIED", "HYDRAULIC_SYSTEM"):
            if structured in faulty:
                agree += 1
            else:
                disagree += 1
        if structured == "HYDRAULIC_PUMP_UNSPECIFIED":
            spec = [p for p in PUMPS if p in faulty]
            pump_llm[spec[0] if len(spec) == 1 else ("PLUSIEURS" if spec else "AUCUNE_PRECISE")] += 1

    L = [f"# Étape 2 — Extraction par LLM ({model})", "",
         f"- Rapports traités : **{n}**",
         f"- Temps moyen par rapport : **{sum(secs) / len(secs):.1f} s**" if secs else "",
         f"- Sorties JSON invalides : **{invalid}**",
         f"- Types de pièces inventés (hors liste fermée) : **{sum(invented_types.values())}** "
         + (f"({', '.join(f'`{k}` ×{v}' for k, v in invented_types.most_common(6))})" if invented_types else ""),
         f"- Tâches AMM citées par le LLM mais absentes du texte : **{invented_amm} / {amm_total}** "
         + (f"(ex. {', '.join(f'`{t}` dans {i}' for i, t in examples)})" if examples else ""),
         f"- Accord avec le champ structuré (quand il est précis) : **{agree} / {agree + disagree}**",
         "", "## Les rapports « PUMP » : quelle pompe est en panne selon le LLM ?", "",
         "| Réponse du LLM | Rapports |", "| --- | ---: |"]
    L += [f"| {k} | {v} |" for k, v in pump_llm.most_common()]
    L += [""]
    L += compare_reference(df, mapper, recs)
    return "\n".join(x for x in L if x is not None)


def to_label(pumps: list[str]) -> str:
    pumps = [p for p in PUMPS if p in pumps]
    if not pumps:
        return "NO_PUMP_FAILED"
    return pumps[0] if len(pumps) == 1 else "SEVERAL"


def compare_reference(df, mapper, recs) -> list[str]:
    """Compare dictionnaire et LLM à la référence data/ground_truth.xlsx."""
    path = ROOT / "data" / "ground_truth.xlsx"
    if not path.exists():
        return ["(Pas de référence : data/ground_truth.xlsx absent.)"]
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    ref = {r[0]: (r[4], r[6], r[7] if len(r) > 7 else "") for r in rows if r[0] and r[4]}
    annot = {v[2] for v in ref.values() if v[2]}
    texts = df.set_index("OperatorControlNumber")["Discrepancy"]
    llm_by_id = {}
    for r in recs:
        try:
            llm_by_id[r["id"]] = to_label(as_list(json.loads(r["raw"]).get("faulty_parts")))
        except Exception:  # noqa: BLE001
            llm_by_id[r["id"]] = "INVALID"
    L = ["## Comparaison à la référence (20 rapports « PUMP »)", "",
         f"Référence : `data/ground_truth.xlsx` — annotateur : {', '.join(annot) or '?'}.", "",
         "| Rapport | Référence | Dictionnaire | LLM |", "| --- | --- | --- | --- |"]
    ok_d = ok_l = n_d = n_l = 0
    for rid, (gold, _comment, _a) in ref.items():
        if rid not in texts.index:
            continue
        dico = to_label([m.canonical for m in mapper.parts.find(str(texts[rid]))])
        llm = llm_by_id.get(rid, "—")
        scored = gold != "CANNOT_TELL"
        if scored:
            n_d += 1
            ok_d += dico == gold
            if llm != "—":
                n_l += 1
                ok_l += llm == gold
        mark = lambda x: f"**{x}**" if scored and x == gold else x  # noqa: E731
        L.append(f"| `{rid}` | {gold} | {mark(dico)} | {mark(llm)} |")
    L += ["", f"- Dictionnaire : **{ok_d} / {n_d}** conformes à la référence.",
          f"- LLM : **{ok_l} / {n_l}** conformes (sur les rapports déjà traités par le LLM)." if n_l
          else "- LLM : aucun de ces rapports n'a encore été traité (lancer `--only-pump`).",
          "- `CANNOT_TELL` dans la référence = non compté.",
          "- Limite : la référence est un LLM (Claude), pas un expert maintenance. "
          "Dans un vrai projet, un échantillon serait validé par les mécaniciens.", ""]
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="llama3.2:3b")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--mock", action="store_true", help="tester sans Ollama")
    ap.add_argument("--only-pump", action="store_true",
                    help="seulement les 117 rapports dont le champ structuré dit « PUMP »")
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
            sys.exit(f"Ollama ne répond pas sur {args.host}. Lance l'application Ollama "
                     f"(ou `ollama serve`), puis `ollama pull {args.model}`.")
    if not args.evaluate_only:
        extract(args, df, mapper, path)
    report = evaluate(df, mapper, path, "dictionnaire (mock)" if args.mock else args.model)
    (OUT / f"etape2_rapport_{tag}.md").write_text(report, encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    main()
