"""Loading a domain: config + data filtered on its scope."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_domain(name: str) -> dict:
    path = ROOT / "domains" / name / "config.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_records(cfg: dict) -> pd.DataFrame:
    src = cfg["source"]
    df = pd.read_csv(ROOT / src["file"], encoding=src.get("encoding", "utf-8"),
                     low_memory=False, dtype=str)
    flt = cfg.get("filter")
    if flt:
        df = df[df[flt["column"]].fillna("").str.startswith(flt["startswith"])]
    df = df.drop_duplicates(subset=[src["id_column"]])
    return df.reset_index(drop=True)
