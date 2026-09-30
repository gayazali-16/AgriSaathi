import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook } from '@testing-library/react';
import { useCasePolling } from './useCasePolling.js';
import { api } from './api.js';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

it('backs off unchanged cases, pauses hidden tabs, resumes immediately and never overlaps', async () => {
  vi.useFakeTimers();
  let visibility = 'visible';
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
  const rows = [{ id: 'one', version: 1, status: 'needs_review' }];
  const get = vi.spyOn(api, 'get').mockResolvedValue(rows);
  const update = vi.fn();
  const { unmount } = renderHook(() => useCasePolling('farmer', false, rows, update));
  await act(() => vi.advanceTimersByTimeAsync(15000));
  expect(get).toHaveBeenCalledTimes(1);
  expect(update).not.toHaveBeenCalled();
  await act(() => vi.advanceTimersByTimeAsync(29999));
  expect(get).toHaveBeenCalledTimes(1);
  await act(() => vi.advanceTimersByTimeAsync(1));
  expect(get).toHaveBeenCalledTimes(2);
  visibility = 'hidden';
  act(() => document.dispatchEvent(new Event('visibilitychange')));
  await act(() => vi.advanceTimersByTimeAsync(240000));
  expect(get).toHaveBeenCalledTimes(2);
  visibility = 'visible';
  let resolve;
  get.mockImplementation(() => new Promise((done) => { resolve = done; }));
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'));
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(get).toHaveBeenCalledTimes(3);
  await act(async () => resolve([{ ...rows[0], version: 2 }]));
  expect(update).toHaveBeenCalledWith([{ ...rows[0], version: 2 }]);
  unmount();
  await vi.advanceTimersByTimeAsync(120000);
  expect(get).toHaveBeenCalledTimes(3);
});

it('does not poll cases without an officer request or while submitting', async () => {
  vi.useFakeTimers();
  const get = vi.spyOn(api, 'get');
  const update = vi.fn();
  const { rerender } = renderHook(({ busy, cases }) => useCasePolling('farmer', busy, cases, update),
    { initialProps: { busy: false, cases: [{ status: 'answered' }] } });
  await vi.advanceTimersByTimeAsync(120000);
  rerender({ busy: true, cases: [{ status: 'needs_review' }] });
  await vi.advanceTimersByTimeAsync(120000);
  expect(get).not.toHaveBeenCalled();
});
