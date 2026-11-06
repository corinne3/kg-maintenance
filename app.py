"""Knowledge graph assistant.

Tab 1: compare classic RAG, naive GraphRAG and schema-guided GraphRAG (maintenance).
Tab 2: free exploration of the whole graph (maintenance + HR): search any node, walk from neighbour to neighbour.
Tab 3: an agent that chooses its tools over the maintenance and HR graphs, with guardrails.

    pip install streamlit scikit-learn
    streamlit run app.py

Ollama must be running (llama3.2:3b) to generate answers or to route with the LLM.
Without it, tab 1 still shows the contexts, and tab 2 works in "rules" mode.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from assistant.agent import Agent, ollama  # noqa: E402
from assistant.explore import ego_view, full_graph, neighbours, render_html, search  # noqa: E402
from assistant.retrieval import PROMPT, KnowledgeBase  # noqa: E402
from assistant.tools import build_tools  # noqa: E402

EXAMPLES = [
    "What problems affect engine-driven pumps on the A320 family?",
    "Which maintenance manual tasks are cited for electric motor pump leaks?",
    "Which operators report the most PTU problems?",
    "What happens when a hydraulic reservoir overheats?",
]
AGENT_EXAMPLES = [
    "Who can work on engine-driven pumps on the A320 family, and how many incidents are there?",
    "Are there people certified for electric motor pumps on the 737?",
    "How many reservoir overheat events are there?",
    "What internal move would suit employee E002?",
    "What internal move would suit employee E120?",
    "What is the average salary band of the team managed by E095?",
    "What is the weather in Toulouse tomorrow?",
]

st.set_page_config(page_title="Knowledge graph assistant", layout="wide")


@st.cache_resource(show_spinner="Building the maintenance graph…")
def get_kb(use_hierarchy: bool) -> KnowledgeBase:
    return KnowledgeBase(use_hierarchy=use_hierarchy)


@st.cache_resource(show_spinner="Building the HR graph (ESCO)…")
def get_hr():
    if not (ROOT / "data" / "esco" / "en").exists():
        return None
    from assistant.hr_kb import HRBase
    return HRBase()


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


st.title("Where enterprise knowledge graphs break")
st.caption("Maintenance: FAA Service Difficulty Reports 2025, ATA 29, 514 reports. HR: ESCO taxonomy + a "
           "synthetic company. Compare retrieval methods, or let an agent choose its tools.")

with st.sidebar:
    st.header("Settings")
    model = st.text_input("Ollama model", "llama3.2:3b")
    use_hierarchy = st.checkbox("Use the model hierarchy (A320 family = A319 + A320 + A321)", value=True)
    st.divider()
    st.markdown("Code and data: see the README. Answers come from a 3-billion-parameter "
                "model running locally; they can be wrong.")

kb = get_kb(use_hierarchy)
tab_compare, tab_explore, tab_agent = st.tabs(
    ["Compare retrieval (maintenance)", "Explore the graph", "Agent (maintenance + HR)"])

# ---------------------------------------------------------------- tab 1
with tab_compare:
    generate = st.checkbox("Generate answers with the LLM", value=False,
                           help="About 30–60 s per answer on a laptop CPU. "
                                "Leave unchecked to compare the contexts only.")
    hops = st.slider("Naive GraphRAG: number of hops", 1, 3, 2)
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

# ---------------------------------------------------------------- tab 2 (written before the agent tab,
# because the agent tab may call st.stop())
@st.cache_resource(show_spinner="Merging the maintenance and HR graphs…")
def get_full_graph(use_hierarchy: bool):
    return full_graph(get_kb(use_hierarchy), get_hr())


with tab_explore:
    g = get_full_graph(use_hierarchy)
    ss = st.session_state
    ss.setdefault("center", "PartType:ENGINE_DRIVEN_PUMP")
    ss.setdefault("history", [])

    def go(node: str):
        if node != ss.center:
            ss.history.append(ss.center)
            ss.center = node

    st.caption(f"The whole graph: {g.number_of_nodes():,} nodes, {g.number_of_edges():,} edges "
               "(FAA maintenance + synthetic HR on ESCO). Salary bands and long absences are not shown: "
               "they are sensitive and stay behind the agent's access rules.")
    s1, s2 = st.columns([2, 3])
    found = search(g, s1.text_input("Search a node (part, condition, operator, aircraft model, "
                                    "report number, employee, skill, job…)", placeholder="e.g. PTU, LEAKING, A320, E161, Excel"))
    if found:
        pick = s2.selectbox(f"{len(found)} match{'es' if len(found) > 1 else ''}", found, format_func=lambda x: x[1])
        if s2.button("Show this node"):
            go(pick[0])
            st.rerun()

    center = ss.center
    rels = sorted({d["relation"] for _, _, d in g.edges(data=True)})
    c1, c2, c3, c4 = st.columns([1, 1, 3, 1])
    depth = c1.radio("Hops", [1, 2], horizontal=True)
    max_nodes = c2.slider("Max nodes", 30, 400, 200, step=10)
    keep = c3.multiselect("Relations to follow (empty = all)", rels)
    if c4.button("← Back", disabled=not ss.history):
        ss.center = ss.history.pop()
        st.rerun()

    view = ego_view(g, center, depth, set(keep) or None, max_nodes)
    d = g.nodes[center]
    deg = view["by_hop"].get(1, 0)
    st.subheader(f"{d.get('label', center)}  ·  {d['type']}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Direct neighbours", deg)
    m2.metric(f"Nodes within {depth} hop{'s' if depth > 1 else ''}", view["reached"])
    m3.metric("Share of the whole graph", f"{100 * view['reached'] / g.number_of_nodes():.0f}%")
    if view["shown"] < view["reached"]:
        st.warning(f"Only the {view['shown']} closest and most connected nodes are drawn, out of {view['reached']}.")
    if deg >= 50:
        st.info("This node is a hub: a naive GraphRAG traversal that goes through it pulls in a large part "
                "of the graph. Try filtering the relations to follow.")
    components.html(render_html(view, 560), height=600, scrolling=False)

    st.markdown("**Relations of this node** · click a row to move to that neighbour")
    rows = neighbours(g, center, hr.today if (hr := get_hr()) else "")
    if keep:
        rows = [r for r in rows if r["relation"] in keep]
    if rows:
        event = st.dataframe([{k: v for k, v in r.items() if k != "id"} for r in rows], hide_index=True,
                             use_container_width=True, on_select="rerun", selection_mode="single-row",
                             key=f"nb_{center}")
        if event.selection.rows:
            go(rows[event.selection.rows[0]]["id"])
            st.rerun()
    else:
        st.caption("No relation with the current filter.")

# ---------------------------------------------------------------- tab 3
with tab_agent:
    hr = get_hr()
    if hr is None:
        st.info("HR tools are off: put the ESCO CSV files in data/esco/en and data/esco/fr to enable them.")
    agent = Agent(kb, build_tools(kb, hr), ollama(model))
    c1, c2 = st.columns(2)
    role = c1.selectbox("Who is asking? (access rights)", ["employee", "manager", "hr"])
    mode = c2.selectbox("Routing", ["hybrid", "rules", "llm"],
                        help="rules: no LLM. llm: the LLM picks the tools. "
                             "hybrid: rules first, the LLM only when no rule applies.")
    picked = st.selectbox("Example questions", AGENT_EXAMPLES, key="agent_example")
    aq = st.text_input("Question for the agent (in English)", value=picked, key="agent_question")
    write = st.checkbox("Let the LLM write the final answer from the tool results", value=False)
    if st.button("Run the agent", type="primary") and aq:
        with st.spinner("The agent is working…"):
            try:
                r = agent.run(aq, role=role, mode=mode, answer=write)
            except Exception as e:  # noqa: BLE001
                st.error(f"The agent failed: {e}. If the routing uses the LLM, is Ollama running?")
                st.stop()
        badge = {"answered": "Answered", "refused": "Refused: access rights or privacy rule",
                 "escalated": "Escalated to a person"}[r.outcome]
        st.subheader(badge)
        st.markdown("**Decision trace**")
        st.table([{"step": s.what, "by": s.by or "-", "detail": s.detail, "seconds": s.seconds} for s in r.trace])
        st.markdown("**Answer**" if write and r.outcome == "answered" else "**Tool results**")
        st.code(r.answer or "(nothing)", language="text")
        st.caption("Every tool call is checked against the ontology (allowed values), the role's access rights "
                   "and the privacy rule (no aggregate under 5 people) before it runs.")
