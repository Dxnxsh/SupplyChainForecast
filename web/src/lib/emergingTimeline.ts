import { useEffect, useState } from "react";

export type EmergingStatus = "nascent" | "bursting" | "candidate";

export interface EmergingCluster {
  cluster_id: string;
  label: string;
  keywords: string[];
  status: EmergingStatus;
  n_total: number;
  n_recent: number;
  z: number;
  velocity: number[];
  first_seen: string;
  example_titles: string[];
}

export interface EmergingTimeline {
  generated_at: string;
  grid_freq: string;
  encoder: string;
  params: Record<string, number>;
  dates: Record<string, { clusters: EmergingCluster[] }>;
}

let cache: EmergingTimeline | null = null;
let inflight: Promise<EmergingTimeline | null> | null = null;

async function loadTimeline(): Promise<EmergingTimeline | null> {
  if (cache) return cache;
  if (inflight) return inflight;
  inflight = fetch(`${import.meta.env.BASE_URL}data/emerging_timeline.json`)
    .then((r) => (r.ok ? (r.json() as Promise<EmergingTimeline>) : null))
    .then((data) => {
      cache = data;
      return data;
    })
    .catch(() => null);
  return inflight;
}

/**
 * Clusters visible as of `asOf` (YYYY-MM-DD, or null for "live"): the entry for that exact
 * weekly grid date if present, else the nearest earlier grid date (EMERGING_SECTORS_PLAN.md
 * §5.1) — the DateWheel rewinds daily but the grid is weekly, and this must never show a
 * cluster that "hasn't happened yet" relative to asOf.
 */
export function clustersAsOf(timeline: EmergingTimeline | null, asOf: string | null): EmergingCluster[] {
  if (!timeline) return [];
  const keys = Object.keys(timeline.dates).sort();
  if (keys.length === 0) return [];
  const target = asOf ?? keys[keys.length - 1];
  let best: string | null = null;
  for (const k of keys) {
    if (k <= target) best = k;
    else break;
  }
  return best ? timeline.dates[best].clusters : [];
}

export function useEmergingTimeline(): { timeline: EmergingTimeline | null; loaded: boolean } {
  const [timeline, setTimeline] = useState<EmergingTimeline | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    loadTimeline().then((t) => {
      if (alive) {
        setTimeline(t);
        setLoaded(true);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  return { timeline, loaded };
}
