# Public data access and coverage

## Prototype data the current workflows use

The application does not load the original 1.19 million row CSV at runtime. It uses small prepared JSON artifacts for historical district/season context and crop presence; curated ICAR practice cards; optional OpenWeather current town weather; cached climate, soil and satellite reference records; and a farmer's own optional crop photo. The question and advisory are saved in SQLite. No PlantVillage training set or countrywide raster is needed for this current Gemini based workflow.

## Downloaded reference extracts

The versioned extracts are under `backend/data/public/`. All coordinates below are representative public reference points, not field locations or district averages.

| Source | Nalgonda | Khammam | Krishna, Andhra Pradesh | Meaning and limitation |
|---|---|---|---|---|
| NASA POWER daily point API, 1–31 August 2025 | Available | Available | Available | Daily gridded T2M, RH2M and corrected precipitation, reduced to a month's mean / total. Historical reference; not today's weather, a local gauge or a forecast. Current town weather is a separate optional OpenWeather integration. |
| ISRIC SoilGrids 2.0, 0–5 cm point query | Available | No prediction values returned for selected point | Available | Modelled pH and soil organic carbon, with 5th and 95th percentile prediction intervals. It is not a soil test. Available N/P/K, electrical conductivity, farmer Soil Health Card records and plot ownership are not present. Khammam's unverified fallback fixture is hidden from farmers and excluded entirely from Gemini. |
| Copernicus Sentinel-2 L2A via Element 84 Earth Search | Available | Available | Available | Selected 2025 scene; compressed red, NIR and scene classification windows around a reference point. NDVI uses reflectance scaling and land classes 4/5, with invalid/negative reflectance pixels rejected. The scene is archived reference data, not a current district measure. No crop mask, cloud-free whole-district mosaic, anomaly, VCI, or disease classification is claimed. |
| Supplied merged agricultural dataset | Historical Krishna label, 3,920 rows, 1980–2017 | Telangana historical label | Available, 3,920 rows, 1980–2017 | Prepared app artifacts use history and crop presence. These source labels predate the Krishna/NTR split in 2022 and their climate numeric units remain undocumented. They are historical context only, not a reliable current boundary crosswalk or field observation. |

The three satellite scenes have mean NDVI between −1 and +1 in the stored extract; the validator checks bounds and manifest hashes. Reference-window means must not be relabelled as district-wide values. Per-scene IDs, selected-point coordinates, acquisition time, request URL, processing method, raster hashes and small raster files support a reproducible spot check. Soil and climate retain their provider responses. See `backend/data/public/manifest.json` for exact downloads and failures.

## What is available for the receiving district?

Useful public data exists for **selected points in current Krishna district**: archived daily climate, SoilGrids estimates where its global model returns values, and public Sentinel-2 imagery. Historical Krishna crop records also exist in the supplied combined dataset, but the year range and historical boundaries limit comparisons with today's district. All three evidence types remain in the backend; the farmer UI displays weather/climate and soil cards, with the separate Sentinel-2 card removed.

Complete field-level AP evidence is not available from these downloads. The prototype has no registered field polygon or verified farmer address to sample; no plot-linked soil-health card/lab NPK and EC report; no verified local crop mask and season-specific district mosaic; no field disease-image labels tied to expert diagnosis; and no trusted official current field weather station feed. NASA POWER is coarse gridded data, SoilGrids is modelled, Sentinel data is a remote-sensing image, and none says what a specific farmer's plot contains. Accessing personal Soil Health Card records would require authorised data access/consent and is not established by the public integration guide alone.

This is sufficient for a clear prototype workflow in the planned Nalgonda/Khammam farmer context and Krishna receiving context, but it is not complete Andhra Pradesh district coverage, verified farm evidence, or India-wide support. The project labels scope in the UI and omits unverified soil/satellite fixture numbers from Gemini prompts.

## Reproduction and sources

Install preparation-only dependencies (`python -m pip install -r requirements-data.txt`) and run `python scripts/download_public_data.py`. Downloads cover three reference points, one August 2025 NASA POWER month, and up to 30 Sentinel candidates in a bounded Aug–Oct 2025 STAC search per point; the lowest scene-cloud-cover result on the first returned page is selected. Only three small raster windows from the selected COG are retained. The `satellite-search.json` file stores the request and chosen scene, not the full candidate response. Runtime does not need rasterio. Check stored files with `python scripts/validate_public_data.py`.

- ISRIC [SoilGrids documentation](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs.html) (public data under CC BY 4.0).
- [Copernicus Sentinel-2](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2) and the [Element 84 Earth Search catalogue](https://github.com/Element84/earth-search) (Sentinel data is freely available; cite Copernicus and the scene/catalogue).
- NASA [POWER Daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) (NASA public Earth science data).
- Current Andhra Pradesh administrative context: [Krishna District Government portal](https://krishna.ap.gov.in/), which lists Machilipatnam as the district headquarters and notes the 2022 Krishna/NTR division.
