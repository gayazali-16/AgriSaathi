import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import FarmerWorkspace from './FarmerWorkspace.jsx';
import { api } from './api.js';
import { translate } from './i18n.js';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each(['accepted', 'rejected'])('shows the officer AI decision (%s) and preserves the original AI answer', async (decision) => {
  vi.spyOn(api, 'get').mockImplementation(async (url) => {
    if (url === '/fields') return [];
    if (url === '/cases/my') return [{ id: 'case-reviewed', question: 'Yellow rice leaves', status: 'approved',
      provider: 'Google Gemini API', advisory: { summary: 'Observe affected and healthy leaves.' }, evidence: [],
      reviews: [{ status: 'approved', ai_decision: decision, note: decision === 'rejected' ? 'Arrange a local field inspection.' : '',
        case_version: 3, created_at: '2026-09-30T12:00:00Z' }] }];
    return [];
  });
  render(<FarmerWorkspace identity={{ actor_id: 'farmer-test' }} language="en" t={(key) => translate('en', key)} />);
  expect(await screen.findByText('Observe affected and healthy leaves.')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Officer response', exact: true })).toBeInTheDocument();
  if (decision === 'rejected') {
    expect(screen.getAllByText(translate('en', 'aiRejected')).length).toBe(2);
    expect(screen.getByText('Arrange a local field inspection.')).toBeInTheDocument();
  } else {
    expect(screen.getByText(translate('en', 'aiAccepted'))).toBeInTheDocument();
    expect(screen.getByText(translate('en', 'aiAcceptedHelp'))).toBeInTheDocument();
  }
});

it('shows a useful quota failure and cooldown without claiming an AI answer', async () => {
  vi.spyOn(api, 'get').mockImplementation(async (url) => {
    if (url === '/fields') return [];
    if (url === '/cases/my') return [{ id: 'case-1', question: 'Yellow rice leaves', status: 'guidance_unavailable',
      provider: 'ai-unavailable', advisory: { summary: 'No AI answer was generated.', failure_category: 'quota', retry_after_seconds: 240 }, evidence: [] }];
    throw new Error(url);
  });
  render(<FarmerWorkspace identity={{ actor_id: 'farmer-test' }} language="en" t={(key) => translate('en', key)} />);
  expect(await screen.findByText(/The AI provider quota is exhausted/)).toHaveTextContent('Retry after about 240 seconds');
  expect(screen.queryByText(/Live Gemini/)).not.toBeInTheDocument();
});

it('prefills a clarification, preserves typing when speech construction fails, and focuses the text fallback', async () => {
  vi.spyOn(api, 'get').mockImplementation(async (url) => {
    if (url === '/fields') return [];
    if (url === '/cases/my') return [{ id: 'case-1', field_id: 'field-test', question: 'Yellow rice leaves', status: 'answered',
      provider: 'Google Gemini API', advisory: { summary: 'Observe first.', clarifying_question: 'When did symptoms start?' }, evidence: [] }];
    if (url.endsWith('/context')) return { field: { district: 'Nalgonda' }, evidence: [] };
    if (url.includes('/planning')) return { candidates: [] };
    return [];
  });
  vi.stubGlobal('SpeechRecognition', function () { throw new Error('permission denied'); });
  render(<FarmerWorkspace identity={{ actor_id: 'farmer-test' }} language="en" t={(key) => translate('en', key)} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Answer this question' }));
  const input = screen.getByLabelText('Your question');
  expect(input.value).toContain('Yellow rice leaves\nWhen did symptoms start?');
  expect(input).toHaveFocus();
  fireEvent.change(input, { target: { value: 'Symptoms started yesterday.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Record a short question' }));
  fireEvent.click(screen.getByRole('button', { name: 'Type instead' }));
  expect(input).toHaveFocus();
  expect(input).toHaveValue('Symptoms started yesterday.');
  vi.unstubAllGlobals();
});
