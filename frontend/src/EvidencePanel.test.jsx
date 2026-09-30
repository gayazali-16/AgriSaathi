import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { EvidencePanel } from './EvidencePanel.jsx';
import { translate } from './i18n.js';

afterEach(cleanup);

describe('EvidencePanel source and verification labels', () => {
  it('hides unverified fixture cards and the removed satellite card even when data exists', () => {
    const context = {
      field: { district: 'Khammam', state: 'Telangana', crop: 'Maize', season: 'Kharif' },
      climate: null,
      weather: { status: 'unavailable' },
      soil: {
        status: 'available',
        verification_status: 'unverified_demo_fixture',
        soil_class: 'Demo soil benchmark',
        metrics: { ph: 7.1, organic_carbon_percent: 1.8 },
        source_title: 'Demo source',
        source_url: 'https://example.test/soil',
      },
      satellite: {
        status: 'available',
        verification_status: 'unverified_demo_fixture',
        sensor: 'Demo satellite window',
        metrics: { mean_ndvi: 0.62, ndvi_anomaly_vs_normal: '+0.03', vegetation_condition_index_vci: 72 },
        source_title: 'Demo source',
        source_url: 'https://example.test/satellite',
      },
      historical: [],
      evidence: [],
    };
    const t = (key) => translate('en', key);
    render(<EvidencePanel context={context} t={t} language="en" />);

    expect(screen.queryByRole('heading', { name: 'Demo soil benchmark' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Demo satellite window' })).not.toBeInTheDocument();
    expect(screen.queryByText('+0.03')).not.toBeInTheDocument();
    expect(screen.queryByText('72')).not.toBeInTheDocument();
    expect(screen.queryByText(/unavailable right now/)).not.toBeInTheDocument();
  });

  it('labels no-key weather as a model estimate and hides absent or malformed satellite metrics', () => {
    const context = {
      field: { district: 'Nalgonda', state: 'Telangana', crop: 'Rice', season: 'Kharif' },
      weather: { status: 'available', data_type: 'live_provider_estimate', provider: 'Open-Meteo',
        reference_location: 'Nalgonda reference point', temperature_c: 28.1, atmospheric_humidity_percent: 70,
        observed_at: '2026-09-30T12:00:00Z' },
      satellite: { status: 'available', sensor: 'Archived window', verification_status: 'verified_public_observation',
        metrics: { mean_ndvi: 0.6, ndvi_anomaly_vs_normal: 'not measured', vegetation_condition_index_vci: 101 } },
      evidence: [{ type: 'live_weather_estimate', source_title: 'Open-Meteo weather models', source_url: 'https://open-meteo.com/en/docs' }],
    };
    render(<EvidencePanel context={context} t={(key) => translate('en', key)} />);
    expect(screen.getByText('Current model estimate')).toBeInTheDocument();
    expect(screen.getByText(/not a station observation or field measurement/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open-Meteo weather models' })).toHaveAttribute('href', 'https://open-meteo.com/en/docs');
    expect(screen.queryByText(translate('en', 'ndviAnomaly'))).not.toBeInTheDocument();
    expect(screen.queryByText(translate('en', 'vci'))).not.toBeInTheDocument();
  });
});
