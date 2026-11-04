"""Maintenance assistant: compare classic RAG, naive GraphRAG and schema-guided GraphRAG.

    pip install streamlit scikit-learn
    streamlit run app.py

Ollama must be running (llama3.2:3b) to generate answers. Without it, the app
still shows the three contexts side by side.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from assistant.retrieval import PROMPT, KnowledgeBase  # noqa: E402

EXAMPLES = [
    "What problems affect engine-driven pumps on the A320 family?",
    "Which maintenance manual tasks are cited for electric motor pump leaks?",
    "Which operators report the most PTU problems?",
    "What happens when a hydraulic reservoir overheats?",
]

st.set_page_config(page_title="Maintenance KG assistant", layout="wide")


@st.cache_resource(show_spinner="Building the knowledge graph…")
def get_kb(use_hierarchy: bool) -> KnowledgeBase:
    return KnowledgeBase(use_hierarchy=use_hierarchy)


def ask_ollama(model: str, prompt: str, host: str = "http://localhost:11434") -> tuple[str, float]:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "stream": False, "keep_alive": "60m",
                       "options": {"temperature": 0, "num_ctx": 4096}}).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as resp:
        answer = json.loads(resp.read())["message"]["content"]
    return answer, time.time() - t0


st.title("Where maintenance knowledge graphs break")
st.caption("FAA Service Difficulty Reports 2025, ATA 29 hydraulic power, 514 reports. "
           "The same question, answered from three different contexts.")

with st.sidebar:
    st.header("Settings")
    model = st.text_input("Ollama model", "llama3.2:3b")
    generate = st.checkbox("Generate answers with the LLM", value=False,
                           help="About 30–60 s per answer on a laptop CPU. "
                                "Leave unchecked to compare the contexts only.")
    use_hierarchy = st.checkbox("Use the model hierarchy (A320 family = A319 + A320 + A321)", value=True)
    hops = st.slider("Naive GraphRAG: number of hops", 1, 3, 2)
    st.divider()
    st.markdown("Code and data: see the README. Answers come from a 3-billion-parameter "
                "model running locally; they can be wrong.")

kb = get_kb(use_hierarchy)

example = st.selectbox("Example questions", EXAMPLES)
question = st.text_input("Your question (in English)", value=example)

if question:
    linked = kb.link(question)
    st.markdown("**Entities found in the question:** "
                + (", ".join(f"`{kb.mapper.parts.labels[p]}`" for p in linked["parts"]) or "no part type")
                + (" · families " + ", ".join(f"`{f}`" for f in linked["families"]) if linked["families"] else "")
                + (" · conditions " + ", ".join(f"`{c}`" for c in linked["conditions"]) if linked["conditions"] else ""))

    contexts = [kb.text_rag(question), kb.naive_graph(question, hops), kb.guided_graph(question)]
    cols = st.columns(3)
    for col, ctx in zip(cols, contexts):
        with col:
            st.subheader(ctx.method)
            m1, m2 = st.columns(2)
            m1.metric("Context size", f"{ctx.chars:,} chars")
            m2.metric("Source reports", len(ctx.sources))
            if ctx.truncated:
                st.warning("Context cut to fit the model: the rest of the graph was dropped.")
            if generate:
                with st.spinner("The LLM is answering…"):
                    try:
                        answer, secs = ask_ollama(model, PROMPT.format(context=ctx.text, question=question))
                        st.markdown(answer)
                        st.caption(f"{secs:.0f} s with {model}")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Ollama did not answer: {e}. Is it running?")
            with st.expander("Context given to the LLM"):
                st.code(ctx.text or "(empty)", language="text")
            if ctx.sources:
                with st.expander(f"Source reports ({len(ctx.sources)})"):
                    for rid in ctx.sources[:12]:
                        st.markdown(f"**{rid}** — {kb._snippet(rid, 400)}")
                    if len(ctx.sources) > 12:
                        st.caption(f"… and {len(ctx.sources) - 12} more")

    st.divider()
    st.markdown(
        "**How to read this.** *Classic RAG* finds texts that look like the question, but it "
        "cannot count or aggregate. *Naive GraphRAG* takes everything around the entities: the "
        "context overflows and gets cut. *Schema-guided GraphRAG* follows the ontology "
        "(part ← report → condition / manual task / aircraft) and gives the LLM aggregates "
        "plus a few sources. It is only as good as entity linking: switch off the model "
        "hierarchy to see the A320 family answer lose half its reports.")
