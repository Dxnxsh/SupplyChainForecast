import { useEffect, useState, useRef } from "react";
import type { Snapshot } from "./types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const CACHE_VERSION = "7";
const STORAGE_PREFIX = `snap_v${CACHE_VERSION}_`;
const PREFETCH_DAYS = 30;

interface State {
  data: Snapshot | null;
  error: string | null;
  loading: boolean;
}

let prefetchStarted = false;
const inFlight = new Map<string, Promise<Snapshot>>();

/** Share one request across concurrent callers for the same key (e.g. switching pages
 * before the first fetch for "live" resolves shouldn't trigger a second full backend rebuild). */
function fetchDeduped(key: string, asOf: string | null): Promise<Snapshot> {
  const existing = inFlight.get(key);
  if (existing) return existing;
  const p = fetchSnapshot(asOf).finally(() => inFlight.delete(key));
  inFlight.set(key, p);
  return p;
}

function dateKey(asOf: string | null): string {
  return asOf ?? "live";
}

function readCache(key: string): Snapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + key);
    if (!raw) return null;
    return JSON.parse(raw) as Snapshot;
  } catch {
    return null;
  }
}

function writeCache(key: string, data: Snapshot) {
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(data));
  } catch {
    // storage full — evict oldest entries
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(STORAGE_PREFIX) && k !== STORAGE_PREFIX + "live") {
        keys.push(k);
      }
    }
    keys.sort();
    const toRemove = keys.slice(0, Math.max(10, Math.floor(keys.length / 2)));
    toRemove.forEach((k) => localStorage.removeItem(k));
    try {
      localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(data));
    } catch {
      // give up
    }
  }
}

function pastDates(days: number): string[] {
  const dates: string[] = [];
  const now = new Date();
  for (let i = 1; i <= days; i++) {
    const d = new Date(now.getTime() - i * 86400000);
    dates.push(d.toISOString().slice(0, 10));
  }
  return dates;
}

async function fetchSnapshot(asOf: string | null): Promise<Snapshot> {
  const url = asOf
    ? `${API_BASE}/api/snapshot?as_of=${asOf}`
    : `${API_BASE}/api/snapshot`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`snapshot ${r.status}`);
  return r.json();
}

async function fetchWithStaticFallback(d: string): Promise<Snapshot> {
  try {
    return await fetchSnapshot(d);
  } catch {
    const r = await fetch(`${import.meta.env.BASE_URL}data/snapshots/${d}.json`);
    if (!r.ok) throw new Error(`static ${r.status}`);
    return r.json();
  }
}

async function prefetchRecent() {
  if (prefetchStarted) return;
  prefetchStarted = true;
  const dates = pastDates(PREFETCH_DAYS);
  for (let i = 0; i < dates.length; i += 3) {
    const batch = dates.slice(i, i + 3);
    await Promise.all(
      batch.map(async (d) => {
        if (readCache(d)) return;
        try {
          const snap = await fetchWithStaticFallback(d);
          writeCache(d, snap);
        } catch {
          // silently skip
        }
      })
    );
  }
}

export function useSnapshot(asOf?: string | null): State {
  const [state, setState] = useState<State>({ data: null, error: null, loading: true });
  const prefetched = useRef(false);

  useEffect(() => {
    let alive = true;
    const key = dateKey(asOf ?? null);

    const cached = readCache(key);
    if (cached) {
      setState({ data: cached, error: null, loading: false });
      return;
    }

    setState((s) => ({ ...s, loading: true }));

    fetchDeduped(key, asOf ?? null)
      .then((data) => {
        writeCache(key, data);
        if (alive) setState({ data, error: null, loading: false });
      })
      .catch(() => {
        const staticUrl = key !== "live"
          ? `${import.meta.env.BASE_URL}data/snapshots/${key}.json`
          : `${import.meta.env.BASE_URL}data/ui_snapshot.json`;
        fetch(staticUrl)
          .then((r) => {
            if (!r.ok) throw new Error(`snapshot ${r.status}`);
            return r.json();
          })
          .then((data: Snapshot) => {
            writeCache(key, data);
            if (alive) setState({ data, error: null, loading: false });
          })
          .catch((e: Error) => {
            if (alive) setState({ data: null, error: e.message, loading: false });
          });
      });

    return () => { alive = false; };
  }, [asOf]);

  // Prefetch recent 30 days after first load, delayed so it never competes
  // with first paint's own network traffic.
  useEffect(() => {
    if (!prefetched.current && state.data && !state.loading) {
      prefetched.current = true;
      const t = setTimeout(prefetchRecent, 6000);
      return () => clearTimeout(t);
    }
  }, [state.data, state.loading]);

  return state;
}
