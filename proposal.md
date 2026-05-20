# Proposal: Soil Moisture Analysis

**Team:** Tejas Phanse, Qian Cheng (Seaqueue), Kumara Swamy Padari  
**Stakeholder:** Rory Dunn, Aperture Space, Inc.  
**Course:** DS 5500 / CS 7980 - Spring 2026, Northeastern University Roux Institute

## Story

Aperture Space is building new satellite sensors to measure soil moisture from space. Before launch, they need a pipeline that can validate satellite measurements against ground-truth data. Their question to us: how well does existing satellite data correlate with what soil sensors actually measure on the ground?

Soil moisture matters for agriculture, drought monitoring, and flood prediction. Current satellite products operate at coarse resolution (SMAP at 9-36 km) or rely on radar (Sentinel-1 at 1 km). Landsat 8/9 offers free imagery at 30 meter resolution but has rarely been used for soil moisture validation. That is the gap we are working on.

## What We Are Doing

We are building a pipeline that extracts Landsat NDMI (Normalized Difference Moisture Index) for a given area and correlates it with soil moisture readings from the Oklahoma Mesonet.

NDMI is computed from Landsat 8/9 Band 5 (NIR) and Band 6 (SWIR):

```
NDMI = (Band 5 - Band 6) / (Band 5 + Band 6)
```

Higher NDMI means more moisture. The pipeline pulls Landsat imagery directly from AWS S3 via the STAC API without downloading full scenes. For any location and time period it returns NDMI statistics (mean, min, max) per year.

For ground truth, we are using soil moisture readings from 121 Oklahoma Mesonet stations (2022-2024), accessed via AWS S3. Stations measure water content at 5, 25, and 60 cm depths. We are matching these readings to Landsat overpass dates at each station location to build a paired dataset for correlation analysis.

We are also incorporating POLARIS soil properties (clay, sand, hydraulic conductivity, water holding capacity) for Oklahoma at 30 meter resolution. Our initial analysis found a Pearson correlation of r = 0.472 between clay content and average soil moisture across stations, which shows soil type affects how satellite signals should be read.

## Final Goal

Build a pipeline that:

1. Takes a geographic area and date range as input
2. Extracts Landsat NDMI values for that area across multiple years
3. Matches NDMI with Oklahoma Mesonet soil moisture readings on the same dates
4. Quantifies the correlation between NDMI and ground-truth measurements

The end result gives Aperture Space a clear answer on how well satellite data reflects actual soil moisture, and a pipeline they can adapt for their own sensors.

## Data

| Source | Description |
|--------|-------------|
| Landsat 8/9 (AWS S3) | 30m satellite imagery accessed via STAC API |
| Oklahoma Mesonet | Hourly soil moisture at 121 stations, 2022-2024 |
| POLARIS | 30m soil properties for Oklahoma, 13 variables (Duke University) |


