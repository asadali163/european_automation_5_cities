"""EU Cities Project — shop map dashboard.

Pick any CSV/XLSX under data/ and see every shop plotted on a map.
Run with: streamlit run app/app.py
"""
import sys
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import DATA_DIR, discover_files, load_dataset

st.set_page_config(page_title="EU Cities — Shop Map", page_icon="🗺️", layout="wide")

st.title("EU Cities Project")
st.caption("Shop mapping dashboard — pick a data file to plot it on the map.")

files = discover_files()
if not files:
    st.error(f"No .csv or .xlsx files found under {DATA_DIR}.")
    st.stop()

labels = [str(f.relative_to(DATA_DIR)) for f in files]
default_idx = next((i for i, l in enumerate(labels) if l.endswith("_geocoded.csv")), 0)

with st.sidebar:
    st.header("Data source")
    choice = st.selectbox("CSV or Excel file", labels, index=default_idx)
    selected_path = files[labels.index(choice)]

    df, meta = load_dataset(selected_path)

    st.markdown("---")
    search = st.text_input("Search name or address")
    only_mapped = st.checkbox("Only show shops with coordinates", value=True)

filtered = df.copy()
if search:
    mask = (
        filtered["Name"].astype(str).str.contains(search, case=False, na=False)
        | filtered["Address"].astype(str).str.contains(search, case=False, na=False)
    )
    filtered = filtered[mask]
if only_mapped:
    filtered = filtered[filtered["Latitude"].notna()]

col1, col2, col3 = st.columns(3)
col1.metric("Total in file", meta["total"])
col2.metric("Mapped", meta["mapped"])
col3.metric("Missing coordinates", meta["unmapped"])

mappable = filtered.dropna(subset=["Latitude", "Longitude"])

if mappable.empty:
    st.warning("No shops with coordinates match the current filters.")
else:
    center = [mappable["Latitude"].astype(float).mean(), mappable["Longitude"].astype(float).mean()]
    fmap = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")
    cluster = MarkerCluster().add_to(fmap)

    for _, row in mappable.iterrows():
        popup_html = (
            f"<b>{row['Name']}</b><br>"
            f"{row['Address']}<br>"
            f"License: {row.get('License Number', '—')}<br>"
            f"Valid: {row.get('Start of Validity', '—')} – {row.get('End of Validity', '—')}"
        )
        folium.CircleMarker(
            location=[float(row["Latitude"]), float(row["Longitude"])],
            radius=5,
            color="#0f6e63",
            weight=1,
            fill=True,
            fill_color="#0f6e63",
            fill_opacity=0.85,
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=row["Name"],
        ).add_to(cluster)

    sw = mappable[["Latitude", "Longitude"]].astype(float).min().values.tolist()
    ne = mappable[["Latitude", "Longitude"]].astype(float).max().values.tolist()
    fmap.fit_bounds([sw, ne])

    st_folium(fmap, width=None, height=560, returned_objects=[])

with st.expander(f"Shop data ({len(filtered)} rows)", expanded=False):
    st.dataframe(filtered, width="stretch", hide_index=True)
