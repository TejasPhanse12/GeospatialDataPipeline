import os
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# =========================================================
# CONFIG
# =========================================================
csv_path = "data/mesonet_landsat_2023_2024.csv"   # change if needed
out_dir = "plotly_station_graphs"
os.makedirs(out_dir, exist_ok=True)

YEAR_FILTER = None          # e.g. 2023 or 2024
ROLLING_DAYS = 14          # recommended: 7 or 14
MIN_PERIODS = 3            # minimum valid points for rolling mean

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
      .sort_values(["station_name", "date_only"])
      .reset_index(drop=True)
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

def minmax_normalize(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    smin = s.min()
    smax = s.max()
    if pd.isna(smin) or pd.isna(smax) or smax == smin:
        return pd.Series(np.nan, index=s.index)
    return (s - smin) / (smax - smin)

# =========================================================
# DERIVED SERIES: ROLLING + NORMALIZED
# =========================================================
daily["TR05_roll"] = (
    daily.groupby("station_name")["TR05"]
         .transform(lambda s: s.rolling(window=ROLLING_DAYS, min_periods=MIN_PERIODS).mean())
)

daily["ndmi_roll"] = (
    daily.groupby("station_name")["ndmi_mean"]
         .transform(lambda s: s.rolling(window=ROLLING_DAYS, min_periods=1).mean())
)

daily["TR05_norm"] = daily.groupby("station_name")["TR05"].transform(minmax_normalize)
daily["TR05_roll_norm"] = daily.groupby("station_name")["TR05_roll"].transform(minmax_normalize)

daily["ndmi_norm"] = daily.groupby("station_name")["ndmi_mean"].transform(minmax_normalize)
daily["ndmi_roll_norm"] = daily.groupby("station_name")["ndmi_roll"].transform(minmax_normalize)

# =========================================================
# WEEKLY AGGREGATION
# =========================================================
weekly = (
    daily.set_index("date_only")
         .groupby("station_name")
         .resample("W")
         .agg({
             "TR05": "mean",
             "ndmi_mean": "mean",
             "cloud_cover": "mean",
             "lat": "mean",
             "lon": "mean",
             "LAT": "mean",
             "LON": "mean"
         })
         .reset_index()
         .sort_values(["station_name", "date_only"])
         .reset_index(drop=True)
)

weekly["TR05_norm"] = weekly.groupby("station_name")["TR05"].transform(minmax_normalize)
weekly["ndmi_norm"] = weekly.groupby("station_name")["ndmi_mean"].transform(minmax_normalize)

# =========================================================
# GRAPH 1: ALL STATIONS TR05 (RAW DAILY)
# =========================================================
fig_tr05_raw = go.Figure()

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()
    lat_val, lon_val = pick_station_lat_lon(dfi)

    customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi)
    ))

    fig_tr05_raw.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05"],
            mode="lines",
            name=station,
            customdata=customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "TR05 Raw: %{y:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

fig_tr05_raw.update_layout(
    title="All Stations - TR05 Across Time (Raw Daily)",
    xaxis_title="Date",
    yaxis_title="TR05",
    template="plotly_white",
    hovermode="closest",
    height=700
)

raw_tr05_path = os.path.join(out_dir, "all_stations_TR05_raw_daily.html")
fig_tr05_raw.write_html(raw_tr05_path)
print(f"Saved: {raw_tr05_path}")

# =========================================================
# GRAPH 2: ALL STATIONS TR05 (ROLLING + NORMALIZED)
# =========================================================
fig_tr05_roll_norm = go.Figure()

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()
    lat_val, lon_val = pick_station_lat_lon(dfi)

    customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["TR05"].fillna(np.nan),
        dfi["TR05_roll"].fillna(np.nan)
    ))

    fig_tr05_roll_norm.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05_roll_norm"],
            mode="lines",
            name=station,
            customdata=customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                f"TR05 {ROLLING_DAYS}-values Rolling Norm: " + "%{y:.4f}<br>"
                "TR05 Raw: %{customdata[3]:.4f}<br>"
                f"TR05 {ROLLING_DAYS}-values Rolling: " + "%{customdata[4]:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

fig_tr05_roll_norm.update_layout(
    title=f"All Stations - TR05 Across Time ({ROLLING_DAYS}-values Rolling + Per-Station Normalized)",
    xaxis_title="Date",
    yaxis_title="TR05 Normalized",
    template="plotly_white",
    hovermode="closest",
    height=700
)

roll_norm_tr05_path = os.path.join(out_dir, f"all_stations_TR05_{ROLLING_DAYS}day_roll_norm.html")
fig_tr05_roll_norm.write_html(roll_norm_tr05_path)
print(f"Saved: {roll_norm_tr05_path}")

# =========================================================
# GRAPH 3: ALL STATIONS TR05 (WEEKLY + NORMALIZED)
# =========================================================
fig_tr05_weekly_norm = go.Figure()

for station in stations:
    dfi = weekly[weekly["station_name"] == station].copy()
    lat_val, lon_val = pick_station_lat_lon(dfi)

    customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["TR05"].fillna(np.nan)
    ))

    fig_tr05_weekly_norm.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05_norm"],
            mode="lines",
            name=station,
            customdata=customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Week: %{x|%Y-%m-%d}<br>"
                "TR05 Weekly Norm: %{y:.4f}<br>"
                "TR05 Weekly Mean: %{customdata[3]:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

fig_tr05_weekly_norm.update_layout(
    title="All Stations - TR05 Across Time (Weekly Mean + Per-Station Normalized)",
    xaxis_title="Date",
    yaxis_title="TR05 Weekly Normalized",
    template="plotly_white",
    hovermode="closest",
    height=700
)

weekly_norm_tr05_path = os.path.join(out_dir, "all_stations_TR05_weekly_norm.html")
fig_tr05_weekly_norm.write_html(weekly_norm_tr05_path)
print(f"Saved: {weekly_norm_tr05_path}")

# =========================================================
# GRAPH 4: ALL STATIONS NDMI (RAW)
# =========================================================
fig_ndmi = go.Figure()

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()
    lat_val, lon_val = pick_station_lat_lon(dfi)

    customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["cloud_cover"].fillna(np.nan)
    ))

    fig_ndmi.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["ndmi_mean"],
            mode="lines+markers",
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
    title="All Stations - NDMI Across Time (Raw Daily)",
    xaxis_title="Date",
    yaxis_title="NDMI Mean",
    template="plotly_white",
    hovermode="closest",
    height=700
)

ndmi_path = os.path.join(out_dir, "all_stations_NDMI_raw_daily.html")
fig_ndmi.write_html(ndmi_path)
print(f"Saved: {ndmi_path}")

# =========================================================
# GRAPH 5: ALL STATIONS NDMI (ROLLING + NORMALIZED)
# =========================================================
fig_ndmi_roll_norm = go.Figure()

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()
    lat_val, lon_val = pick_station_lat_lon(dfi)

    customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["cloud_cover"].fillna(np.nan),
        dfi["ndmi_mean"].fillna(np.nan),
        dfi["ndmi_roll"].fillna(np.nan)
    ))

    fig_ndmi_roll_norm.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["ndmi_roll_norm"],
            mode="lines+markers",
            name=station,
            customdata=customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "NDMI Rolling Norm: %{y:.4f}<br>"
                "NDMI Raw: %{customdata[4]:.4f}<br>"
                "NDMI Rolling: %{customdata[5]:.4f}<br>"
                "Cloud cover: %{customdata[3]:.2f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

fig_ndmi_roll_norm.update_layout(
    title=f"All Stations - NDMI Across Time ({ROLLING_DAYS}-values Rolling + Per-Station Normalized)",
    xaxis_title="Date",
    yaxis_title="NDMI Normalized",
    template="plotly_white",
    hovermode="closest",
    height=700
)

ndmi_roll_norm_path = os.path.join(out_dir, f"all_stations_NDMI_{ROLLING_DAYS}day_roll_norm.html")
fig_ndmi_roll_norm.write_html(ndmi_roll_norm_path)
print(f"Saved: {ndmi_roll_norm_path}")

# =========================================================
# STATION-WISE GRAPHS: SMOOTHED + NORMALIZED OPTIONS
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
        [lon_val] * len(dfi),
        dfi["TR05"].fillna(np.nan),
        dfi["TR05_roll"].fillna(np.nan),
        dfi["TR05_norm"].fillna(np.nan),
        dfi["TR05_roll_norm"].fillna(np.nan),
    ))

    ndmi_customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["cloud_cover"].fillna(np.nan),
        dfi["ndmi_mean"].fillna(np.nan),
        dfi["ndmi_roll"].fillna(np.nan),
        dfi["ndmi_norm"].fillna(np.nan),
        dfi["ndmi_roll_norm"].fillna(np.nan),
    ))

    # smoothed TR05
    fig_station.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05_roll"],
            mode="lines",
            name=f"TR05 {ROLLING_DAYS}-values Rolling",
            yaxis="y1",
            customdata=tr05_customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "TR05 Raw: %{customdata[3]:.4f}<br>"
                f"TR05 {ROLLING_DAYS}-values Rolling: " + "%{y:.4f}<br>"
                "TR05 Raw Norm: %{customdata[5]:.4f}<br>"
                "TR05 Rolling Norm: %{customdata[6]:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

    # smoothed NDMI
    fig_station.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["ndmi_roll"],
            mode="lines+markers",
            name=f"NDMI {ROLLING_DAYS}-values Rolling",
            yaxis="y2",
            customdata=ndmi_customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "NDMI Raw: %{customdata[4]:.4f}<br>"
                f"NDMI {ROLLING_DAYS}-values Rolling: " + "%{y:.4f}<br>"
                "NDMI Raw Norm: %{customdata[6]:.4f}<br>"
                "NDMI Rolling Norm: %{customdata[7]:.4f}<br>"
                "Cloud cover: %{customdata[3]:.2f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

    fig_station.update_layout(
        title=f"{station} - Smoothed TR05 vs Smoothed NDMI",
        xaxis=dict(title="Date"),
        yaxis=dict(title=f"TR05 {ROLLING_DAYS}-values Rolling"),
        yaxis2=dict(
            title=f"NDMI {ROLLING_DAYS}-values Rolling",
            overlaying="y",
            side="right"
        ),
        template="plotly_white",
        hovermode="closest",
        height=650
    )

    station_file = os.path.join(out_dir, f"{safe_name(station)}_TR05_vs_NDMI_smoothed.html")
    fig_station.write_html(station_file)
    count_saved += 1
    print(f"Saved: {station_file}")

# =========================================================
# OPTIONAL: STATION-WISE NORMALIZED COMPARISON
# =========================================================
count_saved_norm = 0

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()

    if dfi["TR05_roll_norm"].isna().all() and dfi["ndmi_roll_norm"].isna().all():
        continue

    lat_val, lon_val = pick_station_lat_lon(dfi)

    fig_station_norm = go.Figure()

    customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["TR05_roll"].fillna(np.nan),
        dfi["ndmi_roll"].fillna(np.nan)
    ))

    fig_station_norm.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05_roll_norm"],
            mode="lines",
            name=f"TR05 {ROLLING_DAYS}-values Rolling Norm",
            customdata=customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "TR05 Rolling Norm: %{y:.4f}<br>"
                f"TR05 {ROLLING_DAYS}-values Rolling: " + "%{customdata[3]:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

    fig_station_norm.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["ndmi_roll_norm"],
            mode="lines+markers",
            name=f"NDMI {ROLLING_DAYS}-values Rolling Norm",
            customdata=customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "NDMI Rolling Norm: %{y:.4f}<br>"
                f"NDMI {ROLLING_DAYS}-values Rolling: " + "%{customdata[4]:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

    fig_station_norm.update_layout(
        title=f"{station} - Normalized Smoothed TR05 vs NDMI",
        xaxis=dict(title="Date"),
        yaxis=dict(title="Normalized Value", range=[0, 1]),
        template="plotly_white",
        hovermode="closest",
        height=650
    )

    station_file_norm = os.path.join(out_dir, f"{safe_name(station)}_TR05_vs_NDMI_smoothed_normalized.html")
    fig_station_norm.write_html(station_file_norm)
    count_saved_norm += 1
    print(f"Saved: {station_file_norm}")

print("\nDone.")
print(
    f"Saved overview graphs + {count_saved} smoothed station graphs + "
    f"{count_saved_norm} normalized station graphs."
)