import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { apiMock } = vi.hoisted(() => ({
  apiMock: { get: vi.fn(), postJson: vi.fn() },
}));

vi.mock('./api.js', () => ({ api: apiMock }));

import OfficerWorkspace from './OfficerWorkspace.jsx';
import { translate } from './i18n.js';

const demoCase = {
  id: 'case-demo-1', crop: 'Rice', district: 'Nalgonda', state: 'Telangana',
  status: 'needs_review', version: 1, created_at: '2026-09-23T09:00:00+00:00',
  question: 'The rice leaves changed color this week.', transcript: null,
  provider: 'demo-abstention', photo_shared_with_officer: false,
  advisory: { summary: 'This demo did not call Gemini.', uncertainty: 'A field visit is still needed.' },
  evidence: [],
};

describe('OfficerWorkspace review controls', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it.each(['accepted', 'rejected'])('records %s AI review without publishing and requires a replacement for rejection', async (decision) => {
    const user = userEvent.setup();
    let currentCase = { ...demoCase, provider: 'Google Gemini API', advisory: { ...demoCase.advisory, summary: 'Observe the affected and healthy rice leaves.', actions: [{ text: 'Take dated photos.' }] } };
    apiMock.get.mockImplementation(async (path) => path === '/officer/queue' ? [currentCase] : []);
    apiMock.postJson.mockImplementation(async (path, payload) => {
      currentCase = { ...currentCase, status: payload.status, version: 2 };
      return currentCase;
    });
    render(<OfficerWorkspace t={(key) => translate('en', key)} />);
    expect(await screen.findByText(currentCase.advisory.summary)).toBeInTheDocument();
    expect(screen.getByText('Take dated photos.')).toBeInTheDocument();
    if (decision === 'rejected') {
      await user.click(screen.getByRole('button', { name: 'Reject AI response', exact: true }));
      expect(apiMock.postJson).not.toHaveBeenCalled();
      expect(screen.getByRole('button', { name: 'Send officer response', exact: true })).toBeDisabled();
      await user.type(screen.getByLabelText('Officer response', { exact: true }), 'Please arrange a local field inspection.');
      await user.click(screen.getByRole('button', { name: 'Send officer response', exact: true }));
    } else {
      await user.click(screen.getByRole('button', { name: 'Accept AI response', exact: true }));
    }
    await waitFor(() => expect(apiMock.postJson).toHaveBeenCalledWith(`/officer/cases/${demoCase.id}/review`, {
      status: 'approved', ai_decision: decision, expected_version: 1,
      note: decision === 'rejected' ? 'Please arrange a local field inspection.' : '',
    }));
    expect(apiMock.postJson).toHaveBeenCalledTimes(1);
    expect(await screen.findByLabelText('Advisory title')).toBeInTheDocument();
  });

  it.each(['ai-unavailable', 'demo-abstention', 'Google Gemini API'])('keeps closed cases read only and distinguishes an actual AI answer for %s', async (provider) => {
    apiMock.get.mockImplementation(async (path) => {
      if (path === '/officer/queue') return [];
      if (path === '/officer/queue?include_closed=true') return [{ ...demoCase, status: 'resolved', provider, model: 'gemini-test',
        evidence: [{ id: 'history', type: 'historical_dataset_summary', source_title: 'Private evidence source', source_url: 'https://example.test/source' }] }];
      return [];
    });
    render(<OfficerWorkspace t={(key) => translate('en', key)} />);
    fireEvent.click(screen.getByLabelText('Include closed cases (read only)'));
    expect(await screen.findByText(demoCase.question)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve for local follow-up' })).toBeDisabled();
    expect(screen.getByLabelText('Review note (optional)')).toBeDisabled();
    expect(screen.getByRole('heading', { name: 'Publish a scoped advisory' })).toBeInTheDocument();
    expect(screen.getByText(translate('en', 'publishApprovalRequired'))).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Publish to matching farmers' })).not.toBeInTheDocument();
    if (provider === 'Google Gemini API') {
      expect(screen.getByText(demoCase.advisory.summary)).toBeInTheDocument();
      expect(screen.getByText(demoCase.advisory.uncertainty)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Accept AI response' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Reject AI response' })).toBeDisabled();
    } else {
      expect(screen.queryByText(demoCase.advisory.summary)).not.toBeInTheDocument();
      expect(screen.queryByText(demoCase.advisory.uncertainty)).not.toBeInTheDocument();
      expect(screen.getByText(translate('en', 'noAIResponse'))).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Write officer response' })).toBeDisabled();
    }
    expect(screen.queryByRole('heading', { name: translate('en', 'uncertainTitle') })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: translate('en', 'evidence') })).not.toBeInTheDocument();
    expect(screen.queryByText('Private evidence source')).not.toBeInTheDocument();
    expect(screen.queryByText(translate('en', 'aiUnavailable'))).not.toBeInTheDocument();
    expect(screen.queryByText(translate('en', 'demoAbstention'))).not.toBeInTheDocument();
  });

  it('shows farmer information and opens publication only after approval', async () => {
    const user = userEvent.setup();
    let currentCase = { ...demoCase };
    apiMock.get.mockImplementation(async (path) => {
      if (path === '/officer/queue') return [currentCase];
      if (path === '/officer/advisories' || path === '/officer/exchanges') return [];
      if (path === `/officer/cases/${demoCase.id}/reviews`) return [];
      throw new Error(`Unexpected API read: ${path}`);
    });
    apiMock.postJson.mockImplementation(async (path, payload) => {
      if (path === `/officer/cases/${demoCase.id}/review`) {
        currentCase = { ...currentCase, status: payload.status, version: currentCase.version + 1 };
        return currentCase;
      }
      throw new Error(`Unexpected API write: ${path}`);
    });

    render(<OfficerWorkspace t={(key) => translate('en', key)} onChangeProfile={vi.fn()} />);

    expect(await screen.findByRole('heading', { name: 'Cases that need a human check.' })).toBeInTheDocument();
    expect(screen.getByText(demoCase.question)).toBeInTheDocument();
    expect(screen.getByText('The farmer did not share a photo for officer review.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Publish a scoped advisory' })).toBeInTheDocument();
    expect(screen.getByText(translate('en', 'publishApprovalRequired'))).toBeInTheDocument();
    expect(screen.queryByLabelText('Advisory title')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Review note (optional)'), 'Ask for a dated photo.');
    await user.click(screen.getByRole('button', { name: 'Approve for local follow-up' }));

    expect(await screen.findByLabelText('Advisory title')).toBeInTheDocument();
    expect(screen.queryByText(translate('en', 'publishApprovalRequired'))).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish to matching farmers' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Insert a cautious draft' }));
    expect(screen.getByLabelText('Advisory title').value).toContain('Nalgonda');
    expect(screen.getByLabelText('Message for farmers').value.length).toBeGreaterThan(10);
    expect(screen.getByLabelText('Valid for days')).toHaveValue('14');
    expect(apiMock.postJson).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(apiMock.postJson).toHaveBeenCalledWith(
      `/officer/cases/${demoCase.id}/review`,
      { status: 'approved', note: 'Ask for a dated photo.', expected_version: 1 },
    ));
  });
});
