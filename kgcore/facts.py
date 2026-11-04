"""Le format pivot : un « fait » = un triplet + sa provenance.

Tout le reste (graphe NetworkX, export Neo4j, export RDF) est construit
à partir de cette liste de faits. C'est ce qui rend la stack réutilisable
d'un domaine à l'autre : seul le passage « donnée brute -> faits » change.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    type: str       # ex. PartType
    key: str        # identifiant stable, ex. ENGINE_DRIVEN_PUMP
    label: str = "" # libellé lisible

    @property
    def id(self) -> str:
        return f"{self.type}:{self.key}"


@dataclass
class Fact:
    subject: Node
    relation: str
    object: Node
    source: str            # structured | dictionary | llm
    record_id: str         # rapport d'où vient le fait (provenance)
    evidence: str = ""     # texte qui justifie le fait
    attrs: dict = field(default_factory=dict)
