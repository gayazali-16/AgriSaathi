import { cropLabel, localeTag, seasonLabel } from './i18n.js';

function SourceLink({ item, t }) {
  const title = item.source_title || item.label || t('source');
  return item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">{title}</a> : <span>{title}</span>;
}

export function EvidencePanel({ context, t, language = 'en' }) {
  if (!context) return <section className="panel"><p>{t('loading')}</p></section>;
  const weather = context.weather;
  const live = weather?.status === 'available';
  const estimated = weather?.data_type === 'live_provider_estimate';
  const climate = context.climate;
  const soil = context.soil;
  const locale = localeTag(language);
  const soilMetrics = soil?.metrics || {};
  const hasSoilEstimate = soil?.status === 'available' && soil.verification_status !== 'unverified_demo_fixture'
    && [soilMetrics.ph, soilMetrics.organic_carbon_percent].some((value) => Number.isFinite(value));
  const hasClimateReference = climate?.status === 'available'
    && [climate.values?.mean_temperature_c, climate.values?.mean_atmospheric_humidity_percent, climate.values?.total_precipitation_mm].every(Number.isFinite);

  return (
    <div className="evidence-stack">
      <section className="panel panel-dark" aria-labelledby="field-context-heading">
        <div className="panel-kicker">{t('evidenceHeading')}</div>
        <h2 id="field-context-heading">{context.field.district}</h2>
        <p className="muted-on-dark">{context.field.state} · {cropLabel(language, context.field.crop)} · {seasonLabel(language, context.field.season)}</p>
        <div className="precision-note"><span className="status-dot" />{t('districtScope')}</div>
      </section>

      {live && <section className="panel" aria-labelledby="weather-heading">
        <div className="panel-heading-row">
          <div><div className="panel-kicker">01 / {t('currentWeather')}</div><h3 id="weather-heading">{weather.reference_location}</h3></div>
          <span className="status-chip status-live">{estimated ? t('currentModelEstimate') : t('live')}</span>
        </div>
        <>
          <p className="weather-primary">{weather.temperature_c ?? '—'}<span>°C</span></p>
          <div className="metric-line"><span>{t('humidity')}</span><strong>{weather.atmospheric_humidity_percent ?? '—'}%</strong></div>
          <p className="fine-print">{estimated ? t('weatherModelLimit') : t('weatherEvidenceLimit')}</p>
          <p className="fine-print">{estimated ? t('estimateTime') : t('observed')}: {new Date(weather.observed_at).toLocaleString(locale)}</p>
          <p className="source-line"><span>{t('source')}: </span><SourceLink item={context.evidence.find((item) => ['live_weather_observation', 'live_weather_estimate'].includes(item.type)) || { source_title: weather.provider }} t={t} /></p>
        </>
      </section>}

      {hasClimateReference && <section className="panel" aria-label={t('climateReference')}>
        <div className="panel-kicker">02 / {t('climateReference')}</div><h3>NASA POWER · {climate.period}</h3>
        <p className="fine-print">{t('referencePointScope')}</p>
        <div className="metric-line"><span>{t('meanTemperature')}</span><strong>{climate.values.mean_temperature_c} °C</strong></div>
        <div className="metric-line"><span>{t('meanHumidity')}</span><strong>{climate.values.mean_atmospheric_humidity_percent}%</strong></div>
        <div className="metric-line"><span>{t('monthlyRainfall')}</span><strong>{climate.values.total_precipitation_mm} mm</strong></div>
        <p className="fine-print">{t('climateEvidenceLimit')}</p>
        <p className="source-line"><span>{t('source')}: </span><SourceLink item={climate} t={t} /></p>
      </section>}

      {hasSoilEstimate && <section className="panel" aria-labelledby="soil-heading">
        <div className="panel-heading-row"><div><div className="panel-kicker">03 / {t('soilHeading')}</div><h3 id="soil-heading">{soil.soil_class}</h3></div>
          <span className="status-chip status-recorded">{soil.verification_status === 'unverified_demo_fixture' ? t('unverifiedDemoData') : t('modelledEstimate')}</span></div>
        {soil.observed_at && <div className="metric-line"><span>{t('observedOn')}</span><strong>{new Date(soil.observed_at).toLocaleDateString(locale)}</strong></div>}
        {soilMetrics.ph != null && <div className="metric-line"><span>{t('ph')}</span><strong>{soilMetrics.ph}</strong></div>}
        {soilMetrics.electrical_conductivity_ds_m != null && <div className="metric-line"><span>{t('ec')}</span><strong>{soilMetrics.electrical_conductivity_ds_m}</strong></div>}
        {soilMetrics.organic_carbon_percent != null && <div className="metric-line"><span>{t('organicCarbon')}</span><strong>{soilMetrics.organic_carbon_percent}%</strong></div>}
        {[soilMetrics.available_nitrogen_kg_ha, soilMetrics.available_phosphorus_kg_ha, soilMetrics.available_potassium_kg_ha].every((value) => value != null) && <div className="metric-line"><span>{t('availableNpk')}</span><strong>{soilMetrics.available_nitrogen_kg_ha} / {soilMetrics.available_phosphorus_kg_ha} / {soilMetrics.available_potassium_kg_ha} kg/ha</strong></div>}
        {soil.prediction_interval_90_percent && <p className="fine-print">{t('predictionInterval')}: pH {soil.prediction_interval_90_percent.ph.join('–')}; {t('organicCarbon')} {soil.prediction_interval_90_percent.organic_carbon_percent.join('–')}%. {t('soilDepth')}: 0–5 cm.</p>}
        <p className="notice notice-amber fine-print">{soil.verification_status === 'unverified_demo_fixture'
          ? <><strong>{t('unverifiedDemoData')}: </strong>{t('unverifiedSoilDemoLimit')}</>
          : t('soilEvidenceLimit')}</p>
        <p className="source-line"><span>{t('source')}: </span><SourceLink item={soil} t={t} /></p>
      </section>}
    </div>
  );
}
