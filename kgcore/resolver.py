"""Entity resolution: map different spellings to the same entity.

Generic: aliases and canonical entities come from the domain config.yaml.
This module knows nothing about aviation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Mention:
    canonical: str      # canonical type, e.g. ENGINE_DRIVEN_PUMP
    surface: str        # text as written, e.g. "EDP"
    start: int
    end: int


class AliasResolver:
    """Finds entity mentions in a text using an alias dictionary.

    Key rule: types are tried in config order. A span already matched by a
    specific type (e.g. "ELECTRIC PUMP") cannot be matched again by a generic
    type (e.g. "PUMP"). This avoids counting the same part twice.
    """

    def __init__(self, types_config: dict):
        self.types = []
        for canonical, spec in types_config.items():
            patterns = [re.compile(p) for p in spec.get("aliases", [])]
            self.types.append((canonical, spec.get("label_en", spec.get("label", canonical)), patterns))
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
                        continue  # already matched by a more specific type
                    taken.append((s, e))
                    found.append(Mention(canonical, m.group(0).strip(), s, e))
        return found

    def resolve_value(self, value: str) -> str | None:
        """For a short structured field (e.g. PartName = "HOSE")."""
        mentions = self.find(value)
        return mentions[0].canonical if mentions else None


def resolve_by_patterns(value: str, rules: list[dict]) -> str | None:
    """Rules like {pattern, family}: 'A320232' -> 'A320'."""
    v = (value or "").upper().strip()
    for rule in rules:
        m = re.match(rule["pattern"], v)
        if m:
            return rule["family"].format(*m.groups())
    return None
