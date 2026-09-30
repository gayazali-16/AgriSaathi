import { useEffect, useMemo, useState } from 'react';
import { cropLabel, seasonLabel } from './i18n.js';

export default function CropCyclePanel({ planning, t, language }) {
  const cycle = planning?.crop_cycle || {};
  const records = cycle.historical_crop_records || planning?.candidates || [];
  const cropOptions = cycle.previous_crop_options || [...new Set(records.map((item) => item.crop))];
  const seasons = cycle.seasons || [...new Set(records.flatMap((item) => item.seasons || []))];
  const [previousCrop, setPreviousCrop] = useState('');
  const [selectedSeason, setSelectedSeason] = useState('');

  useEffect(() => {
    setPreviousCrop('');
    setSelectedSeason('');
  }, [planning?.field_id]);

  const previousRecord = useMemo(() => records.find((item) => item.crop.toLocaleLowerCase() === previousCrop.trim().toLocaleLowerCase()), [records, previousCrop]);
  const relevantSeasons = previousRecord?.seasons || [];
  const activeSeason = relevantSeasons.includes(selectedSeason) ? selectedSeason : relevantSeasons[0] || '';
  const nextOptions = records.filter((item) => item.crop !== previousRecord?.crop && item.seasons?.includes(activeSeason));

  return (
    <section className="panel crop-cycle-panel" aria-labelledby="crop-cycle-heading">
      <div className="panel-heading-row">
        <div><div className="panel-kicker">{t('cropCycleKicker')}</div><h2 id="crop-cycle-heading">{t('cropCycleHeading')}</h2></div>
      </div>
      <p className="body-small">{t('cropCycleIntro')}</p>

      <ol className="crop-cycle-steps">
        <li className="crop-cycle-step">
          <span className="step-number" aria-hidden="true">01</span>
          <div>
            <label className="field-label" htmlFor="previous-crop">{t('previousCrop')}</label>
            <input id="previous-crop" list="previous-crop-options" value={previousCrop} onChange={(event) => { setPreviousCrop(event.target.value); setSelectedSeason(''); }} placeholder={t('previousCropPlaceholder')} autoComplete="off" />
            <datalist id="previous-crop-options">{cropOptions.map((crop) => <option value={crop} key={crop} />)}</datalist>
            <p className="fine-print">{t('previousCropHint')}</p>
          </div>
        </li>

        {previousCrop.trim() && !previousRecord && <li className="crop-cycle-step"><span className="step-number" aria-hidden="true">02</span><p className="body-small" role="status">{t('previousCropNotFound')}</p></li>}

        {previousRecord && <>
          <li className="crop-cycle-step">
            <span className="step-number" aria-hidden="true">02</span>
            <div>
              <h3>{t('relevantSeasons')}</h3>
              <p className="fine-print">{t('relevantSeasonsHint')}</p>
              <div className="season-options" role="group" aria-label={t('relevantSeasons')}>
                {relevantSeasons.map((season) => <button type="button" className="season-option" key={season} aria-pressed={activeSeason === season} onClick={() => setSelectedSeason(season)}>{seasonLabel(language, season)}</button>)}
              </div>
            </div>
          </li>

          <li className="crop-cycle-step" aria-live="polite">
            <span className="step-number" aria-hidden="true">03</span>
            <div className="next-crop-results">
              <h3>{t('nextCropOptions')} · {seasonLabel(language, activeSeason)}</h3>
              {nextOptions.length ? <ul className="next-crop-list">{nextOptions.map((item) => <li key={`${activeSeason}-${item.crop}`}>
                <div className="panel-heading-row"><strong>{cropLabel(language, item.crop)}</strong><span className="historical-tag">{t('historicalOnly')}</span></div>
                <p className="fine-print">{item.historical_record_rows} {t('sourceRows')} · {item.year_range.join('–')}</p>
                <p className="fine-print">{t('cropCandidateReason').replace('{district}', planning.district || '').replace('{season}', seasonLabel(language, activeSeason))}</p><p className="fine-print">{t(item.caveat_key)}</p>
                <a className="fine-print" href={item.source_url} target="_blank" rel="noreferrer">{item.source_title}</a>
              </li>)}</ul> : <p className="body-small">{t('noNextCropRecords')}</p>}
            </div>
          </li>
        </>}
      </ol>

      {!previousCrop.trim() && <p className="body-small crop-cycle-prompt">{t('cropCycleStart')}</p>}
      <p className="crop-cycle-caveat">{t('cropCycleCaveat')}</p>
    </section>
  );
}
