import os
import json
import logging
import concurrent.futures
from datetime import datetime
from typing import List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import numpy as np
import xarray as xr
import rioxarray
import rasterio
import dask
import odc.stac
import boto3

from shapely.geometry import box, shape
from pystac import Item
#from utils.gcs import upload_items_to_gcs


STAC_API = "https://earth-search.aws.element84.com/v1"

logger = logging.getLogger(__name__)


# TODO: We use stuff like this in multiple places, at some point we should consolidate 
# Retry configuration
def get_retry_session(retries=5, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504)):
    """
    Returns a session with retry logic for HTTP requests.
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


def fetch_landsat_metadata(aoi: List[float], start_date: str, end_date: str):
    """
    Fetch landsat metadata for a given AOI and time range using the STAC API with pagination and retry support.

    Args:
        aoi (List[float]): Area of interest [min_lon, min_lat, max_lon, max_lat].
        start_date (str): Start date in 'YYYY-MM-DD' format.
        end_date (str): End date in 'YYYY-MM-DD' format.
    """
    search_endpoint = f"{STAC_API}/search"
    start_datetime = f"{start_date}T00:00:00Z"
    end_datetime = f"{end_date}T23:59:59Z"

    payload = {
        "collections": ["landsat-c2-l2"],
        "bbox": aoi,
        "datetime": f"{start_datetime}/{end_datetime}",
        "limit": 100,
    }

    session = get_retry_session()  # Use retry-enabled session

    all_features = []
    next_payload = payload  # Initial payload for the first request

    while next_payload:
        try:
            # Request metadata
            response = session.post(search_endpoint, json=next_payload, timeout=10)
            response.raise_for_status()
            response_json = response.json()

            # Append features from the current page
            features = response_json.get("features", [])

            # Filter only images that have "OLI" or "TIRS" in the instruments list
            # This ensures we are getting landsat 8 or 9 data
            filtered_features = [
                feature for feature in features 
                if any(inst in feature["properties"].get("instruments", []) for inst in ["oli", "tirs"])
            ]

            all_features.extend(filtered_features)

            # Get the next payload for pagination
            next_payload = None
            for link in response_json.get("links", []):
                if link.get("rel") == "next":
                    next_payload = link.get("body")  # Use the body field from the next link
                    break

            logging.info(f"Fetched {len(filtered_features)} features, total collected: {len(all_features)}")

        except requests.exceptions.RequestException as e:
            logging.info(f"Request failed: {e}")
            break

    logging.info(f"Total tiles found: {len(all_features)}")

    # Create a Shapely geometry for the AOI
    aoi_polygon = box(*aoi)

    # Filter tiles by coverage
    filtered_tiles = []
    for feature in all_features:
        tile_geometry = shape(feature["geometry"])
        intersection = tile_geometry.intersection(aoi_polygon)
        coverage_percentage = (intersection.area / aoi_polygon.area) * 100

        if coverage_percentage >= 50:
            filtered_tiles.append(feature)

    logging.info(f"Tiles covering 50% of AOI: {len(filtered_tiles)}")
    return filtered_tiles


def process_landsat_scene(item: Item, output_dir: str, da_mask: xr.core.dataarray.DataArray, cloud_threshold: float = 15., metadata_file: str = 'baseline.json'):
    """
    Download bands, clip them to AOI, calculate cloudmask, and save them to one GeoTIFF.
    """
    # Convert the item dict to a pystac.Item
    item = Item.from_dict(item)

    # Extract STAC item ID
    item_id = item.id
    logging.info(f"Processing Landsat scene: {item_id}")

    combined_tif_path = os.path.join(output_dir, f"{item_id}_derived.tif")
    if os.path.exists(combined_tif_path):
        return

    # Configure AWS credentials
    session = boto3.Session(
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('SENTINEL_1_AWS_REGION', 'eu-central-1')
    )

    # Set the GDAL configuration options with how to retry, and some other handling
    # https://gdal.org/en/stable/user/configoptions.html
    gdal_config = dict(
        # The following options are the same as GDAL_CLOUD_DEFAULTS in odc.stac
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MAX_RETRY="10",
        GDAL_HTTP_RETRY_DELAY="0.5",
        CPL_CURL_VERBOSE="YES",
        AWS_REQUEST_PAYER="requester",
    )

    if os.getenv('ENV') not in ['prd', 'stg']:
        # Debug if environment is not prod or staging
        gdal_config.update(
            dict(
                CPL_DEBUG="ON",
            )
        )

    with rasterio.Env(**gdal_config), concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        logger.info("Loading dataset")
        logger.info("Checking available bands...")

        # Define needed bands
        required_bands = ["coastal", "blue", "green", "red", "nir08", "swir16", "swir22", "lwir11", "qa_pixel"]

        # Check available bands in STAC item
        missing_bands = [b for b in required_bands if b not in item.assets]

        # Skip tile if bands are missing
        if missing_bands:
            logger.warning(f"Skipping scene {item.id} due to missing bands: {missing_bands}")
            return

        dataset = odc.stac.load(
            [item],
            bands=required_bands,
            # Reproject to match the mask
            like=da_mask,
            # Use nearest-neighbor resampling
            resampling=rasterio.enums.Resampling.nearest.name,
            # Use a thread pool for better performance
            pool=pool,
            # This STAC server doesn't specify nodata so do it here
            nodata=0.,
        ).rename(
            {
                "coastal": "B01",  # Aerosol
                "blue": "B02",  # Blue
                "green": "B03",  # Green
                "red": "B04",  # Red
                "nir08": "B05",  # Near infrared
                "swir16": "B06",  # SWIR-1 (~1.6µm)
                "swir22": "B07",  # SWIR-2 (~2.2µm)
                "lwir11": "B10",  # Thermal Infrared (TIRS1)
                "qa_pixel": "QA_Pixel",
            }
        )
        logger.info("Loaded dataset")

    # Pixel definitions available here under "Landsat Collection 2 Level-1 and Level-2 QA Bands"
    # https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands
    # Additional detail here on page 13:
    # https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/media/files/LSDS-1619_Landsat8-9-Collection2-Level2-Science-Product-Guide-v6.pdf
    # This is the most conservative interpretation of the pixel values
    valid_qa_pixel_values = [
        21824,  # Clear with lows set
        21888,  # Water with lows set
    ]

    # 1 is the fill value (no data)
    no_data_pixels = dataset.QA_Pixel == 1
    # Cloud pixels are values not in the valid set that are also not no data
    cloud_pixels = ~dataset.QA_Pixel.isin(valid_qa_pixel_values) & ~no_data_pixels

    num_cloud_pixels = cloud_pixels.data.sum()
    num_valid_pixels = (~no_data_pixels).data.sum()

    if num_valid_pixels == 0:
        logger.info("Skipping scene %s due to no valid pixels", item_id)
    cloud_coverage = num_cloud_pixels / num_valid_pixels * 100.
    logger.info(f"Cloud coverage is {cloud_coverage:.2f}%")
    if cloud_coverage > cloud_threshold:
        logger.info(f"Skipping scene {item_id} because cloud coverage exceeds threshold of %s", cloud_threshold)
        return

    # These values comes from the STAC API
    scale_factor = 0.0000275
    offset = -0.2
    # B10 has a different offset because it's unit is Kelvin
    b10_scale_factor = 0.00341802
    b10_offset = 149

    landsat_bands = np.stack(
        [
            dataset["B01"].values * scale_factor + offset,  # Coastal/Aerosol
            dataset["B02"].values * scale_factor + offset,  # Blue
            dataset["B03"].values * scale_factor + offset,  # Green
            dataset["B04"].values * scale_factor + offset,  # Red
            dataset["B05"].values * scale_factor + offset,  # Near infrared
            dataset["B06"].values * scale_factor + offset,  # SWIR-1 (~1.6µm)
            dataset["B07"].values * scale_factor + offset,  # SWIR-2 (~2.2µm)
            dataset["B10"].values * b10_scale_factor + b10_offset,  # Thermal Infrared (TIRS1)
        ],
        axis=0,
    )

    # Replace NaNs with median values (avoid ML errors)
    landsat_bands = np.nan_to_num(landsat_bands, nan=np.nanmedian(landsat_bands))

    # Ensure all values are positive
    landsat_bands[landsat_bands < 0] = 0

    if isinstance(landsat_bands, np.ndarray):
        landsat_bands = np.squeeze(landsat_bands)  # For NumPy arrays

    else:
        raise TypeError(f"Unexpected data type: {type(landsat_bands)}")

    # This uses the more conventional Landsat cloudmask and not Cloudsen12
    # Set to 1 where we've identified clouds, 0 otherwise
    cloud_mask = xr.where(cloud_pixels, 1, 0)
    cloud_mask.rio.write_nodata(0, inplace=True)
    dataset = dataset.assign(Cloudmask=cloud_mask)

    # Get the satellite number
    satellite = item.properties["platform"][-1]
    dataset.attrs = {
        "title": f"Landsat {satellite} Processed Dataset",
        "date_created": datetime.now().isoformat(),
        "scene_properties": json.dumps(item.properties),
    }

    with dask.config.set(**{"array.slicing.split_large_chunks": True}):
        dataset.squeeze().rio.to_raster(
            combined_tif_path,
            driver="GTiff",
            dtype=np.float32,
            compress="deflate",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )

    logging.info("Derived GeoTIFF saved at: %s", combined_tif_path)


# TODO: Mostly copied from the Sentinel-2 code. We should ultimately have a reusable
# interface for doing this.
def process_landsat_data(aoi, start_date, end_date, metadata_file='baseline.json'):
    """
    Processes Landsat 8/9 data for a given AOI and date range, saves them locally,
    and uploads the results to GCS.

    Args:
    aoi (list): Area of interest [min_lon, min_lat, max_lon, max_lat].
    start_date (str): Start date in 'YYYY-MM-DD' format.
    end_date (str): End date in 'YYYY-MM-DD' format.
    metadata_file (str): Path to the metadata JSON file containing 'rdir'.
    """
    # Fetch metadata for Landsat images
    items = fetch_landsat_metadata(aoi, start_date, end_date)

    # If we didn't get any matches we can stop here
    if not items:
        return []

    # Establish file system
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    rdir = metadata["rdir"]
    output_dir = os.path.join(rdir, "landsat")
    os.makedirs(output_dir, exist_ok=True)

    mask = f'{rdir}/spatial/gee_in/cids/1/orig_mask_latlon.tif'
    da_mask = rioxarray.open_rasterio(mask)

    for idx, item in enumerate(items, start=1):
        logger.info("Processing item %d/%d: %s", idx, len(items), item["id"])
        process_landsat_scene(item, output_dir, da_mask)

    # Collect the output files (both directories and files)
    output_items = [
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if os.path.isdir(os.path.join(output_dir, f)) or f.endswith(('.tif', '.tiff'))
    ]

    # Get the GCS directory
    # I don't really like this but it should be okay for now
    # We don't really pass data around in an efficient manner in general but thats a bigger todo
    if rdir.startswith("/app/"):
        rdir = rdir[len("/app/"):]
    base_path = "/".join(rdir.split("/")[:2])
    gcs_path = os.path.join(base_path, 'landsat')

    # Upload the items to GCS
    #uploaded_items = upload_items_to_gcs(output_items, gcs_path)
    #logging.info("Uploaded items to GCS: %s", uploaded_items)

    return output_items
