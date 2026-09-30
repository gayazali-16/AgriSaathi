import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from './App.jsx';
import { translate } from './i18n.js';

const field = {
  id: 'field-nalgonda-rice-1', owner_id: 'farmer-nalgonda-1', state: 'Telangana',
  district: 'Nalgonda', crop: 'Rice', season: 'Kharif', stage: 'Vegetative',
  spatial_scope: 'District only; sample field profile', demo_profile: 1,
};

function response(payload) {
  return { ok: true, status: 200, json: async () => payload };
}

describe('AgriSaathi farmer workflow shell', () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

  it('shows login even with an existing session and explains an invalid password', async () => {
    localStorage.setItem('agrisathi-language', 'en');
    const fetchMock = vi.fn(async (url, options = {}) => options.method === 'POST'
      ? { ok: false, status: 401, json: async () => ({ detail: 'Incorrect username or password.' }) }
      : response({ authenticated: true, identity: { role: 'officer', actor_id: 'officer-demo' } }));
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);
    await screen.findByRole('heading', { name: 'Sign in to AgriSaathi' });
    expect(screen.queryByRole('heading', { name: 'Cases that need a human check.' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'rajesh' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in', exact: true }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect username or password');
    expect(JSON.parse(fetchMock.mock.calls.find(([, options]) => options.method === 'POST')[1].body)).toEqual({ username: 'rajesh', password: 'wrong' });
  });

  it('keeps the selected Hindi language through demo sign-in and shows a usable question form', async () => {
    const fetchMock = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/session') && options.method === 'POST') {
        return response({ authenticated: true, identity: { role: 'farmer', actor_id: 'farmer-nalgonda-1' } });
      }
      if (url.endsWith('/session')) return response({ authenticated: false, identity: null, demo_mode: true });
      if (url.endsWith('/fields')) return response([field]);
      if (url.endsWith('/cases/my')) return response([]);
      if (url.endsWith('/context')) return response({ field, historical: [], evidence: [], weather: { status: 'unavailable' }, soil: { reason: 'No soil test.' }, satellite: { reason: 'No satellite export.' } });
      if (url.includes('/planning?language=')) return response({ candidates: [], practices: [] });
      if (url.endsWith('/feed')) return response([]);
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    await screen.findByRole('heading', { name: 'మీ పొలానికి తదుపరి అడుగు స్పష్టంగా.' });
    fireEvent.change(document.querySelector('#language-select'), { target: { value: 'hi' } });
    fireEvent.change(screen.getByLabelText(translate('hi', 'username')), { target: { value: 'ramesh' } });
    fireEvent.change(screen.getByLabelText(translate('hi', 'password')), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: translate('hi', 'loginAction') }));

    expect(await screen.findByRole('heading', { name: 'आपकी फसल में क्या हो रहा है?' })).toBeInTheDocument();
    expect(screen.getByLabelText('आपका सवाल')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'खेत चुनें: Nalgonda · धान · खरीफ' })).toBeChecked();
    expect(screen.getByRole('columnheader', { name: 'जिला' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'फसल की अवस्था' })).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute('lang', 'hi');
    expect(screen.queryByText('मौसम की लाइव जानकारी जुड़ी नहीं है। ऐतिहासिक डेटा को विकल्प नहीं बनाया गया।')).not.toBeInTheDocument();
    expect(screen.getByRole('note')).toHaveTextContent('सलाह के लिए आपकी तस्वीर Google Gemini को भेजी जाएगी।');
    expect(screen.getByLabelText('फसल की तस्वीर (वैकल्पिक)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'छोटा सवाल रिकॉर्ड करें' }));
    expect(screen.getByRole('status')).toHaveTextContent('इस ब्राउज़र में वॉइस इनपुट उपलब्ध नहीं है। आप सवाल लिख सकते हैं।');
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/fields', expect.any(Object)));
  });

  it('answers first and only sends a farmer to the officer after the consent form is submitted', async () => {
    localStorage.setItem('agrisathi-language', 'en');
    let savedCase = null;
    const fetchMock = vi.fn(async (url, options = {}) => {
      if (url.endsWith('/session') && options.method === 'POST') return response({ authenticated: true, identity: { role: 'farmer', actor_id: 'farmer-nalgonda-1' } });
      if (url.endsWith('/session')) return response({ authenticated: false, identity: null, demo_mode: true });
      if (url.endsWith('/fields')) return response([field]);
      if (url.endsWith('/cases/my')) return response(savedCase ? [savedCase] : []);
      if (url.endsWith('/context')) return response({ field, historical: [], evidence: [], weather: { status: 'unavailable' }, soil: { status: 'unavailable' }, satellite: { status: 'unavailable' } });
      if (url.includes('/planning?language=')) return response({ candidates: [], practices: [] });
      if (url.endsWith('/feed')) return response([]);
      if (url.endsWith('/cases') && options.method === 'POST') {
        savedCase = { id: 'case-test-1', field_id: field.id, state: 'Telangana', district: 'Nalgonda', crop: 'Rice', question: 'How should I manage water for rice?', status: 'answered', version: 1, provider: 'Google Gemini API', model: 'gemini-test', photo_shared_with_officer: false, contact_requested: false, advisory: { summary: 'Use a safe water plan based on the field and crop stage.', answer_basis: 'general', uncertainty: 'Field conditions have not been measured.', actions: [], possible_causes: [], summary_source_ids: [] }, evidence: [], reviews: [], messages: [] };
        return response(savedCase);
      }
      if (url.endsWith('/contact-officer') && options.method === 'POST') {
        expect(options.body.get('name')).toBe('Demo Farmer');
        expect(options.body.get('phone')).toBe('+91 9876501234');
        expect(options.body.get('query')).toBe('How should I manage water for rice?');
        expect(options.body.get('consent')).toBe('true');
        savedCase = { ...savedCase, status: 'needs_review', contact_requested: true, version: 2 };
        return response(savedCase);
      }
      throw new Error(`Unexpected request ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<App />);

    await screen.findByRole('heading', { name: 'A clearer next step for your field.' });
    fireEvent.change(document.querySelector('#language-select'), { target: { value: 'en' } });
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'ramesh' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in', exact: true }));
    await screen.findByLabelText('Your question');
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'How should I manage water for rice?' } });
    fireEvent.click(screen.getByRole('button', { name: 'Get careful guidance' }));

    expect(await screen.findByText('Use a safe water plan based on the field and crop stage.')).toBeInTheDocument();
    expect(screen.getByText(/Based on relevant project data|General AI analysis/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Want professional help? Contact an officer' })).toBeInTheDocument();
    expect(savedCase.status).toBe('answered');

    fireEvent.click(screen.getByRole('button', { name: 'Want professional help? Contact an officer' }));
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Demo Farmer' } });
    const phone = screen.getByLabelText('Phone number');
    fireEvent.change(phone, { target: { value: '1234567890' } });
    expect(phone).toBeInvalid();
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/contact-officer'))).toBe(false);
    fireEvent.change(phone, { target: { value: '+91 9876501234' } });
    expect(phone).toBeValid();
    fireEvent.click(screen.getByLabelText(/I agree to share my contact details/));
    fireEvent.click(screen.getByRole('button', { name: 'Send request to officer' }));

    expect(await screen.findByText('Your request was sent to the officer queue.')).toBeInTheDocument();
    expect(savedCase.status).toBe('needs_review');
  });
});
