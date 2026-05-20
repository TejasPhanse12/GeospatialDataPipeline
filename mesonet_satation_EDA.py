import os
import re
import pandas as pd
import plotly.graph_objects as go

# =========================================================
# CONFIG
# =========================================================
csv_path = "data/mesonet_landsat_2023_2024.csv"   # change if needed
out_dir = "plotly_station_graphs"
os.makedirs(out_dir, exist_ok=True)

# Optional: set to 2023 or 2024 if you only want one year
YEAR_FILTER = None   # e.g. 2023 or 2024

# =========================================================
# LOAD DATA
# =========================================================
df = pd.read_csv(csv_path)

# =========================================================
# CLEAN / PREP
# =========================================================
df["date_only"] = pd.to_datetime(df["date_only"], errors="coerce")

for col in ["TR05", "TR25", "TR60", "ndmi_mean", "cloud_cover", "LAT", "LON", "lat", "lon", "year"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.dropna(subset=["station_name", "date_only"]).copy()

if YEAR_FILTER is not None:
    df = df[df["year"] == YEAR_FILTER].copy()

df = df.sort_values(["station_name", "date_only"]).copy()

# aggregate to one row per station per day
daily = (
    df.groupby(["station_name", "date_only"], as_index=False)
      .agg({
          "TR05": "mean",
          "ndmi_mean": "mean",
          "cloud_cover": "mean",
          "lat": "mean",
          "lon": "mean",
          "LAT": "mean",
          "LON": "mean"
      })
)

stations = sorted(daily["station_name"].dropna().unique().tolist())
print(f"Found {len(stations)} stations")

# =========================================================
# HELPERS
# =========================================================
def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", str(name)).strip("_")

def pick_station_lat_lon(dfi: pd.DataFrame):
    lat_val = None
    lon_val = None

    if "lat" in dfi.columns and dfi["lat"].notna().any():
        lat_val = dfi["lat"].dropna().iloc[0]
    elif "LAT" in dfi.columns and dfi["LAT"].notna().any():
        lat_val = dfi["LAT"].dropna().iloc[0]

    if "lon" in dfi.columns and dfi["lon"].notna().any():
        lon_val = dfi["lon"].dropna().iloc[0]
    elif "LON" in dfi.columns and dfi["LON"].notna().any():
        lon_val = dfi["LON"].dropna().iloc[0]

    return lat_val, lon_val

# =========================================================
# GRAPH 1: ALL STATIONS TR05
# =========================================================
fig_tr05 = go.Figure()

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()
    lat_val, lon_val = pick_station_lat_lon(dfi)

    customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi)
    ))

    fig_tr05.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05"],
            mode="lines",
            name=station,
            customdata=customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "TR05: %{y:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

fig_tr05.update_layout(
    title="All Stations - TR05 Across Time",
    xaxis_title="Date",
    yaxis_title="TR05",
    template="plotly_white",
    hovermode="closest",
    height=700
)

tr05_path = os.path.join(out_dir, "all_stations_TR05.html")
fig_tr05.write_html(tr05_path)
print(f"Saved: {tr05_path}")

# =========================================================
# GRAPH 2: ALL STATIONS NDMI
# =========================================================
fig_ndmi = go.Figure()

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()
    lat_val, lon_val = pick_station_lat_lon(dfi)

    customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["cloud_cover"].fillna(float("nan"))
    ))

    fig_ndmi.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["ndmi_mean"],
            mode="lines",
            name=station,
            customdata=customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "NDMI: %{y:.4f}<br>"
                "Cloud cover: %{customdata[3]:.2f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

fig_ndmi.update_layout(
    title="All Stations - NDMI Across Time",
    xaxis_title="Date",
    yaxis_title="NDMI Mean",
    template="plotly_white",
    hovermode="closest",
    height=700
)

ndmi_path = os.path.join(out_dir, "all_stations_NDMI.html")
fig_ndmi.write_html(ndmi_path)
print(f"Saved: {ndmi_path}")

# =========================================================
# GRAPHS 3-122: STATION-WISE TR05 vs NDMI
# =========================================================
count_saved = 0

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()

    if dfi["TR05"].isna().all() and dfi["ndmi_mean"].isna().all():
        print(f"Skipping {station}: both TR05 and NDMI are all NaN")
        continue

    lat_val, lon_val = pick_station_lat_lon(dfi)

    fig_station = go.Figure()

    tr05_customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi)
    ))

    ndmi_customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["cloud_cover"].fillna(float("nan"))
    ))

    fig_station.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05"],
            mode="lines+markers",
            name="TR05",
            yaxis="y1",
            customdata=tr05_customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "TR05: %{y:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

    fig_station.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["ndmi_mean"],
            mode="lines+markers",
            name="NDMI",
            yaxis="y2",
            customdata=ndmi_customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "NDMI: %{y:.4f}<br>"
                "Cloud cover: %{customdata[3]:.2f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

    fig_station.update_layout(
        title=f"{station} - TR05 vs NDMI",
        xaxis=dict(title="Date"),
        yaxis=dict(title="TR05"),
        yaxis2=dict(
            title="NDMI Mean",
            overlaying="y",
            side="right"
        ),
        template="plotly_white",
        hovermode="closest",
        height=600
    )

    station_file = os.path.join(out_dir, f"{safe_name(station)}_TR05_vs_NDMI.html")
    fig_station.write_html(station_file)
    count_saved += 1
    print(f"Saved: {station_file}")

print("\nDone.")
print(f"Saved 2 overview graphs + {count_saved} station graphs = {2 + count_saved} total graphs.")