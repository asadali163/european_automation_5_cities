#!/usr/bin/env python3
"""Geocode Budapest tobacco retail addresses via OpenStreetMap Nominatim.

Caches every geocoded address to data/Budapest/geocode_cache.json so re-runs
never re-query an address that already succeeded or definitively failed.
"""
import json
import re
import time
from pathlib import Path

import openpyxl
import requests

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "data" / "Budapest" / "Budapest Official List.xlsx"
CACHE_PATH = ROOT / "data" / "Budapest" / "geocode_cache.json"
OUTPUT_PATH = ROOT / "data" / "Budapest" / "budapest_geocoded.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "EU-Cities-Project/1.0 (personal visualization project)"}
REQUEST_DELAY = 1.1  # Nominatim usage policy: max 1 req/sec


def load_cache():
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache):
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def strip_district(addr: str) -> str:
    # "1071 Budapest 07. ker. Rottenbiller utca 49." -> drop the redundant
    # district marker, which Nominatim's free-form parser often chokes on.
    addr = re.sub(r"\b\d{1,2}\.\s*ker\.\s*", "", addr)
    return re.sub(r"\s+", " ", addr).strip()


def simplify_house_number(addr: str) -> str:
    # "Zsókavár utca 43-47 fszt" -> "Zsókavár utca 43." — take the first
    # number of a range and drop floor/unit suffixes (fszt, em., ép., etc.)
    addr = re.sub(r"(\d+)\s*-\s*\d+", r"\1", addr)
    addr = re.sub(
        r"(\d+(?:/[A-Za-z])?)\.?\s+[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű.]+\s*$",
        r"\1.",
        addr,
    )
    return re.sub(r"\s+", " ", addr).strip()


def street_only(addr: str) -> str:
    # Last resort: drop the house number entirely, keep postal code/city/street.
    return re.sub(r"\s+\d+.*$", "", addr).strip()


def build_candidates(address: str):
    seen = set()
    candidates = []
    for candidate in [
        address,
        strip_district(address),
        simplify_house_number(strip_district(address)),
        street_only(strip_district(address)),
    ]:
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    return candidates


def geocode(address: str):
    for query in build_candidates(address):
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "hu"},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json()
        time.sleep(REQUEST_DELAY)
        if results:
            return {
                "lat": float(results[0]["lat"]),
                "lon": float(results[0]["lon"]),
                "query_used": query,
            }
    return None


def main():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    cache = load_cache()
    records = []
    geocoded_count = 0
    failed_count = 0
    cached_count = 0

    for i, row in enumerate(rows, start=1):
        name, license_no, address, start_valid, end_valid = row[:5]
        if not address:
            continue

        if address in cache and cache[address] is not None:
            cached_count += 1
            result = cache[address]
        else:
            try:
                result = geocode(address)
            except requests.RequestException as e:
                print(f"[{i}/{len(rows)}] ERROR geocoding '{address}': {e}")
                result = None
            cache[address] = result
            save_cache(cache)
            if result:
                geocoded_count += 1
                print(f"[{i}/{len(rows)}] OK  {address} -> {result['lat']:.5f},{result['lon']:.5f}")
            else:
                failed_count += 1
                print(f"[{i}/{len(rows)}] FAIL {address}")

        if result:
            records.append({
                "name": name,
                "license_number": license_no,
                "address": address,
                "start_of_validity": start_valid,
                "end_of_validity": end_valid,
                "lat": result["lat"],
                "lon": result["lon"],
            })

    OUTPUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"\nDone. cached_hits={cached_count} newly_geocoded={geocoded_count} failed={failed_count}")
    print(f"Total plotted points: {len(records)} / {len(rows)}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
