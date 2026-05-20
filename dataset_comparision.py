import pandas as pd
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# ─────────────────────────────────────────────────────────────
# 1. LOAD MOISTURE / LANDSAT DATA
# ─────────────────────────────────────────────────────────────
moisture_data = pd.read_csv("data/moisture_data.csv")

# parse Landsat timestamp
moisture_data["datetime"] = pd.to_datetime(moisture_data["date"], errors="coerce")
moisture_data["date_only"] = moisture_data["datetime"].dt.date
moisture_data["year"] = moisture_data["datetime"].dt.year

# split by year
moisture_2023 = moisture_data[moisture_data["year"] == 2023].copy()
moisture_2024 = moisture_data[moisture_data["year"] == 2024].copy()

# save split moisture files
moisture_2023.to_csv("data/moisture_data_2023.csv", index=False)
moisture_2024.to_csv("data/moisture_data_2024.csv", index=False)

print("Saved split moisture files:")
print("  data/moisture_data_2023.csv", moisture_2023.shape)
print("  data/moisture_data_2024.csv", moisture_2024.shape)

# ─────────────────────────────────────────────────────────────
# 2. LOAD MESONET DATA
# ─────────────────────────────────────────────────────────────
mesonet_2023 = pd.read_csv("mesonet_data/mesonet_statewide_hourly_2023.csv")
mesonet_2024 = pd.read_csv("mesonet_data/mesonet_statewide_hourly_2024.csv")

mesonet_2023["Date"] = pd.to_datetime(mesonet_2023["Date"], format="mixed", errors="coerce")
mesonet_2024["Date"] = pd.to_datetime(mesonet_2024["Date"], format="mixed", errors="coerce")

mesonet_2023["date_only"] = mesonet_2023["Date"].dt.date
mesonet_2024["date_only"] = mesonet_2024["Date"].dt.date

# If your Mesonet station column is not station_name, rename it here.
# Example:
# mesonet_2023 = mesonet_2023.rename(columns={"STID": "station_name"})
# mesonet_2024 = mesonet_2024.rename(columns={"STID": "station_name"})

# ─────────────────────────────────────────────────────────────
# 3. AGGREGATE MESONET HOURLY DATA TO DAILY
#    This avoids getting many hourly rows per single Landsat scene date
# ─────────────────────────────────────────────────────────────
numeric_cols_2023 = mesonet_2023.select_dtypes(include="number").columns.tolist()
numeric_cols_2024 = mesonet_2024.select_dtypes(include="number").columns.tolist()

# remove helper year columns if present
numeric_cols_2023 = [c for c in numeric_cols_2023 if c not in ["year"]]
numeric_cols_2024 = [c for c in numeric_cols_2024 if c not in ["year"]]

mesonet_daily_2023 = (
    mesonet_2023
    .groupby(["station_name", "date_only"], as_index=False)[numeric_cols_2023]
    .mean()
)

mesonet_daily_2024 = (
    mesonet_2024
    .groupby(["station_name", "date_only"], as_index=False)[numeric_cols_2024]
    .mean()
)

# ─────────────────────────────────────────────────────────────
# 4. MERGE EACH YEAR INDEPENDENTLY
# ─────────────────────────────────────────────────────────────
merged_2023 = pd.merge(
    moisture_2023,
    mesonet_daily_2023,
    on=["station_name", "date_only"],
    how="inner",
    suffixes=("_landsat", "_mesonet")
)

merged_2024 = pd.merge(
    moisture_2024,
    mesonet_daily_2024,
    on=["station_name", "date_only"],
    how="inner",
    suffixes=("_landsat", "_mesonet")
)

# optional combined merged file
merged_all = pd.concat([merged_2023, merged_2024], ignore_index=True)

# ─────────────────────────────────────────────────────────────
# 5. SAVE OUTPUTS
# ─────────────────────────────────────────────────────────────
merged_2023.to_csv("data/mesonet_landsat_2023.csv", index=False)
merged_2024.to_csv("data/mesonet_landsat_2024.csv", index=False)
merged_all.to_csv("data/mesonet_landsat_2023_2024.csv", index=False)

print("\nSaved merged files:")
print("  data/mesonet_landsat_2023.csv", merged_2023.shape)
print("  data/mesonet_landsat_2024.csv", merged_2024.shape)
print("  data/mesonet_landsat_2023_2024.csv", merged_all.shape)

# =========================================================
# CONFIG
# =========================================================
csv_path = "mesonet_data/mesonet_statewide_hourly_2023.csv"
out_dir = "mesonet_truth_plots"
os.makedirs(out_dir, exist_ok=True)

TR05_MIN = 1.3
TR05_MAX = 4.5
HOURLY_JUMP_THRESH = 0.5
ROLLING_DAYS = 14

month_tickvals = list(range(1, 13))
month_ticktext = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
]

# =========================================================
# LOAD
# =========================================================
df = pd.read_csv(csv_path)

# =========================================================
# CLEAN
# =========================================================
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df["TR05"] = pd.to_numeric(df["TR05"], errors="coerce")

df = df.dropna(subset=["Date", "TR05", "station_name"]).copy()
df = df.sort_values(["station_name", "Date"]).reset_index(drop=True)

print(f"Raw rows after basic cleaning: {len(df)}")

# =========================================================
# STEP 0A: HARD PHYSICAL FILTER
# =========================================================
df["TR05_bound"] = df["TR05"].where(
    (df["TR05"] >= TR05_MIN) & (df["TR05"] <= TR05_MAX)
)

# =========================================================
# STEP 0B: DESPIKE HOURLY OUTLIERS
# =========================================================
df["TR05_diff"] = (
    df.groupby("station_name")["TR05_bound"]
      .diff()
      .abs()
)

first_obs_mask = df.groupby("station_name").cumcount() == 0

df["TR05_clean"] = df["TR05_bound"].where(
    (df["TR05_diff"] <= HOURLY_JUMP_THRESH) | first_obs_mask
)

print(f"Rows with bounded TR05: {df['TR05_bound'].notna().sum()}")
print(f"Rows after despike filter: {df['TR05_clean'].notna().sum()}")

kept_pct = 100 * df["TR05_clean"].notna().sum() / len(df)
print(f"Percent of hourly rows kept after cleaning: {kept_pct:.2f}%")

# =========================================================
# STEP 1: DAILY AVERAGE
# =========================================================
df["day"] = df["Date"].dt.floor("D")

daily = (
    df.groupby(["station_name", "day"], as_index=False)
      .agg(
          TR05_raw_mean=("TR05", "mean"),
          TR05_clean_mean=("TR05_clean", "mean"),
          n_obs=("TR05", "count"),
          n_clean=("TR05_clean", lambda x: x.notna().sum())
      )
)

daily["Date"] = pd.to_datetime(daily["day"])
daily = daily.drop(columns=["day"])

daily = daily.dropna(subset=["TR05_clean_mean"]).copy()

# =========================================================
# STEP 2: STATEWIDE DAILY MEAN
# =========================================================
state_daily = (
    daily.groupby("Date", as_index=False)
         .agg(
             TR05_raw=("TR05_raw_mean", "mean"),
             TR05_clean=("TR05_clean_mean", "mean")
         )
         .sort_values("Date")
         .reset_index(drop=True)
)

# =========================================================
# STEP 3: ROLLING SMOOTH
# =========================================================
state_daily["TR05_clean_roll"] = (
    state_daily["TR05_clean"]
    .rolling(ROLLING_DAYS, center=True, min_periods=5)
    .mean()
)

# =========================================================
# GRAPH 1
# =========================================================
fig1 = go.Figure()

fig1.add_trace(go.Scatter(
    x=state_daily["Date"],
    y=state_daily["TR05_raw"],
    mode="lines",
    name="Daily Mean (Raw)",
    opacity=0.25
))

fig1.add_trace(go.Scatter(
    x=state_daily["Date"],
    y=state_daily["TR05_clean"],
    mode="lines",
    name="Daily Mean (Cleaned)",
    opacity=0.5
))

fig1.add_trace(go.Scatter(
    x=state_daily["Date"],
    y=state_daily["TR05_clean_roll"],
    mode="lines",
    name=f"{ROLLING_DAYS}-values Rolling (Cleaned)",
    line=dict(width=3)
))

fig1.update_layout(
    title="Oklahoma Statewide TR05 (Raw vs Cleaned vs Smoothed)",
    xaxis_title="Date",
    yaxis_title="TR05",
    template="plotly_white",
    height=600
)

fig1_path = os.path.join(out_dir, "01_statewide_TR05_daily_cleaned_smoothed.html")
fig1.write_html(fig1_path)
print(f"Saved: {fig1_path}")

# =========================================================
# STEP 4: MONTHLY MEAN
# =========================================================
daily["month"] = daily["Date"].dt.month

monthly = (
    daily.groupby("month", as_index=False)
         .agg(
             TR05_raw=("TR05_raw_mean", "mean"),
             TR05_clean=("TR05_clean_mean", "mean")
         )
)

# =========================================================
# GRAPH 2
# =========================================================
fig2 = go.Figure()

fig2.add_trace(go.Scatter(
    x=monthly["month"],
    y=monthly["TR05_raw"],
    mode="lines+markers",
    name="Monthly Mean (Raw)"
))

fig2.add_trace(go.Scatter(
    x=monthly["month"],
    y=monthly["TR05_clean"],
    mode="lines+markers",
    name="Monthly Mean (Cleaned)"
))

fig2.update_layout(
    title="Seasonal Cycle of TR05 (Monthly Mean)",
    xaxis=dict(
        title="Month",
        tickmode="array",
        tickvals=month_tickvals,
        ticktext=month_ticktext
    ),
    yaxis=dict(title="TR05"),
    template="plotly_white",
    height=550
)

fig2_path = os.path.join(out_dir, "02_monthly_TR05_seasonal_cycle.html")
fig2.write_html(fig2_path)
print(f"Saved: {fig2_path}")

# =========================================================
# GRAPH 3
# =========================================================
fig3 = px.box(
    daily,
    x="month",
    y="TR05_raw_mean",
    title="Monthly Distribution of TR05 (Raw Daily Station Means)"
)

fig3.update_layout(
    xaxis=dict(
        title="Month",
        tickmode="array",
        tickvals=month_tickvals,
        ticktext=month_ticktext
    ),
    yaxis=dict(title="TR05"),
    template="plotly_white",
    height=550
)

fig3_path = os.path.join(out_dir, "03_monthly_TR05_distribution_raw.html")
fig3.write_html(fig3_path)
print(f"Saved: {fig3_path}")

# =========================================================
# GRAPH 4
# =========================================================
fig4 = px.box(
    daily,
    x="month",
    y="TR05_clean_mean",
    title="Monthly Distribution of TR05 (Cleaned Daily Station Means)"
)

fig4.update_layout(
    xaxis=dict(
        title="Month",
        tickmode="array",
        tickvals=month_tickvals,
        ticktext=month_ticktext
    ),
    yaxis=dict(title="TR05"),
    template="plotly_white",
    height=550
)

fig4_path = os.path.join(out_dir, "04_monthly_TR05_distribution_cleaned.html")
fig4.write_html(fig4_path)
print(f"Saved: {fig4_path}")

# =========================================================
# GRAPH 5
# =========================================================
monthly_quality = (
    daily.groupby("month", as_index=False)
         .agg(
             total_obs=("n_obs", "sum"),
             clean_obs=("n_clean", "sum")
         )
)

monthly_quality["keep_ratio"] = monthly_quality["clean_obs"] / monthly_quality["total_obs"]

fig5 = go.Figure()

fig5.add_trace(go.Bar(
    x=monthly_quality["month"],
    y=monthly_quality["keep_ratio"],
    name="Kept Ratio"
))

fig5.update_layout(
    title="Fraction of Hourly TR05 Observations Kept After Cleaning",
    xaxis=dict(
        title="Month",
        tickmode="array",
        tickvals=month_tickvals,
        ticktext=month_ticktext
    ),
    yaxis=dict(title="Kept Ratio", range=[0, 1]),
    template="plotly_white",
    height=500
)

fig5_path = os.path.join(out_dir, "05_monthly_TR05_kept_ratio.html")
fig5.write_html(fig5_path)
print(f"Saved: {fig5_path}")

print("\nDone.")