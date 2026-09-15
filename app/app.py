"""EU Cities Project — shop map dashboard.

Pick any CSV/XLSX under data/ and see every shop plotted on a map, with the
city boundary overlaid when a .kml file sits alongside the data.
Run with: streamlit run app/app.py
"""
import sys
from pathlib import Path

import folium
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_loader import (
    DATA_DIR,
    discover_files,
    find_boundary_for,
    load_dataset,
    load_kml_polygons,
    save_uploaded_city,
)

st.set_page_config(page_title="EU Cities — Shop Map", page_icon="🗺️", layout="wide")

st.title("EU Cities Project")
st.caption("Shop mapping dashboard — pick a data file to plot it on the map.")

files = discover_files()

with st.sidebar:
    st.header("Data source")

    if not files:
        st.warning("No .csv or .xlsx files found under data/ yet — add one below.")
        selected_path = None
    else:
        labels = [str(f.relative_to(DATA_DIR)) for f in files]
        preselect = st.session_state.pop("preselect_label", None)
        if preselect and preselect in labels:
            default_idx = labels.index(preselect)
        else:
            default_idx = next((i for i, l in enumerate(labels) if l.endswith("_geocoded.csv")), 0)
        choice = st.selectbox("CSV or Excel file", labels, index=default_idx)
        selected_path = files[labels.index(choice)]

    st.markdown("---")
    search = st.text_input("Search name or address")
    only_mapped = st.checkbox("Only show shops with coordinates", value=True)

    st.markdown("---")
    with st.expander("➕ Add a new city", expanded=(selected_path is None)):
        st.caption("Upload a shop list and (optionally) a boundary KML for another city.")
        new_city = st.text_input("City name", key="new_city_name")
        new_data = st.file_uploader("Shop data (CSV or Excel)", type=["csv", "xlsx"], key="new_city_data")
        new_boundary = st.file_uploader("City boundary (KML)", type=["kml"], key="new_city_boundary")
        if st.button("Save to project"):
            if not new_city.strip():
                st.error("Enter a city name first.")
            elif new_data is None and new_boundary is None:
                st.error("Upload at least a shop data file or a boundary KML.")
            else:
                city_dir = save_uploaded_city(new_city, new_data, new_boundary)
                st.success(f"Saved to data/{city_dir.name}/")
                if new_data is not None:
                    st.session_state["preselect_label"] = f"{city_dir.name}/{city_dir.name}{Path(new_data.name).suffix.lower()}"
                st.rerun()

if selected_path is None:
    st.info("Add a city from the sidebar to get started.")
    st.stop()

df, meta = load_dataset(selected_path)
boundary_path = find_boundary_for(selected_path)

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
boundary_polygons = load_kml_polygons(boundary_path) if boundary_path else []

if mappable.empty and not boundary_polygons:
    st.warning("Nothing to show yet — no shops with coordinates and no boundary file.")
else:
    # Fit the initial view to the city boundary when we have one — a handful
    # of shops geocoded to addresses in other towns (e.g. a street literally
    # named "Budapest Road" elsewhere) shouldn't zoom the map out to fit them.
    if boundary_polygons:
        fit_lat = [pt[0] for outer, _holes in boundary_polygons for pt in outer]
        fit_lon = [pt[1] for outer, _holes in boundary_polygons for pt in outer]
    elif not mappable.empty:
        fit_lat = mappable["Latitude"].astype(float).tolist()
        fit_lon = mappable["Longitude"].astype(float).tolist()
    else:
        fit_lat, fit_lon = [], []

    center = [sum(fit_lat) / len(fit_lat), sum(fit_lon) / len(fit_lon)]
    fmap = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")

    if boundary_path:
        boundary_name = boundary_path.stem.replace("_", " ")
        for outer, holes in boundary_polygons:
            folium.Polygon(
                locations=[outer] + holes if holes else outer,
                color="#0b5049",
                weight=2.5,
                fill=True,
                fill_color="#0f6e63",
                fill_opacity=0.06,
                tooltip=boundary_name,
            ).add_to(fmap)

    if not mappable.empty:
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

    sw = [min(fit_lat), min(fit_lon)]
    ne = [max(fit_lat), max(fit_lon)]
    fmap.fit_bounds([sw, ne])

    st_folium(fmap, width=None, height=560, returned_objects=[])

with st.expander(f"Shop data ({len(filtered)} rows)", expanded=False):
    st.dataframe(filtered, width="stretch", hide_index=True)
