function SourceLink({ item, t }) {
  const title = item.source_title || item.label || t('source');
  return item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer">{title}</a> : <span>{title}</span>;
}

export function HistoricalContextPanel({ context, t }) {
  if (!context?.historical?.length) return null;

  return (
    <section className="history-section" aria-labelledby="history-section-heading">
      <div className="section-heading">
        <span className="panel-kicker">{t('historicalReference')}</span>
        <h2 id="history-section-heading">{t('historyHeading')}</h2>
        <p className="body-small">{t('historyWhy')}</p>
      </div>
      <div className="history-grid">
        {context.historical.map((item) => <article className="panel historical-context" key={item.id}>
          <div className="panel-heading-row"><h3>{item.period}</h3><span className="historical-tag">{t('historicalReference')}</span></div>
          <p className="fine-print">{t('historyWhat')}</p>
          <p className="fine-print">{t('historicalEvidenceLimit')}</p>
          <p className="source-line"><span>{t('source')}: </span><SourceLink item={item} t={t} /></p>
        </article>)}
      </div>
    </section>
  );
}
