#!/usr/bin/env python3
"""Build a CSV with lat/lon columns for a city, using an existing geocode
cache. Never calls the geocoding API — run geocode_budapest.py (or its
per-city equivalent) first to populate <city_dir>/geocode_cache.json.

Usage:
    python scripts/build_geocoded_csv.py data/Budapest
    python scripts/build_geocoded_csv.py            # builds every city under data/
"""
import csv
import json
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def build_csv(city_dir: Path) -> Path | None:
    xlsx_files = list(city_dir.glob("*.xlsx"))
    cache_path = city_dir / "geocode_cache.json"

    if not xlsx_files:
        print(f"[skip] {city_dir.name}: no .xlsx file found")
        return None
    if not cache_path.exists():
        print(f"[skip] {city_dir.name}: no geocode_cache.json found (run the geocoder first)")
        return None

    xlsx_path = xlsx_files[0]
    cache = json.loads(cache_path.read_text())

    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    out_path = city_dir / f"{city_dir.name}_geocoded.csv"
    matched = 0
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "License Number", "Address", "Start of Validity", "End of Validity", "Latitude", "Longitude"])
        for row in rows:
            name, license_no, address, start_valid, end_valid = row[:5]
            if not address:
                continue
            entry = cache.get(address)
            lat = entry["lat"] if entry else ""
            lon = entry["lon"] if entry else ""
            if entry:
                matched += 1
            writer.writerow([name, license_no, address, start_valid, end_valid, lat, lon])

    print(f"[ok] {city_dir.name}: wrote {out_path.relative_to(ROOT)} ({matched}/{len(rows)} rows with coordinates)")
    return out_path


def main():
    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1]).resolve()]
    else:
        targets = [p for p in DATA_DIR.iterdir() if p.is_dir()]

    for city_dir in targets:
        build_csv(city_dir)


if __name__ == "__main__":
    main()
