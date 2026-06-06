import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { API_BASE } from './api/client';

interface RefreshState {
  tick: number;        // bump this in fetch-effect deps to re-fetch
  lastUpdated: number; // ms timestamp of the last refresh
  live: boolean;       // true when a real-time stream is connected
  refresh: () => void; // manual refresh
}

const RefreshContext = createContext<RefreshState>({
  tick: 0,
  lastUpdated: Date.now(),
  live: false,
  refresh: () => {},
});

export const useRefresh = () => useContext(RefreshContext);

const INTERVAL_MS = 30_000;

export function RefreshProvider({ children }: { children: ReactNode }) {
  const [tick, setTick] = useState(0);
  const [lastUpdated, setLastUpdated] = useState(() => Date.now());
  const [live, setLive] = useState(false);

  const bump = useCallback(() => {
    setTick(t => t + 1);
    setLastUpdated(Date.now());
  }, []);

  // Baseline: poll on an interval and when the tab regains focus. This always
  // runs so the UI stays fresh even without a live backend.
  useEffect(() => {
    const id = window.setInterval(bump, INTERVAL_MS);
    const onFocus = () => bump();
    window.addEventListener('focus', onFocus);
    return () => {
      window.clearInterval(id);
      window.removeEventListener('focus', onFocus);
    };
  }, [bump]);

  // Real-time: try to subscribe to a server-sent-events stream. If the backend
  // exposes `GET /stream`, every pushed event bumps the refresh tick instantly.
  // If the endpoint isn't there (current read-only snapshot deploy), the first
  // connection error closes it cleanly and we stay on the polling baseline.
  useEffect(() => {
    if (typeof EventSource === 'undefined') return;
    let opened = false;
    let es: EventSource | null = null;
    try {
      es = new EventSource(`${API_BASE}/stream`);
      es.onopen = () => {
        opened = true;
        setLive(true);
        bump();
      };
      es.onmessage = () => bump();
      es.onerror = () => {
        // Never opened → endpoint absent; stop EventSource's reconnect storm.
        if (!opened) {
          es?.close();
          setLive(false);
        }
      };
    } catch {
      setLive(false);
    }
    return () => {
      es?.close();
      setLive(false);
    };
  }, [bump]);

  return (
    <RefreshContext.Provider value={{ tick, lastUpdated, live, refresh: bump }}>
      {children}
    </RefreshContext.Provider>
  );
}

/** Re-renders on an interval so relative timestamps ("12s ago") stay live. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
