"""Shared data-loading helpers for the EU Cities dashboard.

Keeps file discovery and lat/lon enrichment in one place so every page
(current and future) reads project data the same way.
"""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

KML_NS = "{http://www.opengis.net/kml/2.2}"

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
    is_csv = path.suffix.lower() == ".csv"
    df = pd.read_csv(path, dtype={"License Number": str, "License number": str}) if is_csv \
        else pd.read_excel(path, dtype={"License number": str})
    df = df.rename(columns={
        "License number": "License Number",
        "Address of tobacco product sales point (location)": "Address",
        "Start of validity": "Start of Validity",
        "End of validity": "End of Validity",
        "latitude": "Latitude",
        "longitude": "Longitude",
    })
    if "Latitude" in df.columns and "Longitude" in df.columns:
        # Already geocoded (e.g. by build_geocoded_csv.py or the Maps scraper).
        pass
    elif is_csv:
        df["Latitude"] = None
        df["Longitude"] = None
    else:
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


def find_boundary_for(path: Path):
    """Return the first .kml file sitting next to a data file, if any."""
    matches = [p for p in path.parent.iterdir() if p.suffix.lower() == ".kml"]
    return matches[0] if matches else None


def _parse_kml_coords(text):
    points = []
    for chunk in text.split():
        parts = chunk.strip().split(",")
        if len(parts) < 2:
            continue
        lon, lat = float(parts[0]), float(parts[1])
        points.append((lat, lon))
    return points


def load_kml_polygons(path: Path):
    """Parse a KML file's Polygon placemarks into [(outer_ring, [hole_rings...]), ...].

    Each ring is a list of (lat, lon) tuples, already reordered from KML's
    native lon,lat so callers can hand them straight to folium/Leaflet.
    """
    tree = ET.parse(path)
    root = tree.getroot()
    polygons = []
    for polygon_el in root.iter(f"{KML_NS}Polygon"):
        outer_el = polygon_el.find(f"{KML_NS}outerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates")
        if outer_el is None or not outer_el.text:
            continue
        outer = _parse_kml_coords(outer_el.text)
        holes = []
        for inner_el in polygon_el.findall(f"{KML_NS}innerBoundaryIs/{KML_NS}LinearRing/{KML_NS}coordinates"):
            if inner_el.text:
                holes.append(_parse_kml_coords(inner_el.text))
        polygons.append((outer, holes))
    return polygons


def slugify(name: str) -> str:
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_-]", "", name)
    return name


def save_uploaded_city(city_name: str, data_file=None, boundary_file=None):
    """Persist uploaded shop data / boundary files under data/<city>/.

    data_file and boundary_file are Streamlit UploadedFile objects (or None).
    Returns the new city directory.
    """
    slug = slugify(city_name)
    if not slug:
        raise ValueError("City name must contain at least one letter or number.")

    city_dir = DATA_DIR / slug
    city_dir.mkdir(parents=True, exist_ok=True)

    if data_file is not None:
        suffix = Path(data_file.name).suffix.lower()
        out_path = city_dir / f"{slug}{suffix}"
        out_path.write_bytes(data_file.getvalue())

    if boundary_file is not None:
        out_path = city_dir / f"{slug}_boundary.kml"
        out_path.write_bytes(boundary_file.getvalue())

    return city_dir
