### Understanding the Landsat
'''
- two ways to calculate the average
Station     # valid days        avg NDMI
A               20                  0.3
B               5                   0.6

- acutal clear days
$\frac{20 \cdot 0.3 + 5 \cdot 0.6}{25} = 0.36$

- equal station weight
$\frac{0.3 + 0.6}{2} = 0.45$
'''
import os
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

# =========================================================
# CONFIG
# =========================================================
csv_path = "data/moisture_data_2023.csv"
out_dir = "landsat_truth_plots"
os.makedirs(out_dir, exist_ok=True)

# NDMI practical bounds
NDMI_MIN = -1.0
NDMI_MAX = 1.0

# Cloud filter
MAX_CLOUD_COVER = 20.0   # try 10, 20, or 30

# Rolling window in number of observations after statewide aggregation
ROLLING_OBS = 5

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
df["date_only"] = pd.to_datetime(df["date_only"], errors="coerce")
df["ndmi_mean"] = pd.to_numeric(df["ndmi_mean"], errors="coerce")
df["cloud_cover"] = pd.to_numeric(df["cloud_cover"], errors="coerce")

df = df.dropna(subset=["date_only", "station_name"]).copy()
df = df.sort_values(["station_name", "date_only"]).reset_index(drop=True)

print(f"Raw rows after basic cleaning: {len(df)}")

# =========================================================
# STEP 0A: CLOUD FILTER
# =========================================================
df["ndmi_cloud_ok"] = df["ndmi_mean"].where(df["cloud_cover"] <= MAX_CLOUD_COVER)

# =========================================================
# STEP 0B: NDMI BOUNDS FILTER
# =========================================================
df["ndmi_clean"] = df["ndmi_cloud_ok"].where(
    (df["ndmi_cloud_ok"] >= NDMI_MIN) & (df["ndmi_cloud_ok"] <= NDMI_MAX)
)

print(f"Rows with cloud cover <= {MAX_CLOUD_COVER}: {df['ndmi_cloud_ok'].notna().sum()}")
print(f"Rows after NDMI cleaning: {df['ndmi_clean'].notna().sum()}")

kept_pct = 100 * df["ndmi_clean"].notna().sum() / len(df)
print(f"Percent of Landsat rows kept after cleaning: {kept_pct:.2f}%")

# =========================================================
# STEP 1: DAILY AVERAGE PER STATION
# =========================================================
df["day"] = df["date_only"].dt.floor("D")

daily = (
    df.groupby(["station_name", "day"], as_index=False)
      .agg(
          ndmi_raw_mean=("ndmi_mean", "mean"),
          ndmi_clean_mean=("ndmi_clean", "mean"),
          cloud_cover_mean=("cloud_cover", "mean"),
          n_obs=("ndmi_mean", "count"),
          n_clean=("ndmi_clean", lambda x: x.notna().sum())
      )
)

daily["Date"] = pd.to_datetime(daily["day"])
daily = daily.drop(columns=["day"])

# Keep days with valid cleaned NDMI
daily = daily.dropna(subset=["ndmi_clean_mean"]).copy()

# =========================================================
# STEP 2: STATEWIDE DAILY MEAN
# =========================================================
state_daily = (
    daily.groupby("Date", as_index=False)
         .agg(
             ndmi_raw=("ndmi_raw_mean", "mean"),
             ndmi_clean=("ndmi_clean_mean", "mean"),
             cloud_cover=("cloud_cover_mean", "mean")
         )
         .sort_values("Date")
         .reset_index(drop=True)
)

# =========================================================
# STEP 3: ROLLING SMOOTH
# Note: this is by observation count, not true daily continuity
# =========================================================
state_daily["ndmi_clean_roll"] = (
    state_daily["ndmi_clean"]
    .rolling(ROLLING_OBS, center=True, min_periods=2)
    .mean()
)

# =========================================================
# GRAPH 1: STATEWIDE DAILY + CLEANED + SMOOTHED
# =========================================================
fig1 = go.Figure()

fig1.add_trace(go.Scatter(
    x=state_daily["Date"],
    y=state_daily["ndmi_raw"],
    mode="lines+markers",
    name="Daily Mean (Raw)",
    opacity=0.25
))

fig1.add_trace(go.Scatter(
    x=state_daily["Date"],
    y=state_daily["ndmi_clean"],
    mode="lines+markers",
    name=f"Daily Mean (Cloud <= {MAX_CLOUD_COVER}%, Cleaned)",
    opacity=0.6
))

fig1.add_trace(go.Scatter(
    x=state_daily["Date"],
    y=state_daily["ndmi_clean_roll"],
    mode="lines",
    name=f"{ROLLING_OBS}-Observation Rolling (Cleaned)",
    line=dict(width=3)
))

fig1.update_layout(
    title="Oklahoma Statewide NDMI (Raw vs Cleaned vs Smoothed)",
    xaxis_title="Date",
    yaxis_title="NDMI",
    template="plotly_white",
    height=600
)

fig1_path = os.path.join(out_dir, "01_statewide_NDMI_daily_cleaned_smoothed.html")
fig1.write_html(fig1_path)
print(f"Saved: {fig1_path}")

# =========================================================
# STEP 4: MONTHLY MEAN
# =========================================================
daily["month"] = daily["Date"].dt.month

monthly = (
    daily.groupby("month", as_index=False)
         .agg(
             ndmi_raw=("ndmi_raw_mean", "mean"),
             ndmi_clean=("ndmi_clean_mean", "mean")
         )
)

# =========================================================
# GRAPH 2: MONTHLY SEASONAL CURVE
# =========================================================
fig2 = go.Figure()

fig2.add_trace(go.Scatter(
    x=monthly["month"],
    y=monthly["ndmi_raw"],
    mode="lines+markers",
    name="Monthly Mean (Raw)"
))

fig2.add_trace(go.Scatter(
    x=monthly["month"],
    y=monthly["ndmi_clean"],
    mode="lines+markers",
    name=f"Monthly Mean (Cloud <= {MAX_CLOUD_COVER}%, Cleaned)"
))

fig2.update_layout(
    title="Seasonal Cycle of NDMI (Monthly Mean)",
    xaxis=dict(
        title="Month",
        tickmode="array",
        tickvals=month_tickvals,
        ticktext=month_ticktext
    ),
    yaxis=dict(title="NDMI"),
    template="plotly_white",
    height=550
)

fig2_path = os.path.join(out_dir, "02_monthly_NDMI_seasonal_cycle.html")
fig2.write_html(fig2_path)
print(f"Saved: {fig2_path}")

# =========================================================
# GRAPH 3: MONTHLY DISTRIBUTION (RAW)
# =========================================================
fig3 = px.box(
    daily,
    x="month",
    y="ndmi_raw_mean",
    title="Monthly Distribution of NDMI (Raw Daily Station Means)"
)

fig3.update_layout(
    xaxis=dict(
        title="Month",
        tickmode="array",
        tickvals=month_tickvals,
        ticktext=month_ticktext
    ),
    yaxis=dict(title="NDMI"),
    template="plotly_white",
    height=550
)

fig3_path = os.path.join(out_dir, "03_monthly_NDMI_distribution_raw.html")
fig3.write_html(fig3_path)
print(f"Saved: {fig3_path}")

# =========================================================
# GRAPH 4: MONTHLY DISTRIBUTION (CLEANED)
# =========================================================
fig4 = px.box(
    daily,
    x="month",
    y="ndmi_clean_mean",
    title=f"Monthly Distribution of NDMI (Cleaned, Cloud <= {MAX_CLOUD_COVER}%)"
)

fig4.update_layout(
    xaxis=dict(
        title="Month",
        tickmode="array",
        tickvals=month_tickvals,
        ticktext=month_ticktext
    ),
    yaxis=dict(title="NDMI"),
    template="plotly_white",
    height=550
)

fig4_path = os.path.join(out_dir, "04_monthly_NDMI_distribution_cleaned.html")
fig4.write_html(fig4_path)
print(f"Saved: {fig4_path}")

# =========================================================
# GRAPH 5: HOW MANY OBS WERE KEPT AFTER CLEANING
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
    title=f"Fraction of Landsat NDMI Observations Kept After Cleaning (Cloud <= {MAX_CLOUD_COVER}%)",
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

fig5_path = os.path.join(out_dir, "05_monthly_NDMI_kept_ratio.html")
fig5.write_html(fig5_path)
print(f"Saved: {fig5_path}")

print("\nDone.")
print("Generated files:")
print(fig1_path)
print(fig2_path)
print(fig3_path)
print(fig4_path)
print(fig5_path)
