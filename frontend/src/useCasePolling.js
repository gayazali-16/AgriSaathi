import { useEffect, useRef } from 'react';
import { api } from './api.js';

export function useCasePolling(actorId, busy, cases, setCases) {
  const latest = useRef(cases);
  latest.current = cases;
  const enabled = cases.some((item) => ['needs_review', 'needs_information', 'approved'].includes(item.status));
  useEffect(() => {
    if (busy || !enabled) return undefined;
    let active = true;
    let inFlight = false;
    let timer;
    let delay = 15000;
    function schedule() {
      clearTimeout(timer);
      if (active && document.visibilityState !== 'hidden') timer = setTimeout(poll, delay);
    }
    async function poll() {
      if (!active || inFlight || document.visibilityState === 'hidden') return;
      inFlight = true;
      try {
        const rows = await api.get('/cases/my');
        if (!active || document.visibilityState === 'hidden') return;
        const current = latest.current;
        // Every workflow mutation increments version, including notes/replies.
        const unchanged = rows.length === current.length && rows.every((row, i) => row.id === current[i].id && row.version === current[i].version);
        delay = unchanged ? Math.min(delay * 2, 120000) : 15000;
        if (!unchanged) setCases(rows);
      } catch {
        delay = Math.min(delay * 2, 120000);
        // The explicit refresh control reports errors and remains available.
      } finally {
        inFlight = false;
        schedule();
      }
    }
    function visibilityChanged() {
      clearTimeout(timer);
      if (document.visibilityState !== 'hidden') { delay = 15000; poll(); }
    }
    document.addEventListener('visibilitychange', visibilityChanged);
    schedule();
    return () => { active = false; clearTimeout(timer); document.removeEventListener('visibilitychange', visibilityChanged); };
  }, [actorId, busy, enabled, setCases]);
}
