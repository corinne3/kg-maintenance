"""Three ways to build the context an LLM answers from.

1. text_rag      : classic RAG. Retrieve the most similar report texts (TF-IDF).
2. naive_graph   : naive GraphRAG. Link entities in the question, take everything
                   within N hops in the graph, serialise it as triples.
3. guided_graph  : schema-guided GraphRAG. Link entities, then follow the ontology
                   (part <- report -> condition / AMM task / aircraft) and return
                   aggregates plus a few source reports.

Each function returns a Context: the text given to the LLM, the source report ids,
and what was linked. No LLM is needed to compare the three contexts.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from domains.maintenance_aviation.mapping import MaintenanceMapper
from kgcore.graph import build_graph, neighborhood
from kgcore.loader import load_domain, load_records

MAX_CHARS = 6000          # context budget given to the LLM (~1,500 tokens)

CONDITION_WORDS = {       # question word -> PartCondition value
    "LEAK": "LEAKING", "CRACK": "CRACKED", "CORRO": "CORRODED", "FAIL": "FAILED",
    "FAULT": "FAULTED", "INOP": "INOPERATIVE", "DAMAG": "DAMAGED", "OVERHEAT": "OVERHEATED",
}


@dataclass
class Context:
    method: str
    text: str
    sources: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)
    nodes: int = 0
    truncated: bool = False

    @property
    def chars(self) -> int:
        return len(self.text)


class KnowledgeBase:
    def __init__(self, use_hierarchy: bool = True):
        self.use_hierarchy = use_hierarchy
        self.cfg = load_domain("maintenance_aviation")
        self.df = load_records(self.cfg)
        self.mapper = MaintenanceMapper(self.cfg)
        self.facts = [f for _, row in self.df.iterrows() for f in self.mapper.facts(row)]
        self.g = build_graph(self.facts)
        self.und = nx.Graph(self.g)
        self.ids = list(self.df["OperatorControlNumber"])
        self.texts = dict(zip(self.ids, self.df["Discrepancy"].fillna("").astype(str)))
        self.tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        self.matrix = self.tfidf.fit_transform([self.texts[i] for i in self.ids])
        self.families = {d["key"] for _, d in self.g.nodes(data=True) if d["type"] == "AircraftModel"}

    # ------------------------------------------------------------ entity linking
    def link(self, question: str) -> dict:
        q = question.upper()
        parts = list(dict.fromkeys(m.canonical for m in self.mapper.parts.find(q)))
        fams = []
        for group, members in self.cfg.get("model_groups", {}).items():
            if group in q and self.use_hierarchy:
                fams += [str(m) for m in members if str(m) in self.families]
                q = q.replace(group, " ")
        fams += [f for f in self.families if re.search(rf"\b{re.escape(f.upper())}\b", q)]
        fams = list(dict.fromkeys(fams))
        conds = [v for k, v in CONDITION_WORDS.items() if k in q]
        return {"parts": parts, "families": fams, "conditions": conds}

    def _snippet(self, rid: str, n: int = 260) -> str:
        t = re.sub(r"\s+", " ", self.texts[rid]).strip()
        return t[:n] + ("…" if len(t) > n else "")

    # ------------------------------------------------------------ 1. classic RAG
    def text_rag(self, question: str, k: int = 8) -> Context:
        sims = cosine_similarity(self.tfidf.transform([question]), self.matrix)[0]
        top = [self.ids[i] for i in sims.argsort()[::-1][:k] if sims[i] > 0]
        lines = [f"[{rid}] {self._snippet(rid, 600)}" for rid in top]
        return Context("Classic RAG (text similarity)", "\n".join(lines), top, [], len(top))

    # ------------------------------------------------------------ 2. naive GraphRAG
    def naive_graph(self, question: str, hops: int = 2) -> Context:
        linked = self.link(question)
        starts = [f"PartType:{p}" for p in linked["parts"]] + \
                 [f"AircraftModel:{f}" for f in linked["families"]]
        starts = [s for s in starts if s in self.g]
        if not starts:
            return Context("Naive GraphRAG (N hops)", "No entity from the question found in the graph.", [], [])
        nodes = set()
        for s in starts:
            nodes |= neighborhood(self.g, s, hops)
        sub = self.g.subgraph(nodes)
        lines = []
        for u, v, d in sub.edges(data=True):
            lines.append(f"{self.g.nodes[u]['label']} {d['relation']} {self.g.nodes[v]['label']}")
        lines = sorted(set(lines))
        text = "\n".join(lines)
        truncated = len(text) > MAX_CHARS
        sources = sorted(n.split(":", 1)[1] for n in nodes if n.startswith("Report:"))
        return Context("Naive GraphRAG (N hops)", text[:MAX_CHARS], sources,
                       [self.g.nodes[s]["label"] for s in starts], len(nodes), truncated)

    # ------------------------------------------------------------ 3. guided GraphRAG
    def guided_graph(self, question: str, k: int = 8) -> Context:
        linked = self.link(question)
        if not linked["parts"]:
            return Context("Schema-guided GraphRAG", "No part type from the question found in the ontology.", [], [])
        return self.guided_query(linked["parts"][0], linked["families"], linked["conditions"], k)

    def guided_query(self, part: str, families: list[str], conditions: list[str], k: int = 8) -> Context:
        """The ontology path part <- report -> condition / manual task / aircraft, with filters."""
        linked = {"parts": [part], "families": list(families), "conditions": list(conditions)}
        pnode = f"PartType:{part}"
        reports = {u for u, _, d in self.g.in_edges(pnode, data=True) if d["relation"] == "INVOLVES_PART"}

        def out(rnode, rel):
            return [v for _, v, d in self.g.out_edges(rnode, data=True) if d["relation"] == rel]

        def family(rnode):
            fams = []
            for a in out(rnode, "CONCERNS"):
                fams += [self.g.nodes[m]["key"] for m in out(a, "IS_MODEL")]
            return fams

        if linked["families"]:
            reports = {r for r in reports if set(family(r)) & set(linked["families"])}
        relaxed = ""
        if linked["conditions"]:
            strict = {r for r in reports
                      if {self.g.nodes[c]["key"] for c in out(r, "HAS_CONDITION")} & set(linked["conditions"])}
            if strict:
                reports = strict
            else:
                # The condition is often only in the free text, not in PartCondition.
                words = [w[:5] for w in linked["conditions"]]
                reports_text = {r for r in reports
                                if any(w in self.texts[r.split(":", 1)[1]].upper() for w in words)}
                relaxed = (f"No report has PartCondition = {', '.join(linked['conditions'])} for this part. "
                           f"Filter relaxed to the free text: {len(reports_text)} reports mention it.")
                reports = reports_text
                linked["conditions"] = []
        conds, amm, fams, ops = Counter(), Counter(), Counter(), Counter()
        for r in sorted(reports):  # sorted: same output on every run
            conds.update(self.g.nodes[c]["label"] for c in out(r, "HAS_CONDITION"))
            amm.update(self.g.nodes[a]["label"] for a in out(r, "REFERENCES"))
            fams.update(family(r))
            ops.update(self.g.nodes[o]["label"] for o in out(r, "REPORTED_BY"))
        # show reports with the reported condition first, then by date order in the file
        ordered = sorted(reports, key=lambda r: self.ids.index(r.split(":", 1)[1]))
        sample = [r.split(":", 1)[1] for r in ordered[:k]]
        label = self.mapper.parts.labels[part]
        filt = []
        if linked["families"]:
            filt.append("aircraft family " + ", ".join(linked["families"]))
        if linked["conditions"]:
            filt.append("condition " + ", ".join(linked["conditions"]))
        top = lambda c: ", ".join(f"{k} ({v})" for k, v in c.most_common(6)) or "none"  # noqa: E731
        lines = [
            f"Query: Report -INVOLVES_PART-> {label}" + (f", filtered on {'; '.join(filt)}" if filt else ""),
            *([relaxed] if relaxed else []),
            f"Matching reports: {len(reports)}",
            f"Conditions reported: {top(conds)}",
            f"Maintenance manual tasks cited: {top(amm)}",
            f"Aircraft families: {top(fams)}",
            f"Operators: {top(ops)}",
            "Source reports:",
        ] + [f"[{rid}] {self._snippet(rid)}" for rid in sample]
        return Context("Schema-guided GraphRAG", "\n".join(lines)[:MAX_CHARS], sample,
                       [label] + linked["families"] + linked["conditions"], len(reports) + 4)


PROMPT = """You answer questions about aircraft hydraulic maintenance reports (FAA, 2025).
Use ONLY the context below. If the context is not enough, say so.
Cite report ids in square brackets when you use them. Answer in 5 sentences at most.

Context:
{context}

Question: {question}
Answer:"""
