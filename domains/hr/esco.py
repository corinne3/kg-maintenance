"""Load the part of ESCO the HR domain needs, in English and French."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from kgcore.lexicon import LabelIndex

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Esco:
    occ: pd.DataFrame                      # uri, label_en, label_fr, alt_en, alt_fr
    skills: pd.DataFrame                   # uri, label_en, label_fr, alt_en, alt_fr
    essential: dict = field(default_factory=dict)   # occupation uri -> list of skill uris
    transversal: set = field(default_factory=set)
    occ_index: LabelIndex = field(default_factory=LabelIndex)
    skill_index: LabelIndex = field(default_factory=LabelIndex)
    full_occ_index: LabelIndex = field(default_factory=LabelIndex)
    all_occ_labels: dict = field(default_factory=dict)   # every ESCO occupation uri -> English label


def _read(lang: str, name: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / "data" / "esco" / lang / f"{name}_{lang}.csv", dtype=str)


def load(cfg: dict) -> Esco:
    oe, of = _read("en", "occupations"), _read("fr", "occupations")
    se, sf = _read("en", "skills"), _read("fr", "skills")
    rel = _read("en", "occupationSkillRelations")
    tr = _read("en", "transversalSkillsCollection")

    occ = oe[["conceptUri", "preferredLabel", "altLabels"]].merge(
        of[["conceptUri", "preferredLabel", "altLabels"]], on="conceptUri", suffixes=("_en", "_fr"))
    occ.columns = ["uri", "label_en", "alt_en", "label_fr", "alt_fr"]
    wanted = {k.lower() for k in cfg["occupations"]}
    sel = occ[occ.label_en.str.lower().isin(wanted)].copy()

    essential = {}
    for uri in sel.uri:
        r = rel[(rel.occupationUri == uri) & (rel.relationType == "essential")]
        essential[uri] = list(r.skillUri)
    needed = {s for v in essential.values() for s in v}

    sk = se[["conceptUri", "preferredLabel", "altLabels"]].merge(
        sf[["conceptUri", "preferredLabel", "altLabels"]], on="conceptUri", suffixes=("_en", "_fr"))
    sk.columns = ["uri", "label_en", "alt_en", "label_fr", "alt_fr"]

    e = Esco(occ=sel.reset_index(drop=True), skills=sk[sk.uri.isin(needed)].reset_index(drop=True),
             essential=essential, transversal=set(tr["conceptUri"]),
             all_occ_labels=dict(zip(occ.uri, occ.label_en)))
    # Occupation index: the WHOLE of ESCO, as a real HR system would use it.
    for _, r in occ.iterrows():
        for lab, alt in ((r.label_en, r.alt_en), (r.label_fr, r.alt_fr)):
            e.full_occ_index.add(r.uri, lab)
            e.full_occ_index.add_many(r.uri, alt)
    for _, r in sel.iterrows():
        for lab, alt in ((r.label_en, r.alt_en), (r.label_fr, r.alt_fr)):
            e.occ_index.add(r.uri, lab)
            e.occ_index.add_many(r.uri, alt)
    # Skill index: the whole skills pillar (13,960 skills).
    for _, r in sk.iterrows():
        for lab, alt in ((r.label_en, r.alt_en), (r.label_fr, r.alt_fr)):
            e.skill_index.add(r.uri, lab)
            e.skill_index.add_many(r.uri, alt)
    return e
