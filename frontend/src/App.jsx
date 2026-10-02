import { useEffect, useState } from 'react';
import FarmerWorkspace from './FarmerWorkspace.jsx';
import OfficerWorkspace from './OfficerWorkspace.jsx';
import { api } from './api.js';
import { languages, localizeError, translate } from './i18n.js';

const sampleAccounts = [
  { username: 'ramesh', role: 'farmerMode', scope: 'Nalgonda · Telangana' },
  { username: 'suresh', role: 'farmerMode', scope: 'Nalgonda · Telangana' },
  { username: 'anil', role: 'farmerMode', scope: 'Khammam · Telangana' },
  { username: 'lakshmi', role: 'farmerMode', scope: 'Krishna · Andhra Pradesh' },
  { username: 'rajesh', role: 'officerMode', scope: 'Telangana' },
  { username: 'priya', role: 'officerMode', scope: 'Andhra Pradesh' },
];

function SampleCredentials({ t }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="sample-credentials">
      <button className="text-button" type="button" aria-expanded={open} aria-controls="sample-login-credentials" onClick={() => setOpen(!open)}>
        {t('sampleCredentials')} <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      <div id="sample-login-credentials" className="sample-credentials-panel" hidden={!open}>
        <p>{t('sampleCredentialsHelp')}</p>
        <table>
          <caption>{t('sampleCredentials')}</caption>
          <thead><tr><th scope="col">{t('username')}</th><th scope="col">{t('password')}</th><th scope="col">{t('sampleAccountRole')}</th><th scope="col">{t('scope')}</th></tr></thead>
          <tbody>{sampleAccounts.map((account) => <tr key={account.username}>
            <td><code>{account.username}</code></td><td><code>123</code></td><td>{t(account.role)}</td><td>{account.scope}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}

function WelcomeScreen({ t, language, setLanguage, onLogin, loginError, busy }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  return (
    <main className="welcome-wrap">
      <section className="welcome-hero">
        <div className="welcome-copy"><span className="eyebrow">{t('welcomeTagline')}</span><h1>{t('welcomeTitle')}</h1><p>{t('welcomeBody')}</p>
          <div className="welcome-rules"><span>01 <b>{t('welcomeRuleEvidence')}</b></span><span>02 <b>{t('welcomeRuleHuman')}</b></span><span>03 <b>{t('welcomeRuleLanguage')}</b></span></div>
        </div>
        <form className="login-card" onSubmit={(event) => { event.preventDefault(); onLogin(username, password); }}>
          <div className="panel-kicker">{t('localPrototype')}</div><h2>{t('loginHeading')}</h2>
          <label className="field-label" htmlFor="login-username">{t('username')}</label>
          <input id="login-username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} maxLength={64} required disabled={busy} />
          <label className="field-label" htmlFor="login-password">{t('password')}</label>
          <input id="login-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} maxLength={128} required disabled={busy} />
          <button className="button button-primary full-width" type="submit" disabled={busy}>{t('loginAction')}</button>
          <p className="fine-print">{t('loginHelp')}</p>
          <p className="fine-print login-caveat">{t('demoNote')}</p>
          {loginError && <p className="notice notice-error" role="alert">{loginError}</p>}
        </form>
      </section>
      <section className="welcome-footnote"><span>{t('agricultureIntelligence')}</span><p>{t('welcomeFootnote')}</p><label htmlFor="welcome-language">{t('language')}</label><select id="welcome-language" value={language} onChange={(event) => setLanguage(event.target.value)}>{languages.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select></section>
    </main>
  );
}

export default function App() {
  const [language, setLanguageState] = useState(() => {
    try { return localStorage.getItem('agrisathi-language') || 'te'; } catch { return 'te'; }
  });
  const [identity, setIdentity] = useState(null);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loginError, setLoginError] = useState('');
  const t = (key) => translate(language, key);

  function setLanguage(next) {
    setLanguageState(next);
    try { localStorage.setItem('agrisathi-language', next); } catch { /* optional preference */ }
  }

  useEffect(() => {
    document.documentElement.lang = language === 'te' ? 'te' : language === 'hi' ? 'hi' : 'en';
  }, [language]);

  useEffect(() => {
    let active = true;
    // Show the login page on every new page launch, even with an existing cookie.
    api.get('/session').catch((err) => {
      if (active) setLoginError(localizeError(language, err));
    }).finally(() => { if (active) setChecking(false); });
    return () => { active = false; };
  }, []);

  async function login(username, password) {
    setBusy(true); setLoginError('');
    try {
      const result = await api.postJson('/session', { username, password });
      setIdentity(result.identity);
    } catch (err) { setLoginError(err.status === 401 ? t('loginInvalid') : localizeError(language, err)); }
    finally { setBusy(false); }
  }

  async function changeProfile() {
    setBusy(true); setLoginError('');
    try { await api.delete('/session'); setIdentity(null); }
    catch (err) { setLoginError(localizeError(language, err)); }
    finally { setBusy(false); }
  }

  return (
    <div className={`app-shell lang-${language}`}>
      <header className="site-header">
        <a className="brand" href="/" aria-label={t('brandHome')}><span className="brand-mark" aria-hidden="true">A</span><span><strong>{t('brand')}</strong><small>{t('strapline')}</small></span></a>
        <div className="header-controls">
          {identity && <span className="session-label">{identity.role === 'officer' ? t('officerMode') : t('farmerMode')}</span>}
          <label htmlFor="language-select">{t('language')}</label>
          <select id="language-select" value={language} onChange={(event) => setLanguage(event.target.value)}>{languages.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select>
        </div>
      </header>
      {checking ? <main className="loading-screen" role="status">{t('loading')}</main> : !identity ? (
        <WelcomeScreen t={t} language={language} setLanguage={setLanguage} onLogin={login} loginError={loginError} busy={busy} />
      ) : identity.role === 'officer' ? (
        <OfficerWorkspace key={identity.actor_id} identity={identity} language={language} t={t} onChangeProfile={changeProfile} />
      ) : (
        <FarmerWorkspace key={identity.actor_id} identity={identity} language={language} t={t} onChangeProfile={changeProfile} />
      )}
      <footer className="site-footer"><span>AGRI / 2026</span><p>{t('footerNotice')}</p><SampleCredentials t={t} /></footer>
    </div>
  );
}
