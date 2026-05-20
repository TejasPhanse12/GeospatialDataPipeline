# Project Plan - Soil Moisture Analysis

**Team:**
- Tejas Phanse (Lead)
- Qian Cheng (Seaqueue)
- Kumara Swamy Padari

**Stakeholder:** Rory Dunn, Aperture Space, Inc.

**Objective:** Quantify the correlation between Landsat-derived NDMI and Oklahoma Mesonet soil moisture readings.

---

## Stakeholder Involvement

Rory Dunn (Senior Platform Engineering Manager, Aperture Space) is our primary contact. He provided the Oklahoma Mesonet dataset and shared Zhang and Liang (2022) as a reference for our approach. His main question: how well does Landsat data correlate with actual soil moisture on the ground? We send updates via email and share outputs for feedback. Next update planned after the Mesonet-Landsat date matching is complete.

---


## Data Sources

| Source | Description |
|--------|-------------|
| Landsat 8/9 (AWS S3) | 30m satellite imagery via STAC API |
| Oklahoma Mesonet | Hourly soil moisture at 121 stations, 2022-2024 |

## Technical Approach

The pipeline works in three parts:

**Satellite data:** Landsat 8/9 imagery is accessed directly from AWS S3 via the STAC API without downloading full scene files. For a given area and date range, the pipeline extracts Band 5 (NIR) and Band 6 (SWIR) and computes NDMI:

```
NDMI = (Band 5 - Band 6) / (Band 5 + Band 6)
```

Cloud masking is applied using the QA pixel band. Current output is NDMI statistics (mean, min, max) per location and year.

**Mesonet data:** Oklahoma Mesonet soil moisture readings (2022-2024) from 121 stations, accessed via AWS S3. Stations record water content at 5 cm (TR05), 25 cm (TR25), and 60 cm (TR60) depths. NDMI values are being matched to Mesonet readings on Landsat overpass dates at each station location.

**Soil properties:** POLARIS soil properties (clay, sand, hydraulic conductivity, water holding capacity) at 30 meter resolution for Oklahoma are used to account for soil type variation. Initial EDA found r = 0.472 between clay content and average soil moisture across stations.

**Statistical Validation:** We used the **Pearson Correlation Coefficient (r)** to quantify the relationship between Landsat-derived NDMI and Mesonet TR05 (5cm soil moisture) readings. This method is chosen because:
- **Linearity:** It effectively captures the linear association between the soil's dielectric properties (affecting TR05) and its shortwave infrared reflectance (captured by NDMI).
- **Standardization:** Pearson's $r$ provides a scale-independent metric ranging from -1 to 1, allowing for direct comparison of correlation strength across 120+ diverse geographic locations in Oklahoma.
- **Significance Testing:** The method allows for the calculation of p-values, ensuring that the identified moisture trends are statistically significant and not the result of random atmospheric or sensor noise.
- **Benchmarking:** It is the most common metric used in remote sensing literature (e.g., Zhang and Liang, 2022) for validating satellite-derived moisture indices against ground-truth point sensors.

---

## Pipeline

The core of our data extraction is handled by `landsat_access.py`, which implements an efficient "cloud-native" approach to satellite imagery processing. Instead of downloading gigabytes of full Landsat scenes, it streams only the required pixels for our Areas of Interest (AOI) directly from AWS S3.

![PipelineFlow](supportingimage/workflow.png)

### Key Stages:

1.  **AOI Definition:** For each Oklahoma Mesonet station, we define a small spatial buffer (~55m) to create a target bounding box.
2.  **STAC Query & Filtering:** We query the Element84 STAC API to find all Landsat 8/9 scenes covering our AOI within the 2023-2024 period. Scenes are filtered to ensure at least 50% spatial coverage of our target area.
3.  **Cloud-Native Extraction:** Using `rasterio`'s windowed reading and AWS `boto3`, the script connects to requester-pays S3 buckets. It only reads the specific pixels within our AOI for the NIR (Band 5), SWIR1 (Band 6), and QA_PIXEL bands.
4.  **Quality Assurance:** The `QA_PIXEL` band is used to mask out pixels affected by clouds, dilated clouds, cirrus, cloud shadows, or snow.
5.  **NDMI Calculation:** We convert raw Digital Numbers (DN) to TOA reflectance using Landsat scaling factors and calculate the Normalized Difference Moisture Index (NDMI).
6.  **Data Persistence:** The results are aggregated into a temporal dataset (`moisture_data.csv`) and visualized as individual PNG plots and station-level animated GIFs.

---


## Risks

| Risk | Likelihood | Plan |
|------|------------|------|
| Landsat 16-day revisit creates sparse temporal coverage | High | Use all available scenes 2022-2024, aggregate by season |
| Cloud cover reduces usable scenes | Medium | Filter to scenes below 20% cloud cover |
| Spatial mismatch between 30m pixel and point sensor | Medium | Extract NDMI at exact station coordinates, note as limitation |
| Mesonet missing data for some stations | Low | Use stations with complete coverage, flag gaps |

