# Data card: AgriSaathi prototype

## Source

- **Dataset:** `crops_dataset.csv` from the supplied `crop-research-data` repository.
- **License:** MIT; the required license text is retained at [DATASET-LICENSE](../DATASET-LICENSE).
- **Source documentation:** The original [dataset README](sources/crop-dataset-README.md) and [reference list](sources/crop-dataset-references.pdf) are bundled so a standalone clone retains the citation and attribution. The published dataset is archived at [Zenodo](https://doi.org/10.5281/zenodo.21981601). The large CSV/XLSX is not required to run the prototype and is not redistributed here.
- **Preparation:** `scripts/prepare_data.py`, versioned here; it reads the source CSV without copying it into this repository.
- **Included regions:** historical labels for Nalgonda and Khammam (Telangana), and Krishna (Andhra Pradesh).
- **Included core crop records:** Rice and Maize only for crop-presence/catalog entries.

## Verified source scale and prototype slice

The scanned source contains 1,194,806 data rows, 26 columns, 87 crop labels, 26 state/union-territory labels, and years 1980–2017. The selected districts contain 10,416 rows across all crops; the three Rice/Maize slices contain 672 rows (224 per district). The current row counts represent source records, not farms or independent field measurements.

The prepared runtime artifacts deduplicate identical `(year, season, temperature, humidity, rainfall)` tuples across selected crop rows. Each district yields 112 unique climate points in the measured subset. See `backend/data/prepared/quality_report.json` for the exact generated counts and `manifest.json` for the source hash.

## Intended uses

- Show that a district/crop label occurs in the historical source.
- Retrieve historical district-season source values with their 1980-2017 scope visible. CSV and README do not state numeric units; these remain unverified source values.
- Provide bounded local context to Gemini without implying the values describe the farmer's plot or today's conditions.

## Excluded uses

The app does not use source production, area, yield, N/P/K consumption, fertilizer-share, fertilizer-dose, irrigation, benefits, or rotation/intercropping strings to advise or predict. The inspected file contains repeated joined values across crop rows, unclear measurement grain and incomplete lineage. The CSV's soil description is not a lab-tested value for a farmer's field. There is no satellite imagery/NDVI or field soil test in this dataset.

## Provenance, quality, and limitations

- The three district names are historical source labels. Current administrative boundaries and geographic polygons have not been verified.
- A crop's historical presence is not a probability of suitability, an optimal-crop score, or a planting recommendation.
- Historical context is not a current forecast, soil moisture reading, farm observation, or alert. Numeric climate columns have no explicit unit declaration and cannot drive thresholds or treatment.
- Invalid/missing climate values stay missing; the preparation script does not impute them.
- The source does not supply complete row-level citations or the join lineage needed to validate all numeric columns.
- **Public soil/satellite/climate evidence:** Small ISRIC SoilGrids, NASA POWER and Copernicus Sentinel-2 extracts are stored in `backend/data/public/`; point/1 km scopes are explained in `docs/data-access.md`. Khammam SoilGrids returned no values. Unverified soil or satellite fallback fixtures are retained for testing but hidden from farmers and excluded from AI reasoning. Their source measurements are not verified and they are not a substitute for local measurements. Individual farmer soil-health-card/lab results, verified N/P/K/EC, crop masks and disease labels are missing.
- Demo farmer profiles are synthetic. They are not records from the source dataset.

## Other evidence

- **Curated practice cards:** `backend/data/guidance.json` contains short Hindi, Telugu and English cards for water management, soil-test-first fertilizer decisions, crop rotation, intercropping and integrated pest management. Each card cites its source and describes its scope. For example, the intercropping study was conducted in a specific rainfed Vertisol context and is not presented as a Telangana/AP prescription. Cards explain discussion topics; they do not confirm an individual diagnosis or provide unsupported chemical/fertilizer rates.
- **Soil:** Nalgonda and Krishna have SoilGrids modelled pH and organic-carbon estimates at selected points with uncertainty intervals. Khammam has no returned SoilGrids values; an unverified fallback fixture is retained for testing but hidden from farmers and excluded from Gemini reasoning. None is an individual soil-health-card/laboratory reading.
- **Satellite:** Each district has an archived Sentinel-2 1 km reference window and a reflectance-derived NDVI mean. These are not district composites, verified crop pixels, VCI or disease diagnoses. The farmer's Sentinel-2 card is removed; backend source data and saved advisory provenance remain. If a public record is unavailable, an existing satellite fixture is marked as unverified demo data and excluded from Gemini reasoning. Processing and scene references for public downloads are retained with the small windows.

### Current weather providers

OpenWeather (when a key is set) supplies a dated town/reference observation.
Without a key, Open-Meteo supplies a **weather-model grid estimate** at the public
district reference coordinates, never the farmer's coordinates. Temperature
and atmospheric humidity do not establish field conditions or soil moisture.
Rainfall, probability and soil moisture stay missing in this fallback. Results
cache for 30 minutes; request/validation failures are not cached or filled from
history. Set `ENABLE_NO_KEY_WEATHER=false` to disable no-key network access.
Sources: [OpenWeather](https://openweathermap.org/current),
[Open-Meteo models](https://open-meteo.com/en/docs).
