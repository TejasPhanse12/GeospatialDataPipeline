import folium
from folium.plugins import Draw
import geopandas as gpd
import json
import webbrowser
import os

# ----------------------------
# Load US States (5m resolution)
# ----------------------------
states_url = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_5m.zip"
states = gpd.read_file(states_url)

# Remove territories (optional)
states = states[~states["STUSPS"].isin(["PR", "GU", "VI", "MP", "AS"])]

# ----------------------------
# Load US Counties (5m resolution)
# ----------------------------
counties_url = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_5m.zip"
counties = gpd.read_file(counties_url)

# Keep only counties from 50 states
counties = counties[counties["STATEFP"].isin(states["STATEFP"])]

# ----------------------------
# Convert CRS to WGS84 (for Folium)
# ----------------------------
states = states.to_crs(epsg=4326)
counties = counties.to_crs(epsg=4326)

print("States loaded:", len(states))
print("Counties loaded:", len(counties))

# Create map centered on USA
m = folium.Map(
    location=[39.5, -98.35],
    zoom_start=4,
    tiles="Esri.WorldImagery"
)

# Add States layer
folium.GeoJson(
    states,
    name="States",
    style_function=lambda x: {
        "fillColor": "none",
        "color": "blue",
        "weight": 1
    },
    tooltip=folium.GeoJsonTooltip(fields=["NAME"], aliases=["State:"])
).add_to(m)

# Add Counties layer
folium.GeoJson(
    counties,
    name="Counties",
    style_function=lambda x: {
        "fillColor": "none",
        "color": "black",
        "weight": 0.5
    }
).add_to(m)

# ----------------------------
# Add County Names as Labels
# ----------------------------
for _, row in counties.iterrows():
    centroid = row.geometry.centroid
    folium.Marker(
        location=[centroid.y, centroid.x],
        icon=folium.DivIcon(
            html=f"""
            <div style="font-size:6pt; color:black;">
                {row['NAME']}
            </div>
            """
        )
    ).add_to(m)

# --------------------------------
# Add Draw Tool
# --------------------------------
draw = Draw(
    export=True,  # Adds export button
    draw_options={
        "polyline": False,
        "circle": False,
        "rectangle": True,   # for AOI bounding box
        "polygon": True,
        "marker": True,
        "circlemarker": False,
    },
    edit_options={"edit": True},
    filename="drawn_data.geojson",
)

draw.add_to(m)

# Save and open
file_path = "maps/aoi_usa_map.html"
m.save(file_path)

# Automatically open in browser
webbrowser.open("file://" + os.path.realpath(file_path))