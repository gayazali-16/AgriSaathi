import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import CropCyclePanel from './CropCyclePanel.jsx';
import { translate } from './i18n.js';

const planning = {
  field_id: 'field-nalgonda-rice-1',
  crop_cycle: {
    previous_crop_options: ['Maize', 'Rice'],
    seasons: ['Kharif', 'Rabi', 'Zaid'],
    sequence_data_available: false,
    historical_crop_records: [
      { crop: 'Rice', historical_record_rows: 112, seasons: ['Kharif', 'Rabi', 'Zaid'], year_range: [1980, 2017], caveat_key: 'cropHistoryCaveat', source_url: 'https://doi.org/example', source_title: 'Historical dataset' },
      { crop: 'Maize', historical_record_rows: 112, seasons: ['Kharif', 'Rabi', 'Zaid'], year_range: [1980, 2017], caveat_key: 'cropHistoryCaveat', source_url: 'https://doi.org/example', source_title: 'Historical dataset' },
    ],
  },
};

describe('CropCyclePanel', () => {
  it('reveals historical crop entries by season after the farmer enters the previous crop', () => {
    render(<CropCyclePanel planning={planning} language="en" t={(key) => translate('en', key)} />);
    const previousCrop = screen.getByLabelText('Previous crop');
    fireEvent.change(previousCrop, { target: { value: 'Rice' } });

    expect(screen.getByRole('button', { name: 'Kharif' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: 'Other crops recorded in this season · Kharif' })).toBeInTheDocument();
    expect(screen.getByText('Maize')).toBeInTheDocument();
    expect(screen.getByText(/candidate to discuss, not a tested rotation or suitability ranking/)).toBeInTheDocument();
    expect(screen.getByText(/not current recommendations/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Rabi' }));
    expect(screen.getByRole('heading', { name: 'Other crops recorded in this season · Rabi' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rabi' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.change(previousCrop, { target: { value: 'Wheat' } });
    expect(screen.getByText('No historical record matches this crop in the selected district. No seasons or options were inferred.')).toBeInTheDocument();
  });
});
