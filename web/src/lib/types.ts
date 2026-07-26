export type Status = "calm" | "watch" | "active";

export interface Headline {
  title: string;
  date: string;
  url: string | null;
}

export interface Sector {
  key: string;
  name: string;
  subtitle: string;
  icon: string;
  lat: number;
  lon: number;
  p: number;
  outlook: "unlikely" | "possible" | "likely";
  likelihood: "low" | "moderate" | "high";
  status: Status;
  summary: string;
  headlines: Headline[];
  data_confidence: "limited" | "normal" | "unknown";
  train_pos: number | null;
  trend: { date: string; p: number }[];
  drivers: string[];
}

export interface MapPoint {
  lat: number;
  lon: number;
  title: string;
  date: string;
}

export interface FeedEntry {
  ts: string;
  source: string;
  title: string;
  url: string;
  relevance_p: number;
  relevant: boolean;
  theme: string | null;
  sentiment_score: number;
  sector_key: string | null;
}

export interface Snapshot {
  as_of: string;
  generated_at: string;
  data_note: string;
  summary: {
    active: number;
    watch: number;
    calm: number;
    total_articles: number;
    clean_events: number;
    event_days: number;
  };
  sectors: Sector[];
  map_points: MapPoint[];
  feed: FeedEntry[];
  metrics: Record<string, unknown>;
}
