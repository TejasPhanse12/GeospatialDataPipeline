import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import pearsonr
import dash
from dash import dcc, html, Input, Output, callback

# ─────────────────────────────────────────────────────────────
# DATA LOADING  (your original logic — untouched)
# ─────────────────────────────────────────────────────────────
mesonet_data_2024 = pd.read_csv("mesonet_data/mesonet_statewide_hourly_2024.csv")
mesonet_data_2024["Date"] = pd.to_datetime(mesonet_data_2024["Date"], format="mixed")
mesonet_data_2024["Time"] = mesonet_data_2024["Date"].dt.time
mesonet_data_2024["Month_Year"] = mesonet_data_2024["Date"].dt.to_period("M")
mesonet_data_2024["Date"] = mesonet_data_2024["Date"].dt.date

mesonet_data_2023 = pd.read_csv("mesonet_data/mesonet_statewide_hourly_2023.csv")
mesonet_data_2023["Date"] = pd.to_datetime(mesonet_data_2023["Date"], format="mixed")
mesonet_data_2023["Time"] = mesonet_data_2023["Date"].dt.time
mesonet_data_2023["Month_Year"] = mesonet_data_2023["Date"].dt.to_period("M")
mesonet_data_2023["Date"] = mesonet_data_2023["Date"].dt.date

mesonet_data = pd.concat([mesonet_data_2023, mesonet_data_2024], ignore_index=True)

moisture_data = pd.read_csv("data/moisture_data.csv")
moisture_data["datetime"] = pd.to_datetime(moisture_data["date"])
moisture_data["date"] = moisture_data["datetime"].dt.date
moisture_data["Month_Year"] = moisture_data["datetime"].dt.strftime("%Y-%m")

ALL_STATIONS = sorted(moisture_data["station_name"].unique().tolist())

# ─────────────────────────────────────────────────────────────
# AGGREGATION  (extended to support per-station + quality gate)
# ─────────────────────────────────────────────────────────────
def build_master(station):
    """
    Mirrors your original merge logic but:
      - filters to a single station when requested
      - aggregates ALL available scenes per month (no quality gate)
      - carries cloud_cover through for the second correlation plot
    """
    m = moisture_data.copy()

    # Station filter
    if station != "__ALL__":
        print(station)
        m = m[m["station_name"] == station]
        meso = mesonet_data[mesonet_data["station_name"] == station].copy()
    else:
        meso = mesonet_data.copy()

    # Landsat monthly aggregation — all scenes included
    landsat_monthly = (
        m.groupby("Month_Year", as_index=False)
        .agg(
            Avg_NDMI_Moisture=("ndmi_mean", "mean"),
            Avg_Cloud_Cover=("cloud_cover", "mean"),
            scene_count=("scene_id", "count"),
        )
    )

    # Mesonet monthly aggregation (your original logic)
    meso_monthly = (
        meso.groupby("Month_Year", as_index=False)["TR05"]
        .mean()
        .rename(columns={"TR05": "Avg_mesonet_Moisture"})
    )
    meso_monthly["Month_Year"] = meso_monthly["Month_Year"].astype(str)

    # Merge (your original logic)
    master = pd.merge(landsat_monthly, meso_monthly, on="Month_Year", how="inner")
    print(master)
    return master


def add_derived_columns(master):
    """
    Your original normalization + rolling/expanding correlation logic — untouched.
    """
    def min_max_normalize(series):
        return (series - series.min()) / (series.max() - series.min())

    master = master.copy()
    master["NDMI_Normalized"]    = min_max_normalize(master["Avg_NDMI_Moisture"])
    master["Mesonet_Normalized"] = min_max_normalize(master["Avg_mesonet_Moisture"])

    epsilon = 1e-6
    master["NDMI_LogScaled"]    = np.log(master["NDMI_Normalized"] + epsilon)
    master["Mesonet_LogScaled"] = np.log(master["Mesonet_Normalized"] + epsilon)

    master["Rolling_Correlation"] = (
        master["NDMI_Normalized"]
        .rolling(window=1)
        .corr(master["Mesonet_Normalized"])
    )

    r_values, p_values = [], []
    for i in range(len(master)):
        if i < 2:
            r_values.append(np.nan)
            p_values.append(np.nan)
        else:
            r, p = pearsonr(
                master["NDMI_Normalized"].iloc[: i + 1],
                master["Mesonet_Normalized"].iloc[: i + 1],
            )
            r_values.append(r)
            p_values.append(p)

    master["Expanding_R"] = r_values
    master["Expanding_P"] = p_values
    master["Significant"] = master["Expanding_P"] < 0.05
    return master


# ─────────────────────────────────────────────────────────────
# FIGURE BUILDER  (subplots + cloud subplot)
# ─────────────────────────────────────────────────────────────
def build_figure(master):
    if master.empty:
        fig = go.Figure()
        fig.update_layout(title="No data available for the selected filters.")
        return fig

    r_final = master["Expanding_R"].dropna().iloc[-1] if master["Expanding_R"].notna().any() else float("nan")
    p_final = master["Expanding_P"].dropna().iloc[-1] if master["Expanding_P"].notna().any() else float("nan")

    # 3 subplots: your original 2 + cloud correlation
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=(
            "Soil Moisture Trend Comparison: Landsat NDMI vs Mesonet TR05",
            f"Validation: Expanding Pearson r = {r_final:.4f},  p = {p_final:.4f}",
            "Cloud Cover vs NDMI Mean",
        ),
        vertical_spacing=0.12,
    )

    # ── Row 1: your original RAW / NORMALIZED / LOG traces ────
    fig.add_trace(go.Scatter(
        x=master["Month_Year"], y=master["Avg_NDMI_Moisture"],
        mode="lines+markers", name="NDMI Raw", visible=True,
        hovertemplate="<b>%{x}</b><br>NDMI Raw: %{y:.6f}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=master["Month_Year"], y=master["Avg_mesonet_Moisture"],
        mode="lines+markers", name="Mesonet Raw", visible=True,
        hovertemplate="<b>%{x}</b><br>Mesonet Raw: %{y:.6f}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=master["Month_Year"], y=master["NDMI_Normalized"],
        mode="lines+markers", name="NDMI Normalized", visible=False,
        hovertemplate="<b>%{x}</b><br>NDMI Normalized: %{y:.4f}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=master["Month_Year"], y=master["Mesonet_Normalized"],
        mode="lines+markers", name="Mesonet Normalized", visible=False,
        hovertemplate="<b>%{x}</b><br>Mesonet Normalized: %{y:.4f}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=master["Month_Year"], y=master["NDMI_LogScaled"],
        mode="lines+markers", name="NDMI Log Scaled", visible=False,
        hovertemplate="<b>%{x}</b><br>NDMI Log Scaled: %{y:.4f}<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=master["Month_Year"], y=master["Mesonet_LogScaled"],
        mode="lines+markers", name="Mesonet Log Scaled", visible=False,
        hovertemplate="<b>%{x}</b><br>Mesonet Log Scaled: %{y:.4f}<extra></extra>",
    ), row=1, col=1)

    # ── Row 2: your original expanding correlation ─────────────
    fig.add_trace(go.Scatter(
        x=master["Month_Year"], y=master["Expanding_R"],
        mode="lines+markers", name="Expanding Pearson r",
        line=dict(color="green"),
        hovertemplate=(
            "<b>%{x}</b><br>Pearson r: %{y:.4f}<br>"
            "p-value: %{customdata:.4f}<extra></extra>"
        ),
        customdata=master["Expanding_P"],
    ), row=2, col=1)

    sig_data = master[master["Significant"]]
    fig.add_trace(go.Scatter(
        x=sig_data["Month_Year"], y=sig_data["Expanding_R"],
        mode="markers", name="Significant (p < 0.05)",
        marker=dict(color="red", size=10, symbol="star"),
        hovertemplate=(
            "<b>%{x}</b><br>Pearson r: %{y:.4f}<br>"
            "p-value: %{customdata:.4f}<extra></extra>"
        ),
        customdata=sig_data["Expanding_P"],
    ), row=2, col=1)

    fig.add_hline(
        y=0, line_dash="dash", line_color="red",
        annotation_text="Zero Correlation",
        annotation_position="bottom right",
        row=2, col=1,
    )

    # ── Row 3: Cloud Cover × NDMI ──────────────────────────────
    fig.add_trace(go.Scatter(
        x=master["Avg_Cloud_Cover"], y=master["Avg_NDMI_Moisture"],
        mode="markers",
        marker=dict(
            color=master["Avg_Cloud_Cover"],
            colorscale="RdBu_r",
            size=8, opacity=0.75,
            colorbar=dict(title="Cloud %", thickness=12, len=0.3, y=0.1),
        ),
        name="Cloud vs NDMI",
        text=master["Month_Year"],
        hovertemplate=(
            "<b>%{text}</b><br>Cloud Cover: %{x:.1f}%<br>"
            "NDMI Mean: %{y:.6f}<extra></extra>"
        ),
    ), row=3, col=1)

    # OLS trend line for cloud vs NDMI
    if len(master) >= 3:
        x_c = master["Avg_Cloud_Cover"].values
        y_c = master["Avg_NDMI_Moisture"].values
        mask = ~(np.isnan(x_c) | np.isnan(y_c))
        if mask.sum() >= 3:
            from scipy.stats import linregress
            slope, intercept, r_cc, p_cc, _ = linregress(x_c[mask], y_c[mask])
            x_line = np.array([x_c[mask].min(), x_c[mask].max()])
            fig.add_trace(go.Scatter(
                x=x_line, y=slope * x_line + intercept,
                mode="lines",
                name=f"Cloud Trend  r={r_cc:.3f}  p={p_cc:.3e}",
                line=dict(color="orange", dash="dot", width=2),
            ), row=3, col=1)

    # ── Toggle buttons (your original logic — trace indices updated)
    # Trace index map:
    #  0=NDMI Raw,  1=Mesonet Raw,  2=NDMI Norm,  3=Mesonet Norm,
    #  4=NDMI Log,  5=Mesonet Log,  6=Expanding r, 7=Significant,
    #  8=Cloud scatter, 9=Cloud trend
    def vis(raw=False, norm=False, log=False):
        v = [False] * 10
        if raw:  v[0], v[1] = True, True
        if norm: v[2], v[3] = True, True
        if log:  v[4], v[5] = True, True
        v[6] = v[7] = True   # correlation row always visible
        v[8] = v[9] = True   # cloud row always visible
        return v

    fig.update_layout(
        updatemenus=[
            dict(
                type="buttons", direction="left",
                x=0.0, y=1.07, xanchor="left", yanchor="top",
                buttons=[
                    dict(label="Raw",        method="update",
                         args=[{"visible": vis(raw=True)},
                               {"yaxis.title.text": "Raw Moisture Value"}]),
                    dict(label="Normalized", method="update",
                         args=[{"visible": vis(norm=True)},
                               {"yaxis.title.text": "Normalized Moisture (0–1)"}]),
                    dict(label="Log Scaled", method="update",
                         args=[{"visible": vis(log=True)},
                               {"yaxis.title.text": "Log Scaled Moisture"}]),
                ],
            )
        ],
        height=1050,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    fig.update_yaxes(title_text="Raw Moisture Value",            row=1, col=1)
    fig.update_yaxes(title_text="Pearson r", range=[-1.5, 1.5], row=2, col=1)
    fig.update_yaxes(title_text="NDMI Mean",                     row=3, col=1)
    fig.update_xaxes(title_text="Month", tickangle=45,           row=2, col=1)
    fig.update_xaxes(title_text="Cloud Cover (%)",               row=3, col=1)

    return fig


# ─────────────────────────────────────────────────────────────
# DASH APP  (minimal wrapper — needed for 120-station dropdown)
# ─────────────────────────────────────────────────────────────
app = dash.Dash(__name__, title="NDMI Correlation Dashboard")

app.layout = html.Div([
    html.Div([
        html.Div([
            html.Label("Station", style={"fontWeight": "600", "marginRight": "8px"}),
            dcc.Dropdown(
                id="station-select",
                options=[{"label": "All Stations", "value": "__ALL__"}]
                        + [{"label": s, "value": s} for s in ALL_STATIONS],
                value="__ALL__",
                clearable=False,
                style={"width": "260px", "display": "inline-block"},
            ),
        ], style={"display": "inline-block", "marginRight": "30px"}),


    ], style={"padding": "16px 24px", "background": "#f5f5f5",
              "borderBottom": "1px solid #ddd"}),

    dcc.Graph(id="main-figure", config={"displayModeBar": True}),
])


@callback(
    Output("main-figure", "figure"),
    Input("station-select", "value"),
)
def update_figure(station):
    master = build_master(station)
    master = add_derived_columns(master)
    return build_figure(master)


if __name__ == "__main__":
    app.run(debug=True, port=8050)