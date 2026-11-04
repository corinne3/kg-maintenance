"""The pivot format: a "fact" = a triple + its provenance.

Everything else (NetworkX graph, Neo4j export, RDF export) is built from
this list of facts. That is what makes the stack reusable from one domain
to another: only the "raw data -> facts" step changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    type: str       # e.g. PartType
    key: str        # stable identifier, e.g. ENGINE_DRIVEN_PUMP
    label: str = "" # readable label

    @property
    def id(self) -> str:
        return f"{self.type}:{self.key}"


@dataclass
class Fact:
    subject: Node
    relation: str
    object: Node
    source: str            # structured | dictionary | llm
    record_id: str         # report the fact comes from (provenance)
    evidence: str = ""     # text that supports the fact
    attrs: dict = field(default_factory=dict)
