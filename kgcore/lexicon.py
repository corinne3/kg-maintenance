"""Label-based entity linking against a reference vocabulary (e.g. ESCO).

Generic: a LabelIndex maps normalised labels (preferred + alternative, any
language) to concept ids. A lookup returns every concept that carries the
label, so ambiguity is visible instead of silently resolved.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFKC", str(text)).casefold()
    t = t.replace("’", "'")
    t = re.sub(r"[\s_]+", " ", t)
    return t.strip(" .;,")


def gendered_variants(label: str) -> list[str]:
    """French gendered labels: 'ingénieur/ingénieure de données'.

    Returns the full label plus each readable form:
    'ingénieure de données' and the rebuilt masculine 'ingénieur de données'.
    """
    out = [label]
    if "/" not in label:
        return out
    left, right = label.split("/", 1)
    left, right = left.strip(), right.strip()
    out += [left, right]
    if len(left.split()) == 1 and len(right.split()) > 1:
        out.append(left + " " + " ".join(right.split()[1:]))
    return out


@dataclass
class Match:
    query: str
    ids: set
    how: str          # exact | fuzzy | none

    @property
    def status(self) -> str:
        if not self.ids:
            return "unresolved"
        return "ambiguous" if len(self.ids) > 1 else "resolved"


class LabelIndex:
    def __init__(self):
        self.by_label: dict[str, set] = defaultdict(set)

    def add(self, concept_id: str, label: str):
        if not isinstance(label, str) or not label.strip():
            return
        for v in gendered_variants(label):
            n = normalise(v)
            if n:
                self.by_label[n].add(concept_id)

    def add_many(self, concept_id: str, labels: str):
        """ESCO stores alternative labels one per line."""
        if isinstance(labels, str):
            for lab in labels.split("\n"):
                self.add(concept_id, lab)

    def lookup(self, text: str, fuzzy_cutoff: float | None = None) -> Match:
        n = normalise(text)
        if n in self.by_label:
            return Match(text, set(self.by_label[n]), "exact")
        if fuzzy_cutoff:
            close = difflib.get_close_matches(n, self.by_label.keys(), n=1, cutoff=fuzzy_cutoff)
            if close:
                return Match(text, set(self.by_label[close[0]]), "fuzzy")
        return Match(text, set(), "none")

    def ambiguous_labels(self) -> dict[str, set]:
        return {k: v for k, v in self.by_label.items() if len(v) > 1}
