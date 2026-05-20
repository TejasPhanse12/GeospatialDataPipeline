# Literature Review: Satellite-Based Soil Moisture Estimation and Validation

## Introduction

Soil moisture is a critical variable in hydrology, agriculture, and climate science, influencing water and energy exchange at the land-atmosphere interface. Accurate estimation of soil moisture at high spatial and temporal resolution remains a challenge due to sparse ground-based observation networks and limitations of individual remote sensing platforms. This review covers the current state of satellite-based soil moisture estimation, ground-truth validation methods, and approaches relevant to our project: correlating Landsat-derived NDMI with ground-truth measurements from the Oklahoma Mesonet.

## Satellite Remote Sensing for Soil Moisture

### Synthetic Aperture Radar (SAR) Approaches

Synthetic Aperture Radar is widely used for soil moisture retrieval because it works in all weather conditions, day or night. Balenzano et al. (2021) validated a Sentinel-1 soil moisture product at 1 km resolution against 167 ground stations across Europe, America, and Australia (2015-2020). They used a Short Term Change Detection algorithm on C-band VV and VH polarization data. They flagged a problem that also applies to our work: the spatial mismatch between a point sensor on the ground and a satellite pixel overhead.

Rahmati et al. (2025) reviewed ten years of Sentinel-1 retrieval work and found AI-based methods promising but limited by interpretability, dependence on large training datasets, and compute cost. They recommended combining Sentinel-1 with optical data for better results.

Fan et al. (2025) built a global 1 km soil moisture product from Sentinel-1 for 2016-2022, achieving an unbiased RMSD of 0.077 m3/m3 against ground observations.

### Optical and Multispectral Approaches

Optical remote sensing gives different but complementary information to SAR. Sadeghi et al. (2020) used Sentinel-2 with the OPTRAM model and got r = 0.73 to 0.80 for soil moisture using NDMI and NDVI as inputs, though the model tended to overestimate at medium to high moisture levels.

El Hajj et al. (2023) showed that combining Sentinel-1 radar with Sentinel-2 optical data at 1 km using neural networks trained with Water Cloud Model simulations gave better results than either sensor alone.

### Spectral Indices for Soil Moisture

For optical sensors like Landsat 8/9 and Sentinel-2, the NIR and SWIR bands are particularly sensitive to water content in soil and vegetation (Gao, 1996). The most common moisture index is NDMI, calculated as (NIR - SWIR1) / (NIR + SWIR1). For Landsat 8/9, this is (Band 5 - Band 6) / (Band 5 + Band 6) (USGS). Published studies report NDMI R-squared values between 0.60 and 0.85 for moisture estimation.

Cloud masking using the QA pixel band is a required preprocessing step because cloud contamination distorts spectral index calculations. Landsat Collection 2 Level-2 products provide surface reflectance with quality assessment bands for pixel-level cloud, shadow, and snow detection.

For SAR approaches, Sentinel-1 provides C-band VV and VH polarization data. Backscatter in these polarizations responds to soil moisture because wetter soil has higher dielectric constant. Balenzano et al. (2021) used dual-polarization for their 1 km retrieval, while Fan et al. (2025) developed a dual-polarization algorithm that retrieves both soil moisture and surface roughness.

### Landsat-Based Soil Moisture Estimation

Zhang and Liang (2022) used Landsat 8 with Random Forest and XGBoost to estimate soil moisture at 30 m. They trained on 1,154 stations from the International Soil Moisture Network and combined Landsat data with SMAP, ERA5-Land, soil texture, and terrain data. Their paper is the closest to what we are doing, but they trained globally and did not validate against the Oklahoma Mesonet.

Ghasemloo et al. (2022) combined Landsat 8 NDVI with Sentinel-1 SAR through neural networks and showed that fusing optical and radar data outperforms either source alone.

The USGS produces Landsat-derived NDMI for Landsat 8/9, calculated as (Band 5 - Band 6) / (Band 5 + Band 6). The 30 m resolution makes it suitable for comparison against point-based ground stations like the Oklahoma Mesonet.

### Multi-Sensor Integration

Peng et al. (2021) provided a roadmap for high-resolution satellite soil moisture and concluded that no single sensor meets all needs. They recommended combining SAR with optical/thermal data and coarse-resolution microwave products.

Das et al. (2019) combined SMAP and Sentinel-1 to produce a 1-3 km soil moisture product achieving about 0.05 m3/m3 RMSE, showing the value of merging passive and active microwave data.

## Ground-Truth Validation: Oklahoma Mesonet

The Oklahoma Mesonet has been running since January 1994 with 120+ stations in all 77 Oklahoma counties (McPherson et al., 2007). Stations measure soil moisture at 5, 25, and 60 cm depths using Campbell Scientific CS229L heat dissipation sensors every 30 minutes. The network covers a west-to-east gradient in climate, vegetation, and soil types, making it useful for validation studies.

Zamora et al. (2023) used the Mesonet alongside SMAP and the Noah land surface model in a triple-collocation study, confirming it as a reliable ground truth source.

Scott et al. (2013) built a soil property database for Mesonet stations with sand, silt, clay percentages, bulk density, and van Genuchten water retention parameters, which helps characterize soil conditions at each station.

## Identified Gap

Zhang and Liang (2022) showed Landsat plus ML works for soil moisture but did not validate against the Oklahoma Mesonet. Most validation studies use Sentinel-1/2, not Landsat. Nobody has taken Landsat NDMI at 30 m and correlated it with Mesonet ground readings over multiple years. Our project addresses this gap by building a pipeline that correlates Landsat 8/9 NDMI with Oklahoma Mesonet ground-truth measurements for 2023-2024.

## Discussion

The literature shows a clear direction: from coarse-resolution passive microwave products (SMAP at 9-36 km) toward higher-resolution retrievals using SAR and optical data. Sentinel-1 SAR has received the most attention because it works through clouds, but optical indices like NDMI offer finer resolution and are easier to interpret.

There is a tradeoff between accuracy and resolution. Microwave products give physically grounded moisture estimates but at coarser resolution. Optical indices like NDMI work at finer resolution but measure moisture indirectly through vegetation water content. Zhang and Liang (2022) showed that Landsat 8 with ML can bridge this gap at 30 m, but their approach needed training data from over 1,000 globally distributed stations.

Validation is another challenge. The spatial representativeness error from Balenzano et al. (2021) applies broadly: a point sensor does not perfectly represent a satellite pixel. Dense networks like the Oklahoma Mesonet help, but the mismatch between a 30 m Landsat pixel and a single ground sensor is still a source of uncertainty.

## Conclusion

Sentinel-1 SAR and multi-sensor fusion lead the field in satellite soil moisture estimation. But Landsat 8/9 remains underused despite its 30 m resolution and free availability. Our project contributes by directly correlating Landsat NDMI with Oklahoma Mesonet ground-truth measurements over 2023-2024. This addresses the gap between coarse-resolution microwave products and the field-scale estimates that Aperture Space needs for sensor calibration.

## References

1. Balenzano, A., Mattia, F., Satalino, G., et al. (2021). Sentinel-1 soil moisture at 1 km resolution: a validation study. *Remote Sensing of Environment*, 263, 112554.

2. Das, N. N., Entekhabi, D., Dunbar, R. S., et al. (2019). The SMAP and Copernicus Sentinel 1A/B microwave active-passive high resolution surface soil moisture product. *Remote Sensing of Environment*, 233, 111380.

3. Fan, D., Zhao, T., Jiang, X., et al. (2025). A Sentinel-1 SAR-based global 1-km resolution soil moisture data product: Algorithm and preliminary assessment. *Remote Sensing of Environment*, 318, 114579.

4. Gao, B. (1996). NDWI - A normalized difference water index for remote sensing of vegetation liquid water from space. *Remote Sensing of Environment*, 58(3), 257-266.

5. Ghasemloo, N., Matkan, A.A., Alimohammadi, A., et al. (2022). Estimating the Agricultural Farm Soil Moisture Using Spectral Indices of Landsat 8, and Sentinel-1, and Artificial Neural Networks. *Journal of Geovisualization and Spatial Analysis*, 6, 19.

6. El Hajj, M., et al. (2023). Soil moisture estimates at 1 km resolution making a synergistic use of Sentinel data. *Hydrology and Earth System Sciences*, 27, 1221-1242.

7. McPherson, R. A., et al. (2007). Statewide monitoring of the mesoscale environment: A technical update on the Oklahoma Mesonet. *Journal of Atmospheric and Oceanic Technology*, 24(3), 301-321.

8. Peng, J., Albergel, C., Balenzano, A., et al. (2021). A roadmap for high-resolution satellite soil moisture applications. *Remote Sensing of Environment*, 252, 112162.

9. Rahmati, M., Balenzano, A., Bechtold, M., et al. (2025). Soil moisture retrieval from Sentinel-1: Lessons learned after more than a decade in orbit. *Remote Sensing of Environment*, 317, 114505.

10. Sadeghi, M., Babaeian, E., Tuller, M., & Jones, S. B. (2020). Retrieving soil moisture in rainfed and irrigated fields using Sentinel-2 observations and a modified OPTRAM approach. *International Journal of Applied Earth Observation and Geoinformation*, 89, 102113.

11. Scott, B. L., Ochsner, T. E., Illston, B. G., et al. (2013). New soil property database improves Oklahoma Mesonet soil moisture estimates. *Journal of Atmospheric and Oceanic Technology*, 30(11), 2585-2595.

12. USGS. Normalized Difference Moisture Index - Landsat Missions. https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index

13. Zamora, R. J., et al. (2023). Triple collocation of ground-, satellite- and land surface model-based surface soil moisture products in Oklahoma. *Remote Sensing*, 15(13), 3450.

14. Zhang, Y. & Liang, S. (2022). Soil moisture content retrieval from Landsat 8 data using ensemble learning. *ISPRS Journal of Photogrammetry and Remote Sensing*, 185, 32-47.
