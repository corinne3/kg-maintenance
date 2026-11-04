"""Entity resolution : ramener des écritures différentes à une même entité.

Générique : les variantes et les entités canoniques viennent du config.yaml
du domaine. Ce module ne sait rien de l'aviation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Mention:
    canonical: str      # type canonique, ex. ENGINE_DRIVEN_PUMP
    surface: str        # texte tel qu'écrit, ex. "EDP"
    start: int
    end: int


class AliasResolver:
    """Trouve les mentions d'entités dans un texte à partir d'un dictionnaire.

    Règle clé : les types sont testés dans l'ordre du config. Un passage de
    texte déjà reconnu par un type précis (ex. "ELECTRIC PUMP") ne peut plus
    être reconnu par un type générique (ex. "PUMP"). C'est ce qui évite de
    compter deux fois la même pièce.
    """

    def __init__(self, types_config: dict):
        self.types = []
        for canonical, spec in types_config.items():
            patterns = [re.compile(p) for p in spec.get("aliases", [])]
            self.types.append((canonical, spec.get("label", canonical), patterns))
        self.labels = {c: lab for c, lab, _ in self.types}

    def find(self, text: str) -> list[Mention]:
        text = (text or "").upper()
        taken: list[tuple[int, int]] = []
        found: list[Mention] = []
        for canonical, _label, patterns in self.types:
            for pat in patterns:
                for m in pat.finditer(text):
                    s, e = m.span()
                    if any(s < te and ts < e for ts, te in taken):
                        continue  # déjà reconnu par un type plus précis
                    taken.append((s, e))
                    found.append(Mention(canonical, m.group(0).strip(), s, e))
        return found

    def resolve_value(self, value: str) -> str | None:
        """Pour un champ structuré court (ex. PartName = "HOSE")."""
        mentions = self.find(value)
        return mentions[0].canonical if mentions else None


def resolve_by_patterns(value: str, rules: list[dict]) -> str | None:
    """Règles du type {pattern, family} : 'A320232' -> 'A320'."""
    v = (value or "").upper().strip()
    for rule in rules:
        m = re.match(rule["pattern"], v)
        if m:
            return rule["family"].format(*m.groups())
    return None
