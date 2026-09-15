"""Shared data-loading helpers for the EU Cities dashboard.

Keeps file discovery and lat/lon enrichment in one place so every page
(current and future) reads project data the same way.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

RAW_COLUMNS = ["Name", "License number", "Address of tobacco product sales point (location)", "Start of validity", "End of validity"]
CSV_COLUMNS = ["Name", "License Number", "Address", "Start of Validity", "End of Validity", "Latitude", "Longitude"]


def discover_files():
    """Return every .csv/.xlsx under data/, newest-looking (geocoded csv) first."""
    files = []
    if not DATA_DIR.exists():
        return files
    for path in sorted(DATA_DIR.rglob("*")):
        if path.suffix.lower() in (".csv", ".xlsx") and path.is_file():
            files.append(path)
    return files


def load_cache_for(path: Path):
    cache_path = path.parent / "geocode_cache.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return {}


def load_dataset(path: Path):
    """Load a CSV or XLSX into a normalized DataFrame with Latitude/Longitude.

    - A CSV produced by build_geocoded_csv.py already has coordinates.
    - A raw XLSX (name/address only) is enriched from a sibling
      geocode_cache.json when one exists, without any network calls.
    Returns (dataframe, meta) where meta describes coverage.
    """
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype={"License Number": str})
        if "Latitude" not in df.columns or "Longitude" not in df.columns:
            df["Latitude"] = None
            df["Longitude"] = None
    else:
        df = pd.read_excel(path, dtype={"License number": str})
        df = df.rename(columns={
            "License number": "License Number",
            "Address of tobacco product sales point (location)": "Address",
            "Start of validity": "Start of Validity",
            "End of validity": "End of Validity",
        })
        cache = load_cache_for(path)
        lats, lons = [], []
        for addr in df["Address"]:
            entry = cache.get(addr) if isinstance(addr, str) else None
            lats.append(entry["lat"] if entry else None)
            lons.append(entry["lon"] if entry else None)
        df["Latitude"] = lats
        df["Longitude"] = lons

    total = len(df)
    mapped = int(df["Latitude"].notna().sum())
    meta = {"total": total, "mapped": mapped, "unmapped": total - mapped}
    return df, meta
