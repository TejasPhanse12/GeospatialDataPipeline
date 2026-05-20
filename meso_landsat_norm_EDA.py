import os
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# =========================================================
# CONFIG
# =========================================================
csv_path = "data/mesonet_landsat_2023_2024.csv"   # change if needed
out_dir = "plotly_station_graphs_toggle"
os.makedirs(out_dir, exist_ok=True)

YEAR_FILTER = None   # set to 2023 or 2024 if wanted

# =========================================================
# LOAD DATA
# =========================================================
df = pd.read_csv(csv_path)

df["date_only"] = pd.to_datetime(df["date_only"], errors="coerce")

for col in ["TR05", "ndmi_mean", "cloud_cover", "lat", "lon", "LAT", "LON", "year"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.dropna(subset=["station_name", "date_only"]).copy()

if YEAR_FILTER is not None:
    df = df[df["year"] == YEAR_FILTER].copy()

df = df.sort_values(["station_name", "date_only"]).copy()

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
    valid = s.dropna()

    if len(valid) == 0:
        return pd.Series(np.nan, index=series.index)

    s_min = valid.min()
    s_max = valid.max()

    if pd.isna(s_min) or pd.isna(s_max) or s_max == s_min:
        # flat series -> put valid points at 0.5
        out = pd.Series(np.nan, index=series.index, dtype=float)
        out.loc[valid.index] = 0.5
        return out

    return (s - s_min) / (s_max - s_min)


count_saved = 0

for station in stations:
    dfi = daily[daily["station_name"] == station].copy()

    if dfi["TR05"].isna().all() and dfi["ndmi_mean"].isna().all():
        print(f"Skipping {station}: both TR05 and NDMI are all NaN")
        continue

    dfi = dfi.sort_values("date_only").copy()
    dfi["TR05_norm"] = minmax_normalize(dfi["TR05"])

    lat_val, lon_val = pick_station_lat_lon(dfi)

    tr05_customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["TR05_norm"].tolist()
    ))

    ndmi_customdata = list(zip(
        [station] * len(dfi),
        [lat_val] * len(dfi),
        [lon_val] * len(dfi),
        dfi["cloud_cover"].fillna(float("nan")).tolist()
    ))

    fig_station = go.Figure()

    # Trace 0: raw TR05 (visible by default)
    fig_station.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05"],
            mode="lines+markers",
            name="TR05",
            yaxis="y1",
            visible=True,
            customdata=tr05_customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "TR05: %{y:.4f}<br>"
                "TR05 normalized: %{customdata[3]:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

    # Trace 1: normalized TR05 (hidden initially)
    fig_station.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["TR05_norm"],
            mode="lines+markers",
            name="TR05 normalized",
            yaxis="y1",
            visible=False,
            customdata=tr05_customdata,
            hovertemplate=(
                "Station: %{customdata[0]}<br>"
                "Date: %{x|%Y-%m-%d}<br>"
                "TR05 normalized: %{y:.4f}<br>"
                "Raw TR05: %{customdata[3]:.4f}<br>"
                "Lat: %{customdata[1]:.5f}<br>"
                "Lon: %{customdata[2]:.5f}"
                "<extra></extra>"
            )
        )
    )

    # Trace 2: NDMI (always visible)
    fig_station.add_trace(
        go.Scatter(
            x=dfi["date_only"],
            y=dfi["ndmi_mean"],
            mode="lines+markers",
            name="NDMI",
            yaxis="y2",
            visible=True,
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
        yaxis=dict(title="TR05 / Normalized TR05"),
        yaxis2=dict(
            title="NDMI Mean",
            overlaying="y",
            side="right"
        ),
        template="plotly_white",
        hovermode="closest",
        height=650,
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                x=0.5,
                y=1.18,
                xanchor="center",
                yanchor="top",
                showactive=True,
                buttons=[
                    dict(
                        label="Raw TR05",
                        method="update",
                        args=[
                            {"visible": [True, False, True]},
                            {"yaxis": {"title": "TR05"}}
                        ]
                    ),
                    dict(
                        label="Normalized TR05",
                        method="update",
                        args=[
                            {"visible": [False, True, True]},
                            {"yaxis": {"title": "Normalized TR05 (0-1)"}}
                        ]
                    ),
                ]
            )
        ]
    )

    station_file = os.path.join(out_dir, f"{safe_name(station)}_TR05_toggle_vs_NDMI.html")
    fig_station.write_html(station_file)
    count_saved += 1
    print(f"Saved: {station_file}")

print(f"\nDone. Saved {count_saved} station graphs with TR05 toggle buttons.")