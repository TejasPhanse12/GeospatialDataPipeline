# load libraries
import os
import json
import logging
from datetime import datetime
from typing import List

import matplotlib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import numpy as np
import pandas as pd
import geopandas as gpd
from pyproj import Transformer
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.animation as animation
from matplotlib.animation import FFMpegWriter as ffmpeg

import rasterio
from rasterio.session import AWSSession
import concurrent.futures
from rasterio.transform import xy
from rasterio.windows import from_bounds as window_from_bounds
from rasterio.windows import transform as window_transform
from rasterio.warp import transform_bounds
import boto3

from shapely.geometry import box, shape
from pystac import Item

#--------------- SETTING UP GLOBAL VARIABLES -----------------
# Loading Coordinate data from geojason file
coordinates_gdf = gpd.read_file("coordinates/drawn_data.geojson")

# STAC API endpoint for Landsat data
STAC_API = "https://earth-search.aws.element84.com/v1"

# Required bands for Landsat 8/9 Level-2 data {Bands written to the output GeoTIFF (in order → band indices 1–9)}
REQUIRED_BANDS = [
    "coastal",   # B01 – Aerosol
    "blue",      # B02
    "green",     # B03
    "red",       # B04
    "nir08",     # B05 – NIR  ← used for NDMI / soil moisture
    "swir16",    # B06 – SWIR-1  ← used for NDMI
    "swir22",    # B07 – SWIR-2
    "lwir11",    # B10 – Thermal (Kelvin)
    "qa_pixel",  # QA  – cloud / fill flags
]

scene_links_dataset = {
    "station_name": [],
    "scene_id": [],
    "scene_datetime": [],
    "scene_platform": [],
    "scene_lat" : [],
    "scene_lon" : [],
    "scene_cloud_cover": [],
    "blue_link": [],
    "green_link": [],
    "red_link": [],
    "nir08_link": [],
    "swir16_link": [],
    "swir22_link": [],
    "qa_pixel_link": []

}

mositure_analysis_data = {
    "scene_id" : [],
    "date" : [],
    "lat" : [],
    "lon" : [],
    "scene_cloud_cover" : [],
    "nir08" : [],
    "swir16" : [],
    "swir22" : [],
    "ndmi_min" : [],
    "ndmi_mean" : [],
    "ndmi_max" : []
}

# --------------- SETTING UP LOGGING FOR DEBUGGING -----------------
# Setting up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ------------- SETTING BOTO3 and AWS SESSION FOR TIFF DOWNLOAD ----------------
access_key = os.getenv("AWS_ACCESS_KEY_ID")
secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
boto_session = boto3.Session(
        aws_access_key_id    = access_key,
        aws_secret_access_key= secret_key,
        region_name          = "us-west-2",
    )
aws_session = AWSSession(boto_session, requester_pays=True)

# Low (Red), Medium (Yellow), High (Blue)
colors = ["red", "yellow", "blue"]

# 'moisture_map' is the name of the custom map
moisture_cmap = mcolors.LinearSegmentedColormap.from_list("moisture_map", colors)

# ── QA_PIXEL Bit flags (Landsat Collection 2) ─────────────────────────
FILL          = (1 << 0)   # Bit 0 — no data at all
DILATED_CLOUD = (1 << 1)   # Bit 1 — cloud buffer zone
CIRRUS        = (1 << 2)   # Bit 2 — thin/high-altitude cloud
CLOUD         = (1 << 3)   # Bit 3 — opaque cloud
CLOUD_SHADOW  = (1 << 4)   # Bit 4 — shadow cast by cloud
SNOW          = (1 << 5)   # Bit 5 — snow/ice (include if AOI is arid → low risk)

CLOUD_MASK_BITS = FILL | DILATED_CLOUD | CIRRUS | CLOUD | CLOUD_SHADOW | SNOW

ndmi_readings = {
        "station_name": [],
        "lat": [],
        "lon": [],
        "scene_id": [],
        "date": [],
        "cloud_cover": [],
        "ndmi_mean": [],
    }

# ── Step 1: STAC query (mirrors fetch_landsat_metadata) ──────────────────────
# We use a custom function with retries to handle potential network issues and pagination.
def _retry_session(retries=5, backoff=0.3):
    session = requests.Session()
    retry = Retry(
        total=retries, read=retries, connect=retries,
        backoff_factor=backoff,
        status_forcelist=(500, 502, 503, 504),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# The main function to fetch scenes from the STAC API, handling pagination and filtering by AOI coverage.
def fetch_scenes(aoi: List[float], payload: dict) -> List[dict]:
    """
    Query the STAC API for Landsat 8/9 scenes that cover ≥50 % of the AOI.

    Returns a list of raw GeoJSON feature dicts (same shape as what
    fetch_landsat_metadata() returns in landsat.py).
    """
    endpoint = f"{STAC_API}/search"
    session      = _retry_session()
    all_features = []
    next_payload = payload

    while next_payload:
        try:
            resp = session.post(endpoint, json=next_payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as exc:
            logger.error("STAC request failed: %s", exc)
            break

        features = data.get("features", [])

        # Keep only Landsat 8/9 (OLI / TIRS instruments)
        oli_tirs = [
            f for f in features
            if any(inst in f["properties"].get("instruments", []) for inst in ["oli", "tirs"])
        ]
        all_features.extend(oli_tirs)
        logger.info("Page: %d scenes (OLI/TIRS), running total: %d", len(oli_tirs), len(all_features))

        # Follow pagination link
        next_payload = None
        for link in data.get("links", []):
            if link.get("rel") == "next":
                next_payload = link.get("body")
                break

    logger.info("STAC total: %d scenes before coverage filter", len(all_features))

    # Filter by AOI coverage ≥ 50 %  (mirrors landsat.py)
    aoi_poly = box(*aoi)
    covered  = []
    for feat in all_features:
        tile_geom    = shape(feat["geometry"])
        intersection = tile_geom.intersection(aoi_poly)
        pct          = (intersection.area / aoi_poly.area) * 100
        if pct >= 50:
            covered.append(feat)

    logger.info("Scenes covering ≥50 %% of AOI: %d", len(covered))
    return covered

# ── Step 2: Inspect asset URLs (bonus utility) ────────────────────────────────
def inspect_scene_assets(station, feature: dict):
    """
    Print the S3 URLs for every band asset in a STAC feature.
    Useful for verifying what will be downloaded before you incur S3 costs.
    """
    item = Item.from_dict(feature)

    scene_id = item.id
    scene_datetime = item.datetime
    scene_platform = item.properties.get("platform", "unknown")
    scene_cloud_cover = item.properties.get("eo:cloud_cover")

    centroid = item.properties.get("proj:centroid", {})
    lat = centroid.get("lat")
    lon = centroid.get("lon")

    blue_link = ""
    green_link = ""
    red_link = ""
    nir08_link = ""
    swir16_link = ""
    swir22_link = ""
    qa_pixel_link = ""

    for band in REQUIRED_BANDS:
        asset = item.assets.get(band)
        if asset:
            if band == "blue":
                blue_link = asset.href
            elif band == "green":
                green_link = asset.href
            elif band == "red":
                red_link = asset.href
            elif band == "nir08":
                nir08_link = asset.href
            elif band == "swir16":
                swir16_link = asset.href
            elif band == "swir22":
                swir22_link = asset.href
            elif band == "qa_pixel":
                qa_pixel_link = asset.href
        else:
            print(f"  {band:<12} → *** MISSING ***")

    # Append values to dataset
    scene_links_dataset["station_name"].append(station)
    scene_links_dataset["scene_id"].append(scene_id)
    scene_links_dataset["scene_datetime"].append(scene_datetime)
    scene_links_dataset["scene_platform"].append(scene_platform)
    scene_links_dataset["scene_lat"].append(np.mean(lat))
    scene_links_dataset["scene_lon"].append(np.mean(lon))
    scene_links_dataset["scene_cloud_cover"].append(scene_cloud_cover)
    scene_links_dataset["blue_link"].append(blue_link)
    scene_links_dataset["green_link"].append(green_link)
    scene_links_dataset["red_link"].append(red_link)
    scene_links_dataset["nir08_link"].append(nir08_link)
    scene_links_dataset["swir16_link"].append(swir16_link)
    scene_links_dataset["swir22_link"].append(swir22_link)
    scene_links_dataset["qa_pixel_link"].append(qa_pixel_link)


# Calculate soil moisture and return the data for plotting or animation
def get_soil_moisture_data(row, aoi_list, aws_session):
    try:
        # Load scene links from CSV
        if not row.empty:
            scene_id = row["scene_id"]
            scene_date = row["scene_datetime"]
            lat = row["scene_lat"]
            lon = row["scene_lon"]
            
            print(f"Opening Scene: {scene_id}")
                    
            # Use rasterio.Env with the AWS session to access S3 links
            with rasterio.Env(aws_session):
                with rasterio.open(row["nir08_link"]) as nir_src, \
                     rasterio.open(row["swir16_link"]) as swir16_src, \
                     rasterio.open(row["qa_pixel_link"]) as qa_pixel_src:
                    
                    # Transform AOI bounds from EPSG:4326 to source CRS (e.g., UTM)
                    left, bottom, right, top = aoi_list
                    dst_left, dst_bottom, dst_right, dst_top = transform_bounds(
                                "EPSG:4326", nir_src.crs, left, bottom, right, top
                            )
                            
                    # Define window to read based on the transformed bounds
                    window = window_from_bounds(dst_left, dst_bottom, dst_right, dst_top, nir_src.transform)
                            
                    # Reading Data from .TIF source bands (raw DN values) only within window
                    nir_DN    = nir_src.read(1, window=window, boundless=True, fill_value=1).astype(float)
                    swir16_DN = swir16_src.read(1, window=window, boundless=True, fill_value=1).astype(float)
                    qa_DN     = qa_pixel_src.read(1, window=window, boundless=True, fill_value=1).astype(np.uint16)


                    # Read QA Pixel Band to ensure the qixel quality
                    qa_DN = qa_pixel_src.read(1, window=window, boundless=True, fill_value=0).astype(np.uint16)
                    valid_mask = (qa_DN & CLOUD_MASK_BITS) == 0

                    # Mask out invalid pixels in the NIR and SWIR16 bands
                    nir_DN[~valid_mask] = np.nan
                    swir16_DN[~valid_mask] = np.nan

                    # Apply Landsat scaling (DN → reflectance)
                    nir_reflectance = (nir_DN * 0.0000275) - 0.2
                    swir16_reflectance = (swir16_DN * 0.0000275) - 0.2

                    # Clip to valid reflectance range [0, 1]
                    nir_reflectance = np.clip(nir_reflectance, 0, 1)
                    swir16_reflectance = np.clip(swir16_reflectance, 0, 1)

                    with np.errstate(divide='ignore', invalid='ignore'):
                        # NDMI 
                        ndmi = (nir_reflectance - swir16_reflectance) / (nir_reflectance + swir16_reflectance)
                        ndmi = np.clip(ndmi, -1, 1)

                        # Mask any remaining invalid values
                        ndmi[np.isnan(nir_reflectance) | np.isnan(swir16_reflectance)] = np.nan

                        mean_ndmi = np.nanmean(ndmi)
                            
                    # printing the shape of the NDMI array to verify it's correct
                    print(f"NDMI shape: {ndmi.shape} \tMean NDMI: {mean_ndmi:.4f}")
                    
                    return {
                        "lat": lat,
                        "lon": lon,
                        "ndmi": ndmi,
                        "scene_id": scene_id,
                        "date": scene_date,
                        "mean_ndmi": mean_ndmi,
                        "cloud_cover": row["scene_cloud_cover"]
                    }
        else:
            print("Row is empty.")
            return None
    except Exception as e:
        print(f"Error accessing TIF from AWS: {e}")
        return None

# Original function refactored to use the new data fetcher
def soil_moisture_plot (station, row, aoi_list, aws_session):
    data = get_soil_moisture_data(row, aoi_list, aws_session)
    if data:
        ndmi = data["ndmi"]
        scene_id = data["scene_id"]
        mean_ndmi = data["mean_ndmi"]
        lat = data["lat"]
        lon = data["lon"]

        ndmi_readings["station_name"].append(station)
        ndmi_readings["lat"].append(lat)
        ndmi_readings["lon"].append(lon)
        ndmi_readings["scene_id"].append(scene_id)
        ndmi_readings["date"].append(data["date"])
        ndmi_readings["cloud_cover"].append(data["cloud_cover"])
        ndmi_readings["ndmi_mean"].append(mean_ndmi)

        # Plotting the data
        plt.figure(figsize=(10, 8))
        plt.imshow(ndmi, cmap= moisture_cmap, vmin=-1, vmax=1)
        plt.colorbar(label='Moisture Index (NDMI)')
        plt.title(f"Landsat Scene - {scene_id}\n(Windowed View of AOI)")
        plt.xlabel("Columns")
        plt.ylabel("Rows")
        plt.savefig(f"images/{scene_id}.png", dpi=300)
        plt.close()
        return data
    return None

def create_soil_moisture_animation(station, ndmi_data_list):
    """
    Creates an MP4 animation from a list of NDMI data.
    """
    output_path= f"gif/{station}_soil_moisture_change.mp4"
    if not ndmi_data_list:
        print("No data available to create animation.")
        return

    print(f"Creating animation with {len(ndmi_data_list)} frames...")
    # Use a specific figure to avoid issues with other plots
    fig, ax = plt.subplots(figsize=(10, 8))

    # Initialize with first frame
    first_data = ndmi_data_list[0]
    im = ax.imshow(first_data["ndmi"], cmap=moisture_cmap, vmin=-1, vmax=1)
    plt.colorbar(im, label='Moisture Index (NDMI)')
    title = ax.set_title(f"Landsat Scene - {first_data['scene_id']}\nDate: {first_data['date']}")
    ax.set_xlabel("Columns")
    ax.set_ylabel("Rows")

    def update(frame):
        data = ndmi_data_list[frame]
        im.set_array(data["ndmi"])
        title.set_text(f"Landsat Scene - {data['scene_id']}\nDate: {data['date']}")
        return [im, title]

    ani = animation.FuncAnimation(fig, update, frames=len(ndmi_data_list), interval=500, blit=False)

    # Always save as GIF using PillowWriter
    gif_output_path = output_path.replace(".mp4", ".gif")
    try:
        ani.save(gif_output_path, writer='pillow', fps=1)
        print(f"Animation saved as GIF to {gif_output_path}")
    except Exception as gif_e:
        print(f"Error saving GIF animation: {gif_e}")

    plt.close(fig)


if __name__ == "__main__":

    # Load and preprocess Mesonet data 
    # Mesonet Data for 2024
    mesonet_data_2024 = pd.read_csv("mesonet_data/mesonet_statewide_hourly_2024(in).csv")
    mesonet_data_2024["Date"] = pd.to_datetime(mesonet_data_2024["Date"],format = "mixed")
    mesonet_data_2024["Time"] = mesonet_data_2024["Date"].dt.time
    mesonet_data_2024["Month_Year"] = mesonet_data_2024["Date"].dt.to_period("M")
    mesonet_data_2024["Date"] = mesonet_data_2024["Date"].dt.date

    # Mesonet Data for 2023
    mesonet_data_2023 = pd.read_csv("mesonet_data/mesonet_statewide_hourly_2023.csv")
    mesonet_data_2023["Date"] = pd.to_datetime(mesonet_data_2023["Date"],format = "mixed")
    mesonet_data_2023["Time"] = mesonet_data_2023["Date"].dt.time
    mesonet_data_2023["Month_Year"] = mesonet_data_2023["Date"].dt.to_period("M")
    mesonet_data_2023["Date"] = mesonet_data_2023["Date"].dt.date

    # Combine 2023 and 2024 data
    mesonet_data = pd.concat([mesonet_data_2023, mesonet_data_2024], ignore_index=True)

    #Station list
    station_list = mesonet_data["station_name"].unique()
    logger.info(f"Available stations in Mesonet data: {len(station_list)} \n{station_list}")
    
    #Enter station name to filter mesonet data
    #station_list = ["Copan", "Tulsa"]
    
    year_list = [2023,2024]

    for station in station_list:

        logger.info (f"\nProcessing station: {station}")

        station_data = mesonet_data[mesonet_data["station_name"] == station].copy()

        lat = station_data["LAT"].iloc[0]
        lon = station_data["LON"].iloc[0]

        buffer = 0.00045  # ~55m at mid-latitudes
        min_lat = lat - buffer
        max_lat = lat + buffer
        min_lon = lon - buffer
        max_lon = lon + buffer

        aoi_list = [min_lon, min_lat, max_lon, max_lat] 

        print("Bounding Box (min_lat, min_lon, max_lat, max_lon):\n",aoi_list,"\n")

        # Fetch Landsat data for the given coordinates and dates
        #start_date = input("Enter the start date (YYYY-MM-DD): ")
        #end_date = input("Enter the end date (YYYY-MM-DD): ")

        for year in year_list:
            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"
            start_datetime = f"{start_date}T00:00:00Z"
            end_datetime = f"{end_date}T23:59:59Z"

            logger.info(f"\nFetching Landsat scenes for {station} from {start_date} to {end_date}...\n")
            
            # Setting data parameters
            param ={
                "collections": ["landsat-c2-l2"],
                "bbox": aoi_list,
                "datetime": f"{start_datetime}/{end_datetime}",
                "limit": 1000
            }
            scenes = fetch_scenes(aoi_list, param)
            logger.info(f"Total scenes fetched: {len(scenes)}")
            # Save scenes to a JSON file for later use
            with open(f"data/landsat_scenes_{start_date}_{end_date}.json", "w") as f:
                json.dump(scenes, f, indent=2)
            
            logger.info(f"Scenes saved to data/landsat_scenes_{start_date}_{end_date}.json\n")
            # Sorting images out that has low cloud cover 
            scenes.sort(key = lambda x: x["properties"].get("eo:cloud_cover", 999))
            if len(scenes) > 0:
                for scene in scenes:  
                    inspect_scene_assets(station, scene)
                
        # convert dict to dataframe:
        scene_links_dataset_df = pd.DataFrame(scene_links_dataset)
        scene_links_dataset_df.to_csv("data/scene_links.csv")
        logger.info("Saving all the scenes into a dataframe")
        logger.info(f"DataFrame shape: {scene_links_dataset_df.shape}")
        logger.info(f"\n{scene_links_dataset_df}")


    # Load scene links if available
    scene_links = pd.read_csv("data/scene_links.csv")
    scene_links.sort_values("scene_datetime", inplace=True)  # Sort by date for chronological processing

    for station in station_list:

        # station specific
        scenes = scene_links[scene_links["station_name"] == station].copy()

        lat = scenes["scene_lat"].iloc[0]
        lon = scenes["scene_lon"].iloc[0]

        buffer = 0.00045  # ~55m at mid-latitudes
        min_lat = lat - buffer
        max_lat = lat + buffer
        min_lon = lon - buffer
        max_lon = lon + buffer

        aoi_list = [min_lon, min_lat, max_lon, max_lat] 

        if aws_session:
            print("AWS Session established successfully.\n")
            
            ndmi_data_list = []
            for count, (_, row) in enumerate (scenes.iterrows()):  # Loop can be extended to multiple scenes
                # Process scene and save individual plot
                data = soil_moisture_plot(station, row, aoi_list, aws_session)

                if data:
                    ndmi_data_list.append(data)
                
                # if count > 10:
                #     break
            
            # Create animation from all processed scenes
            if ndmi_data_list:
                create_soil_moisture_animation(station, ndmi_data_list)
            else:
                print("Could not establish AWS session. Please ensure AccessCredentials.csv is correctly formatted.")
        
    
    ndmi_df = pd.DataFrame(ndmi_readings)
    ndmi_df.to_csv("data/moisture_data.csv", index=False)
    logger.info("Soil moisture data saved to data/soil_moisture_data.csv")







