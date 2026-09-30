import { useEffect, useRef, useState } from 'react';
import { api } from './api.js';
import { basisLabel, cropLabel, localizeError, localeTag, statusLabel } from './i18n.js';

export default function OfficerWorkspace({ identity, language, t, onChangeProfile }) {
  const isAP = identity?.actor_id === 'officer-demo-ap';
  const [queue, setQueue] = useState([]);
  const [advisories, setAdvisories] = useState([]);
  const [receipts, setReceipts] = useState([]);
  const [reviewHistory, setReviewHistory] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [showResponse, setShowResponse] = useState(false);
  const [officerResponse, setOfficerResponse] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [validDays, setValidDays] = useState(14);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showClosed, setShowClosed] = useState(false);
  const [loading, setLoading] = useState(true);
  const publishPanel = useRef(null);
  const selected = queue.find((item) => item.id === selectedId) || null;
  const hasAIResponse = selected?.provider === 'Google Gemini API';
  const caseClosed = ['resolved', 'rejected'].includes(selected?.status);
  const activeReceipts = receipts.filter((item) => item.payload?.valid_until >= new Date().toISOString());

  async function refresh(preferredCaseId = '', includeClosed = showClosed) {
    const [cases, published, exchangeRows] = await Promise.all([
      api.get(includeClosed ? '/officer/queue?include_closed=true' : '/officer/queue'), api.get('/officer/advisories'), api.get('/officer/exchanges'),
    ]);
    setQueue(cases); setAdvisories(published); setReceipts(exchangeRows);
    setSelectedId((current) => preferredCaseId || (cases.some((item) => item.id === current) ? current : cases[0]?.id || ''));
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([api.get(showClosed ? '/officer/queue?include_closed=true' : '/officer/queue'), api.get('/officer/advisories'), api.get('/officer/exchanges')])
      .then(([cases, published, exchangeRows]) => {
        if (!active) return;
        setQueue(cases); setAdvisories(published); setReceipts(exchangeRows);
        setSelectedId((current) => cases.some((item) => item.id === current) ? current : cases[0]?.id || '');
      }).catch((err) => { if (active) setError(localizeError(language, err)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [identity?.actor_id, showClosed]);

  useEffect(() => {
    setReviewNote(''); setTitle(''); setBody(''); setReviewHistory([]);
    setShowResponse(false); setOfficerResponse('');
  }, [selectedId]);

  async function reloadQueue() {
    setLoading(true); setError('');
    try { await refresh(); }
    catch (err) { setError(localizeError(language, err)); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    if (!selectedId) { setReviewHistory([]); return undefined; }
    let active = true;
    api.get(`/officer/cases/${selectedId}/reviews`)
      .then((rows) => { if (active) setReviewHistory(rows); })
      .catch((err) => { if (active) setError(localizeError(language, err)); });
    return () => { active = false; };
  }, [selectedId]);

  async function review(status, aiDecision = null, responseNote = reviewNote) {
    if (!selected) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const updated = await api.postJson(`/officer/cases/${selected.id}/review`, {
        status, note: responseNote, expected_version: selected.version,
        ...(aiDecision ? { ai_decision: aiDecision } : {}),
      });
      const closed = ['resolved', 'rejected'].includes(updated.status);
      if (closed) setShowClosed(true);
      await refresh(updated.id, showClosed || closed);
      setReviewHistory(await api.get(`/officer/cases/${updated.id}/reviews`));
      setNotice(`${t('reviewedCaseUpdated')}: ${statusLabel(language, updated.status)}.`);
      setShowResponse(false); setOfficerResponse('');
    } catch (err) { setError(localizeError(language, err)); }
    finally { setBusy(false); }
  }

  async function publish(event) {
    event.preventDefault();
    if (!selected || selected.status !== 'approved') return;
    setBusy(true); setError(''); setNotice('');
    try {
      const advisory = await api.postJson('/officer/advisories', {
        title, body, valid_days: Number(validDays), source_case_id: selected.id,
      });
      await refresh(selected.id);
      setNotice(t(advisory.state === 'Telangana' ? 'publishedAcrossStates' : 'publishedAdvisory'));
    } catch (err) { setError(localizeError(language, err)); }
    finally { setBusy(false); }
  }

  function seedDraft() {
    if (!selected) return;
    setTitle(t('draftTitle').replace('{crop}', cropLabel(language, selected.crop)).replace('{district}', selected.district));
    setBody(t('draftBody'));
  }

  return (
    <main className="workspace">
      <section className="page-intro">
        <div><span className="eyebrow">{t('officerEyebrow')}</span><h1>{t('officerTitle')}</h1><p>{t('officerIntro')}</p></div>
        <div className="intro-meta"><span className="sample-tag">{isAP ? 'ANDHRA PRADESH' : 'TELANGANA'}</span><button className="text-button" onClick={onChangeProfile}>{t('signOut')}</button></div>
      </section>
      {error && <div className="notice notice-error" role="alert"><strong>{t('errorTitle')}</strong><span>{error}</span><button onClick={() => setError('')} aria-label={t('close')}>×</button></div>}
      {notice && <div className="notice notice-green" role="status">{notice}<button onClick={() => setNotice('')} aria-label={t('close')}>×</button></div>}
      <button className="button button-outline" onClick={reloadQueue} disabled={busy || loading}>{t('refreshQueue')}</button>
      <label className="consent-row"><input type="checkbox" checked={showClosed} onChange={(event) => setShowClosed(event.target.checked)} disabled={busy} /><span>{t('includeClosed')}</span></label>
      {loading && <p role="status">{t('loading')}</p>}

      <div className="officer-grid">
        <aside className="panel queue-panel">
          <div className="panel-heading-row"><div><div className="panel-kicker">01 / {t('queue')}</div><h2>{t('queue')}</h2></div><span className="count-chip">{queue.length}</span></div>
          {!queue.length ? <p className="body-small">{loading ? t('loading') : error ? t('queueLoadFailed') : t('noQueue')}</p> : <ul className="case-list">{queue.map((item) => (
            <li key={item.id}><button className={`case-list-item ${selectedId === item.id ? 'selected' : ''}`} onClick={() => setSelectedId(item.id)}>
              <span><strong>{cropLabel(language, item.crop)} · {item.district}</strong><small>{new Date(item.created_at).toLocaleString(localeTag(language))}</small></span><span className="case-status">{statusLabel(language, item.status)}</span>
            </button></li>
          ))}</ul>}
        </aside>

        <div className="officer-detail-column">
          {selected ? <>
            <section className="panel officer-case-panel">
              <div className="panel-heading-row"><div><div className="panel-kicker">02 / {t('caseReview')}</div><h2>{cropLabel(language, selected.crop)} · {selected.district}</h2></div><span className="status-chip status-review">{statusLabel(language, selected.status)}</span></div>
              <p className="fine-print">{t('locationLabel')}: {t('districtScope')}</p>
              <button className="text-button" type="button" onClick={() => { publishPanel.current?.scrollIntoView({ block: 'start' }); publishPanel.current?.focus({ preventScroll: true }); }}>{t('viewPublishCard')}</button>
              {selected.contact ? <div className="contact-officer-details"><h3>{t('contactDetails')}</h3><div className="metric-line"><span>{t('contactName')}</span><strong>{selected.contact.name}</strong></div><div className="metric-line"><span>{t('contactPhone')}</span><strong><a href={`tel:${selected.contact.phone}`}>{selected.contact.phone}</a></strong></div><div className="metric-line"><span>{t('contactLocation')}</span><strong>{selected.contact.location}</strong></div>{selected.contact.query !== selected.question && <><h4>{t('contactRequestMessage')}</h4><blockquote>{selected.contact.query}</blockquote></>}</div> : <p className="fine-print">{t('noContactRequest')}</p>}
              <h3>{t('farmerQuestion')}</h3><blockquote>{selected.question}</blockquote>
              <section className="result-section" aria-labelledby="ai-response-heading">
                <h3 id="ai-response-heading">{t('aiResponseHeading')}</h3>
                {hasAIResponse ? <>
                  <p className="fine-print">{t('aiResponseHelp')}</p>
                  <blockquote>{selected.advisory?.summary}</blockquote>
                  {selected.advisory?.answer_basis && <p className="fine-print">{t('answerBasis')}: {basisLabel(language, selected.advisory.answer_basis)}</p>}
                  {!!selected.advisory?.possible_causes?.length && <><h4>{t('possibleCauses')}</h4><ul>{selected.advisory.possible_causes.map((cause, index) => <li key={index}><strong>{cause.label}</strong>: {cause.visual_reason}</li>)}</ul></>}
                  {!!selected.advisory?.actions?.length && <><h4>{t('nextSteps')}</h4><ul>{selected.advisory.actions.map((action, index) => <li key={index}>{action.text}</li>)}</ul></>}
                  {selected.advisory?.uncertainty && <><h4>{t('uncertainty')}</h4><p>{selected.advisory.uncertainty}</p></>}
                  {selected.advisory?.clarifying_question && <><h4>{t('clarificationHeading')}</h4><p>{selected.advisory.clarifying_question}</p></>}
                  <div className="review-actions">
                    <button className="button button-primary" type="button" disabled={busy || caseClosed} onClick={() => review('approved', 'accepted')}>{t('acceptAI')}</button>
                    <button className="button button-outline" type="button" disabled={busy || caseClosed} onClick={() => setShowResponse(true)} aria-expanded={showResponse}>{t('rejectAI')}</button>
                  </div>
                </> : <><p>{t('noAIResponse')}</p><button className="button button-outline" type="button" disabled={busy || caseClosed} onClick={() => setShowResponse(true)} aria-expanded={showResponse}>{t('writeOfficerResponse')}</button></>}
                {showResponse && <form onSubmit={(event) => { event.preventDefault(); review('approved', hasAIResponse ? 'rejected' : null, officerResponse); }}>
                  <label className="field-label" htmlFor="officer-response">{t('officerResponse')}</label>
                  <p id="officer-response-help" className="fine-print">{t('officerResponseHelp')}</p>
                  <textarea id="officer-response" aria-describedby="officer-response-help" value={officerResponse} onChange={(event) => setOfficerResponse(event.target.value)} minLength={10} maxLength={1200} rows={4} required disabled={busy || caseClosed} />
                  <button className="button button-primary" type="submit" disabled={busy || caseClosed || officerResponse.trim().length < 10}>{t('sendOfficerResponse')}</button>
                </form>}
              </section>
              {selected.transcript && <><h3>{t('farmerTranscript')}</h3><blockquote>{selected.transcript}</blockquote></>}
              {!!selected.messages?.length && <div className="result-section"><h3>{t('yourReplies')}</h3>{selected.messages.map((message, index) => <blockquote key={index}>{message.body}</blockquote>)}</div>}
              <div className="result-section"><h3>{t('reviewHistory')}</h3>
                {!reviewHistory.length ? <p className="fine-print">{t('noReviewHistory')}</p> : <ul className="evidence-list">{reviewHistory.map((review, index) => <li key={`${review.case_version}-${index}`}><span className="evidence-marker" /><div><strong>{statusLabel(language, review.status)}</strong>{review.ai_decision && <p>{t(review.ai_decision === 'accepted' ? 'aiAccepted' : 'aiRejected')}</p>}<p>{review.note || t('noOfficerNote')}</p><span className="fine-print">{new Date(review.created_at).toLocaleString(localeTag(language))}</span></div></li>)}</ul>}
              </div>
              <div className="officer-photo">
                <h3>{t('photoEvidence')}</h3>
                {selected.photo_shared_with_officer
                  ? <img src={`/api/v1/officer/cases/${selected.id}/photo`} alt={`${t('photoEvidence')} · ${cropLabel(language, selected.crop)}`} />
                  : <p className="fine-print">{t('noSharedPhoto')}</p>}
              </div>
              <label className="field-label" htmlFor="review-note">{t('reviewerNote')}</label>
              <textarea id="review-note" maxLength={1200} disabled={busy || ['resolved', 'rejected'].includes(selected.status)} rows={3} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} placeholder={t('notePlaceholder')} />
              <div className="review-actions">
                <button className="button button-outline" type="button" onClick={() => review('needs_information')} disabled={busy || ['resolved', 'rejected'].includes(selected.status)}>{t('requestInfo')}</button>
                <button className="button button-primary" type="button" onClick={() => review('approved')} disabled={busy || ['resolved', 'rejected'].includes(selected.status)}>{t('approve')}</button>
                <button className="button button-quiet" type="button" onClick={() => review('rejected')} disabled={busy || ['resolved', 'rejected'].includes(selected.status)}>{t('reject')}</button>
              </div>
              <div className="review-actions"><button className="text-button" type="button" onClick={() => review('resolved')} disabled={busy || ['resolved', 'rejected'].includes(selected.status)}>{t('resolve')}</button></div>
            </section>

            <section className="panel publish-panel" ref={publishPanel} tabIndex={-1} aria-labelledby="publish-heading">
              <div className="panel-heading-row"><div><div className="panel-kicker">03 / {t('publishHeading')}</div><h2 id="publish-heading">{t('publishHeading')}</h2></div><span className="status-chip status-live">{t('humanReviewed')}</span></div>
              {selected.status === 'approved' ? <>
              {!isAP && <p className="fine-print">{t('automaticShareHelp')}</p>}
              <p className="notice notice-amber">{t('publishWarning')}</p>
              <form onSubmit={publish}>
                <button className="text-button" type="button" onClick={seedDraft}>{t('insertDraft')}</button>
                <label className="field-label" htmlFor="advisory-title">{t('publishTitle')}</label>
                <input id="advisory-title" value={title} onChange={(event) => setTitle(event.target.value)} minLength={4} maxLength={120} required />
                <label className="field-label" htmlFor="advisory-body">{t('publishBody')}</label>
                <textarea id="advisory-body" value={body} onChange={(event) => setBody(event.target.value)} minLength={10} maxLength={1800} rows={5} required />
                <label className="field-label" htmlFor="valid-days">{t('validity')}</label>
                <select id="valid-days" value={validDays} onChange={(event) => setValidDays(event.target.value)}><option value="7">7</option><option value="14">14</option><option value="30">30</option></select>
                <button className="button button-primary" type="submit" disabled={busy}>{t('publishAction')}</button>
              </form>
              </> : <p className="notice notice-amber">{t('publishApprovalRequired')}</p>}
            </section>
          </> : <section className="panel quiet-empty"><h2>{t('queue')}</h2><p>{loading ? t('loading') : error ? t('queueLoadFailed') : t('noQueue')}</p></section>}
        </div>

        <aside className="officer-exchange-column">
          <section className="panel exchange-panel">
            <div className="panel-kicker">04 / {t('publishedAdvisories')}</div><h2>{t('publishedAdvisories')}</h2>
            {!advisories.length ? <p className="body-small">{t('noPublishedAdvisories')}</p> : <ul className="receipt-list">{advisories.slice(0, 5).map((item) => <li key={item.id}><div><strong>{item.title}</strong><p>{item.body}</p><p className="fine-print">{item.district} · {cropLabel(language, item.crop)} · {t('validUntil')} {new Date(item.valid_until).toLocaleDateString(localeTag(language))}</p></div></li>)}</ul>}
          </section>
          <section className="panel receipts-panel"><div className="panel-kicker">05 / {t('regionalSharing')}</div><h3>{t('regionalSharing')}</h3>
            {!activeReceipts.length ? <p className="body-small">{t('noRegionalShares')}</p> : <ul className="receipt-list">{activeReceipts.map((item) => <li key={item.id}><span className="receipt-check" aria-hidden="true">✓</span><div><strong>{item.payload.title}</strong><p>{item.payload.body}</p><p>{item.source_state} → {item.target_state} / {item.payload.target_district}</p><small>{cropLabel(language, item.payload.crop)} · {t('validUntil')} {new Date(item.payload.valid_until).toLocaleDateString(localeTag(language))}</small></div></li>)}</ul>}
          </section>
        </aside>
      </div>
    </main>
  );
}
