"""Raw data quality summary and the data dictionary reader for the Data and Cleaning page."""
from pathlib import Path

import pandas as pd

from core.data import SECTOR_FIX

DOCS = Path(__file__).resolve().parent.parent / "docs"
ALLOWED_SECTORS = set(SECTOR_FIX.values())


def quality_summary(raw: pd.DataFrame) -> dict:
    """Count the problems in the raw invoice file before any cleaning."""
    missing = raw.isna().sum()
    missing = missing[missing > 0].rename("missing_rows").to_frame()
    missing["missing_pct"] = (missing["missing_rows"] / len(raw) * 100).round(1)

    labels = raw["sector"].astype(str)
    variants = (labels[~labels.isin(ALLOWED_SECTORS)].value_counts()
                .rename_axis("raw_label").rename("rows").reset_index())
    variants["raw_label"] = "'" + variants["raw_label"] + "'"
    return dict(rows=len(raw), columns=raw.shape[1], duplicate_rows=int(raw.duplicated().sum()),
                missing=missing.rename_axis("column").reset_index(), sector_variants=variants)


def read_dictionary(section: str = "invoices.csv") -> pd.DataFrame:
    """Parse one table from docs/DATA_DICTIONARY.md into a dataframe."""
    lines = (DOCS / "DATA_DICTIONARY.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## ") and section in line)
    table = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.startswith("|"):
            table.append([cell.strip().strip("`") for cell in line.strip("|").split("|")])
        elif table:
            break
    header, rows = table[0], [row for row in table[2:] if len(row) == len(table[0])]
    return pd.DataFrame(rows, columns=header)
