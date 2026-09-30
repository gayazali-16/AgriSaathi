import { useCasePolling } from './useCasePolling.js';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api.js';
import { EvidencePanel } from './EvidencePanel.jsx';
import CropCyclePanel from './CropCyclePanel.jsx';
import { HistoricalContextPanel } from './HistoricalContextPanel.jsx';
import { basisLabel, cropLabel, fieldScopeLabel, fieldStageLabel, localizeError, localeTag, seasonLabel, statusLabel } from './i18n.js';

function EvidenceList({ items, t }) {
  if (!items?.length) return <p className="body-small">{t('noEvidenceAttached')}</p>;
  const label = (item) => {
    if (item.type === 'historical_dataset_summary') return t('historyEvidence');
    if (item.type === 'curated_agronomy_reference') return t('referenceEvidence');
    if (['live_weather_observation', 'live_weather_estimate'].includes(item.type)) return t('weatherEvidence');
    if (item.type === 'user_uploaded_image') return t('photoEvidence');
    if (item.type.includes('soil')) return t('soilHeading');
    if (item.type.includes('satellite')) return t('satelliteHeading');
    return item.type;
  };
  const warning = (item) => item.type === 'historical_dataset_summary' ? t('historicalEvidenceLimit')
    : item.type === 'live_weather_estimate' ? t('weatherModelLimit')
    : ['live_weather_observation', 'live_weather_estimate'].includes(item.type) ? t('weatherEvidenceLimit')
      : item.type.includes('soil') ? t('soilEvidenceLimit')
        : item.type.includes('satellite') ? t('satelliteEvidenceLimit') : '';
  return (
    <ul className="evidence-list">
      {items.map((item) => (
        <li key={item.id}>
          <span className="evidence-marker" aria-hidden="true" />
          <div><strong>{label(item)}</strong>
            {item.period && <span className="fine-print"> · {item.period}</span>}
            {warning(item) && <p className="fine-print">{warning(item)}</p>}
            {item.source_url && <a className="fine-print" href={item.source_url} target="_blank" rel="noreferrer">{item.source_title || t('source')}</a>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function CasePanel({ item, t, language, field, onDeletePhoto, onSpeak, onReply, onContactOfficer, onClarify, busy }) {
  const advisory = item.advisory || {};
  const latestAIReview = (item.reviews || []).filter((review) => review.ai_decision).at(-1);
  const [reply, setReply] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactQuery, setContactQuery] = useState(item.question);
  const [manualLocation, setManualLocation] = useState('');
  const [contactPhoto, setContactPhoto] = useState(null);
  const [contactConsent, setContactConsent] = useState(false);
  const [showContact, setShowContact] = useState(false);
  const sourcesById = new Map((item.evidence || []).map((source) => [source.id, source]));
  const sourceLabel = (id) => {
    const source = sourcesById.get(id);
    if (!source) return t('source');
    if (source.type === 'historical_dataset_summary') return t('historyEvidence');
    if (['live_weather_observation', 'live_weather_estimate'].includes(source.type)) return t('weatherEvidence');
    if (source.type === 'user_uploaded_image') return t('photoEvidence');
    if (source.type?.includes('soil')) return t('soilHeading');
    if (source.type?.includes('satellite')) return t('satelliteHeading');
    return source.label || source.source_title || t('source');
  };
  const profileLocation = [field?.district || item.district, field?.state || item.state].filter(Boolean).join(', ');
  async function submitContact(event) {
    event.preventDefault();
    const form = new FormData();
    form.set('expected_version', String(item.version));
    form.set('name', contactName.trim());
    form.set('phone', contactPhone.trim());
    form.set('location', [profileLocation, manualLocation.trim()].filter(Boolean).join(', '));
    form.set('query', contactQuery.trim());
    form.set('consent', String(contactConsent));
    if (contactPhoto) form.set('photo', contactPhoto);
    if (await onContactOfficer(item, form)) setShowContact(false);
  }
  return (
    <section className="panel case-panel" aria-labelledby="case-heading" aria-live="polite">
      <div className="panel-heading-row">
        <div><div className="panel-kicker">{t('advisoryHeading')}</div><h2 id="case-heading">{t('adviceTitle')}</h2></div>
        <span className="status-chip status-review">{statusLabel(language, item.status)}</span>
      </div>
      {latestAIReview?.ai_decision === 'rejected' && <p className="notice notice-amber">{t('aiRejected')}</p>}
      <p className="case-summary">{advisory.summary}</p>
      {advisory.clarifying_question && <div className="notice notice-amber">
        <div><strong>{t('clarificationHeading')}</strong><p>{advisory.clarifying_question}</p>
          <p className="fine-print">{t('clarificationHelp')}</p>
          <button className="button button-outline" type="button" onClick={() => onClarify(item)} disabled={busy}>{t('answerClarification')}</button>
        </div>
      </div>}
      {advisory.answer_basis && <p className="notice notice-neutral answer-basis"><strong>{t('answerBasis')}:</strong> {basisLabel(language, advisory.answer_basis)}</p>}
      <button className="button button-outline" type="button" onClick={onSpeak}>{t('readAloud')}</button>
      {advisory.summary_source_ids?.length ? <p className="fine-print">{t('citedEvidence')}: {advisory.summary_source_ids.map(sourceLabel).join(', ')}</p> : item.provider !== 'demo-abstention' && <p className="fine-print">{t('noDirectCitation')}</p>}
      {item.provider === 'ai-unavailable' ? <p className="notice notice-amber">{t(({ quota: 'failureQuota', timeout: 'failureTimeout', auth: 'failureAuth', model: 'failureModel', schema: 'failureSchema', network: 'failureNetwork' })[advisory.failure_category] || 'aiUnavailable')}{advisory.retry_after_seconds > 0 && <span> {t('quotaRetry').replace('{seconds}', advisory.retry_after_seconds)}</span>}</p> : item.provider === 'demo-abstention'
        ? <p className="notice notice-neutral">{t('demoAbstention')}</p>
        : <p className="notice notice-green">{t('liveGemini')}</p>}
      {advisory.possible_causes?.length > 0 && (
        <details className="result-section source-details">
          <summary>{t('possibleCauses')}</summary>
          <ul className="cause-list">{advisory.possible_causes.map((cause, index) => <li key={`${cause.label}-${index}`}><strong>{cause.label}</strong><p>{cause.visual_reason}</p>{cause.source_ids?.length > 0 && <p className="fine-print">{t('citedEvidence')}: {cause.source_ids.map(sourceLabel).join(', ')}</p>}</li>)}</ul>
        </details>
      )}
      <div className="result-section">
        <h3>{t('nextSteps')}</h3>
        {advisory.actions?.length ? advisory.actions.map((action, index) => (
          <div className="action-card" key={`${action.practice}-${index}`}>
            <strong>{action.practice || t('safeAction')}</strong><p>{action.text}</p>
            {action.source_ids?.length > 0 && <p className="fine-print">{t('citedEvidence')}: {action.source_ids.map(sourceLabel).join(', ')}</p>}
            {action.source_url && <a href={action.source_url} target="_blank" rel="noreferrer">{action.source_title}</a>}
          </div>
        )) : <p className="body-small">{t('noSafeAction')}</p>}
      </div>
      <div className="result-section uncertainty-block">
        <h3>{t('uncertainty')}</h3><p>{advisory.uncertainty}</p>
        {['needs_review', 'needs_information'].includes(item.status) ? <p className="notice notice-amber">{t('officerReview')}</p> : item.status === 'answered' && <p className="notice notice-neutral">{t('directAdvice')}</p>}
        {item.status === 'approved' && <p className="notice notice-green">{t('approvedFollowupNext')}</p>}
        {item.status === 'answered' && advisory.needs_officer_review && <p className="notice notice-amber">{t('aiSuggestReview')} {advisory.review_reason}</p>}
        {['answered', 'guidance_unavailable'].includes(item.status) && !item.contact_requested && <div className="contact-cta">
          <button className="button button-outline" type="button" onClick={() => setShowContact((value) => !value)} aria-expanded={showContact}>{t('askOfficer')}</button>
          {showContact && <form className="contact-form" onSubmit={submitContact}>
            <h4>{t('contactHeading')}</h4><p className="fine-print">{t('contactIntro')}</p>
            <label className="field-label" htmlFor="contact-name">{t('contactName')}</label>
            <input id="contact-name" value={contactName} onChange={(event) => setContactName(event.target.value)} minLength={2} maxLength={100} required />
            <label className="field-label" htmlFor="contact-phone">{t('contactPhone')}</label>
            <input id="contact-phone" type="tel" inputMode="tel" autoComplete="tel" value={contactPhone} onChange={(event) => setContactPhone(event.target.value)} pattern={'(?:[+]?91(?: |-)?)?[6-9][0-9]{9}'} title={t('validIndianPhoneHint')} aria-describedby="contact-phone-help" minLength={10} maxLength={16} required />
            <p id="contact-phone-help" className="fine-print">{t('validIndianPhoneHint')}</p>
            <p className="fine-print">{t('contactPhoneNote')}</p>
            <label className="field-label" htmlFor="contact-location">{t('contactLocation')}</label>
            <input id="contact-location" value={profileLocation} readOnly />
            <p className="fine-print">{t('contactLocationNote')}</p>
            <label className="field-label" htmlFor="contact-manual-location">{t('contactManualLocation')}</label>
            <input id="contact-manual-location" value={manualLocation} onChange={(event) => setManualLocation(event.target.value)} maxLength={100} />
            <label className="field-label" htmlFor="contact-query">{t('contactQuery')}</label>
            <textarea id="contact-query" value={contactQuery} onChange={(event) => setContactQuery(event.target.value)} minLength={4} maxLength={1500} rows={3} required />
            <label className="field-label" htmlFor="contact-photo">{t('contactPhoto')}</label>
            <input id="contact-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setContactPhoto(event.target.files?.[0] || null)} />
            <p className="fine-print">{t('contactPhotoNote')}</p>
            <label className="consent-row"><input type="checkbox" checked={contactConsent} onChange={(event) => setContactConsent(event.target.checked)} required /><span>{t('contactConsent')}</span></label>
            <button className="button button-primary" disabled={busy || !contactConsent}>{busy ? t('submitting') : t('sendContactRequest')}</button>
          </form>}
        </div>}
        {item.contact_requested && <p className="notice notice-green">{t('contactRequestSaved')}</p>}
      </div>
      {!!item.reviews?.length && <div className="result-section"><h3>{t('officerResponse')}</h3>{item.reviews.map((review) => <div key={review.case_version}><strong>{statusLabel(language, review.status)}</strong>{review.ai_decision && <p>{t(review.ai_decision === 'accepted' ? 'aiAccepted' : 'aiRejected')}</p>}<p>{review.note || (review.ai_decision === 'accepted' ? t('aiAcceptedHelp') : t('noReviewNote'))}</p><small>{new Date(review.created_at).toLocaleString(localeTag(language))}</small></div>)}</div>}
      {!!item.messages?.length && <div className="result-section"><h3>{t('yourReplies')}</h3>{item.messages.map((message, index) => <p key={index}>{message.body}</p>)}</div>}
      {item.status === 'needs_information' && <form onSubmit={async (event) => { event.preventDefault(); if (await onReply(item, reply)) setReply(''); }}><label className="field-label" htmlFor="farmer-reply">{t('replyLabel')}</label><p id="reply-visibility" className="fine-print">{t('replyVisibility')}</p><textarea aria-describedby="reply-visibility" id="farmer-reply" value={reply} onChange={(event) => setReply(event.target.value)} required minLength={4} maxLength={1500} /><button className="button button-primary" disabled={busy}>{t('sendReply')}</button></form>}
      <details className="result-section source-details"><summary>{t('sourceDetails')}</summary><h3>{t('evidence')}</h3><EvidenceList items={item.evidence} t={t} /></details>
      <div className="case-footer">
        <span>{item.photo_shared_with_officer ? t('photoShared') : t('photoNotShared')}</span>
        {item.photo_shared_with_officer && <button className="text-button" type="button" onClick={() => onDeletePhoto(item.id)} disabled={busy}>{t('deletePrivatePhoto')}</button>}
      </div>
    </section>
  );
}

export default function FarmerWorkspace({ identity, language, t, onChangeProfile }) {
  const [fields, setFields] = useState([]);
  const [fieldId, setFieldId] = useState('');
  const [context, setContext] = useState(null);
  const [planning, setPlanning] = useState(null);
  const [feed, setFeed] = useState([]);
  const [cases, setCases] = useState([]);
  const [selectedCaseId, setSelectedCaseId] = useState('');
  const [question, setQuestion] = useState('');
  const [transcript, setTranscript] = useState('');
  const [photo, setPhoto] = useState(null);
  const [recording, setRecording] = useState(false);
  const [voiceNote, setVoiceNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [feedBusy, setFeedBusy] = useState(false);
  const currentFieldId = useRef(fieldId);
  currentFieldId.current = fieldId;
  const submissionId = useRef(crypto.randomUUID());
  const recognition = useRef(null);
  const questionInput = useRef(null);
  const previewUrl = useMemo(() => photo ? URL.createObjectURL(photo) : '', [photo]);
  const selectedCase = cases.find((item) => item.id === selectedCaseId) || null;

  async function refreshFeed() {
    if (!fieldId) return;
    const requestedField = fieldId;
    setFeedBusy(true);
    try {
      const rows = await api.get(`/fields/${requestedField}/feed`);
      if (currentFieldId.current === requestedField) setFeed(rows);
    } catch (err) { setError(localizeError(language, err)); }
    finally { setFeedBusy(false); }
  }

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    recognition.current?.abort?.();
  }, [previewUrl]);

  useEffect(() => {
    let active = true;
    async function load() {
      setError('');
      try {
        const [fieldRows, caseRows] = await Promise.all([api.get('/fields'), api.get('/cases/my')]);
        if (!active) return;
        setFields(fieldRows);
        setCases(caseRows);
        setFieldId((current) => fieldRows.some((field) => field.id === current) ? current : fieldRows[0]?.id || '');
        setSelectedCaseId((current) => caseRows.some((item) => item.id === current) ? current : caseRows[0]?.id || '');
      } catch (err) { if (active) setError(localizeError(language, err)); }
    }
    load();
    return () => { active = false; };
  }, [identity.actor_id]);

  useEffect(() => {
    if (!fieldId) return undefined;
    let active = true;
    setContext(null); setPlanning(null);
    Promise.all([
      api.get(`/fields/${fieldId}/context`),
      api.get(`/fields/${fieldId}/planning?language=${language}`),
      api.get(`/fields/${fieldId}/feed`),
    ]).then(([ctx, plan, advisories]) => {
      if (active) { setContext(ctx); setPlanning(plan); setFeed(advisories); }
    }).catch((err) => { if (active) setError(localizeError(language, err)); });
    return () => { active = false; };
  }, [fieldId, identity.actor_id, language]);

  function startVoice() {
    setVoiceNote('');
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { setVoiceNote(t('voiceUnavailable')); return; }
    let instance;
    try { instance = new SpeechRecognition(); }
    catch { setVoiceNote(t('voiceUnavailable')); return; }
    recognition.current = instance;
    let receivedSpeech = false;
    instance.lang = language === 'te' ? 'te-IN' : language === 'hi' ? 'hi-IN' : 'en-IN';
    instance.interimResults = false;
    instance.maxAlternatives = 1;
    instance.onstart = () => setRecording(true);
    instance.onerror = () => { setRecording(false); setVoiceNote(t('voiceUnavailable')); };
    instance.onend = () => { setRecording(false); if (!receivedSpeech) setVoiceNote(t('voiceUnavailable')); };
    instance.onresult = (event) => {
      const spoken = event.results?.[0]?.[0]?.transcript || '';
      if (!spoken.trim()) { setVoiceNote(t('voiceUnavailable')); return; }
      receivedSpeech = true;
      setQuestion(spoken);
      setTranscript(spoken);
      setVoiceNote('');
    };
    try { instance.start(); }
    catch { setRecording(false); setVoiceNote(t('voiceUnavailable')); }
  }

  async function refreshCases(preferredId) {
    const caseRows = await api.get('/cases/my');
    setCases(caseRows);
    if (preferredId) setSelectedCaseId(preferredId);
  }

  useCasePolling(identity.actor_id, busy, cases, setCases);

  async function caseAction(item, suffix, payload = {}) {
    setBusy(true); setError('');
    try {
      await api.postJson(`/cases/${item.id}/${suffix}`, { ...payload, expected_version: item.version });
      await refreshCases(item.id);
      return true;
    } catch (err) { setError(localizeError(language, err)); return false; }
    finally { setBusy(false); }
  }

  async function submitQuestion(event) {
    event.preventDefault(); setError(''); setNotice('');
    if (!fieldId) { setError(t('chooseFieldError')); return; }
    if (!question.trim() && !photo) { setError(t('questionOrPhotoError')); return; }
    const form = new FormData();
    form.set('field_id', fieldId);
    form.set('question', question.trim());
    form.set('transcript', transcript);
    form.set('language', language);
    form.set('submission_id', submissionId.current);
    if (photo) form.set('photo', photo);
    setBusy(true);
    try {
      const result = await api.postForm('/cases', form);
      await refreshCases(result.id);
      setQuestion(''); setTranscript(''); setPhoto(null);
      submissionId.current = crypto.randomUUID();
      setNotice(t('caseSaved'));
    } catch (err) { setError(localizeError(language, err)); }
    finally { setBusy(false); }
  }

  async function removePhoto(caseId) {
    setBusy(true); setError(''); setNotice('');
    try {
      await api.delete(`/cases/${caseId}/photo`);
      await refreshCases(caseId);
      setNotice(t('photoDeleted'));
    } catch (err) { setError(localizeError(language, err)); }
    finally { setBusy(false); }
  }

  async function contactOfficer(item, form) {
    setBusy(true); setError(''); setNotice('');
    try {
      await api.postForm(`/cases/${item.id}/contact-officer`, form);
      await refreshCases(item.id);
      setNotice(t('contactRequestSaved'));
      return true;
    } catch (err) { setError(localizeError(language, err)); return false; }
    finally { setBusy(false); }
  }

  function speakSummary() {
    const text = selectedCase?.advisory?.summary;
    if (!text || !('speechSynthesis' in window)) { setNotice(t('speechUnavailable')); return; }
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = localeTag(language);
      utterance.onerror = () => setNotice(t('speechUnavailable'));
      window.speechSynthesis.speak(utterance);
    } catch { setNotice(t('speechUnavailable')); }
  }

  function answerClarification(item) {
    setFieldId(item.field_id);
    setQuestion(`${item.question.slice(0, 900)}\n${item.advisory.clarifying_question}\n`);
    setTranscript('');
    questionInput.current?.focus();
  }

  const fieldLabel = (field) => `${field.district} · ${cropLabel(language, field.crop)} · ${seasonLabel(language, field.season)}`;
  return (
    <main className="workspace">
      <section className="page-intro">
        <div><span className="eyebrow">{t('farmerEyebrow')}</span><h1>{t('farmerTitle')}</h1><p>{t('farmerIntro')}</p></div>
        <div className="intro-meta"><span className="sample-tag">{t('sampleProfile')}</span><span>{fields.find((field) => field.id === fieldId)?.district || ''}</span><button className="text-button" onClick={onChangeProfile}>{t('signOut')}</button></div>
      </section>

      {error && <div className="notice notice-error" role="alert"><strong>{t('errorTitle')}</strong><span>{error}</span><button onClick={() => setError('')} aria-label={t('close')}>×</button></div>}
      {notice && <div className="notice notice-green" role="status">{notice}<button onClick={() => setNotice('')} aria-label={t('close')}>×</button></div>}

      <div className="farmer-flow">
        <section className="farmer-current-info" aria-labelledby="current-info-heading">
          <section className="panel field-selector-panel" aria-labelledby="field-selector-heading">
            <div className="panel-heading-row"><div><div className="panel-kicker">{t('currentField')}</div><h2 id="field-selector-heading">{t('fieldLabel')}</h2></div><span className="count-chip">{fields.length}</span></div>
            {fields.length ? <div className="field-table-scroll" role="region" aria-label={t('fieldLabel')} tabIndex={0}>
              <table className="field-table">
                <thead><tr><th scope="col">{t('selectField')}</th><th scope="col">{t('fieldDistrict')}</th><th scope="col">{t('fieldCrop')}</th><th scope="col">{t('fieldSeason')}</th><th scope="col">{t('fieldStage')}</th><th scope="col">{t('fieldDetails')}</th></tr></thead>
                <tbody>{fields.map((field) => <tr key={field.id} className={field.id === fieldId ? 'selected' : ''}>
                  <td><input type="radio" name="selected-field" value={field.id} checked={field.id === fieldId} onChange={() => setFieldId(field.id)} aria-label={`${t('selectField')}: ${fieldLabel(field)}`} /></td>
                  <th scope="row">{field.district}</th><td>{cropLabel(language, field.crop)}</td><td>{seasonLabel(language, field.season)}</td><td>{fieldStageLabel(language, field.stage)}</td><td>{fieldScopeLabel(language, field.spatial_scope)}</td>
                </tr>)}</tbody>
              </table>
            </div> : <p className="body-small">{t('noFields')}</p>}
          </section>

          <section className="data-section" aria-labelledby="current-info-heading">
            <div className="section-heading"><span className="panel-kicker">{t('fieldSupport')}</span><h2 id="current-info-heading">{t('evidenceHeading')}</h2></div>
            <EvidencePanel context={context} t={t} language={language} />
          </section>

          <section className="panel feed-panel"><div className="panel-heading-row"><div><div className="panel-kicker">{t('regionalFeed')}</div><h3>{t('regionalFeed')}</h3></div><button className="text-button" onClick={refreshFeed} disabled={feedBusy || busy || !fieldId}>{t('refreshAdvisories')}</button></div>
            {!feed.length ? <p className="body-small">{t('noFeed')}</p> : <ul className="feed-list">{feed.map((item) => <li key={item.id}><div className="panel-heading-row"><strong>{item.title}</strong><span className="status-chip status-live">{item.exchange_source === 'local' ? t('published') : t('regionalShare')}</span></div><p>{item.body}</p><p className="fine-print">{item.district} · {cropLabel(language, item.crop)} · {t('validUntil')} {new Date(item.valid_until).toLocaleDateString(localeTag(language))}</p></li>)}</ul>}
          </section>
        </section>

        {planning && <CropCyclePanel planning={planning} t={t} language={language} />}

        <section className="farmer-service-flow" aria-labelledby="farmer-service-heading">
          <div className="section-heading"><span className="panel-kicker">{t('askSection')}</span><h2 id="farmer-service-heading">{t('askSection')}</h2></div>
          <div className="farmer-service-grid">
            <form className="panel question-panel" onSubmit={submitQuestion}>
              <div className="panel-kicker">{t('agricultureIntelligence')}</div>
              <label className="field-label" htmlFor="question-input">{t('questionLabel')}</label>
              <textarea id="question-input" ref={questionInput} value={question} onChange={(event) => { setQuestion(event.target.value); setTranscript(''); }} placeholder={t('questionPlaceholder')} maxLength={1500} rows={5} />
              <div className="form-row voice-row">
                <button className="button button-outline" type="button" onClick={recording ? () => recognition.current?.stop?.() : startVoice}>
                  {recording ? t('stopRecording') : t('recordVoice')}
                </button>
                <span className="fine-print">{t('voicePrivacy')}</span>
              </div>
              {voiceNote && <div><p className="fine-print" role="status">{voiceNote}</p><button className="text-button" type="button" onClick={() => questionInput.current?.focus()}>{t('typeInstead')}</button></div>}
              {transcript && <p className="transcript-confirmed" role="status">✓ {t('transcriptReady')}</p>}
              <label className="field-label" htmlFor="photo-input">{t('photoLabel')}</label>
              <div className="photo-input-group">
                <input id="photo-input" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={(event) => setPhoto(event.target.files?.[0] || null)} />
                <p className="photo-upload-notice" role="note">{t('photoNotice')}</p>
              </div>
              <p className="fine-print">{t('photoHelp')}</p>
              {photo && <div className="photo-preview"><img src={previewUrl} alt={t('selectedPhotoAlt')} /><div><strong>{photo.name}</strong><span>{Math.max(1, Math.round(photo.size / 1024))} KB</span><button className="text-button" type="button" onClick={() => setPhoto(null)}>{t('removePhoto')}</button></div></div>}
              <div className="submit-row"><span className="fine-print">{t('safetyReminder')}</span><button className="button button-primary" type="submit" disabled={busy}>{busy ? t('submitting') : t('submitQuestion')}</button></div>
            </form>

            <div className="farmer-case-column">
              {selectedCase && <CasePanel key={selectedCase.id} item={selectedCase} t={t} language={language} field={fields.find((item) => item.id === selectedCase.field_id)} onDeletePhoto={removePhoto} onSpeak={speakSummary} onReply={(item, text) => caseAction(item, 'reply', { text })} onContactOfficer={contactOfficer} onClarify={answerClarification} busy={busy} />}
              {!selectedCase && <section className="panel quiet-empty"><h2>{t('advisoryHeading')}</h2><p>{t('noCases')}</p></section>}
            </div>

            <section className="panel cases-panel">
              <div className="panel-heading-row"><div><div className="panel-kicker">{t('caseHistory')}</div><h2>{t('casesHeading')}</h2></div><div className="cases-panel-actions"><span className="count-chip">{cases.length}</span><button className="text-button" onClick={() => refreshCases(selectedCaseId).catch((err) => setError(localizeError(language, err)))} disabled={busy}>{t('refreshCases')}</button></div></div>
              {!cases.length ? <p className="body-small">{t('noCases')}</p> : <ul className="case-list">{cases.map((item) => {
                const relatedField = fields.find((field) => field.id === item.field_id);
                return <li key={item.id}><button className={`case-list-item ${selectedCaseId === item.id ? 'selected' : ''}`} onClick={() => setSelectedCaseId(item.id)}>
                  <span className="case-list-copy"><strong>{item.question}</strong><small>{cropLabel(language, item.crop)} · {item.district}{relatedField?.season ? ` · ${seasonLabel(language, relatedField.season)}` : ''} · {new Date(item.created_at).toLocaleString(localeTag(language))}</small></span><span className="case-status">{t('caseStatus')}: {statusLabel(language, item.status)}</span>
                </button></li>;
              })}</ul>}
            </section>
          </div>
        </section>

        <HistoricalContextPanel context={context} t={t} />
      </div>
    </main>
  );
}
