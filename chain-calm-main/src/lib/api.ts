import { API_BASE_URL } from '@/lib/config';

export interface BackendSupplier {
  id: number;
  node_name: string;
  latitude: number;
  longitude: number;
  country?: string | null;
  current_risk_score?: number | null;
  criticality: number;
}

export interface BackendEvent {
  id: number;
  article_url: string;
  article_source?: string | null;
  article_title?: string | null;
  article_timestamp?: string | null;
  event_text_segment?: string | null;
  potential_event_types?: string[] | null;
  extracted_locations?: string[] | null;
  matched_node?: string | null;
  risk_score?: number | null;
  risk_relevance_score?: number | null;
  risk_severity_score?: number | null;
  impact_score?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  temporal_info?: {
    is_predictive?: boolean;
    predicted_date?: string;
    predicted_date_confidence?: 'high' | 'medium' | 'low' | string;
    event_description?: string;
  } | null;
}

export interface BackendSummary {
  total_events: number;
  avg_risk_score?: number | null;
  most_common_event_type?: string | null;
}

export interface BackendHybridForecastPoint {
  ds: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
  news_contribution: number;
  historical_contribution: number;
  method: string;
}

export interface RssIngestStatus {
  is_running: boolean;
  current_step: string;
  progress_percent: number;
  items_processed: number;
  total_items: number;
  error: string | null;
}


const fetchJson = async <T>(path: string): Promise<T> => {
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      `Request failed (${response.status}) for ${path}: ${detail || response.statusText}`
    );
  }

  return response.json() as Promise<T>;
};

const clampLimit = (value: number, max = 200) => Math.min(Math.max(Math.floor(value), 1), max);

export const api = {
  getSuppliers: () => fetchJson<BackendSupplier[]>('/suppliers'),
  getLatestEvents: (count = 100) =>
    fetchJson<BackendEvent[]>(`/events/latest?count=${clampLimit(count)}`),
  getEventsByNode: (nodeName: string, limit = 200) =>
    fetchJson<BackendEvent[]>(
      `/events/by_node/${encodeURIComponent(nodeName)}?limit=${clampLimit(limit)}`
    ),
  getForecastedEvents: (count = 100) =>
    fetchJson<BackendEvent[]>(`/events/forecasted?count=${clampLimit(count)}`),
  getForecastedEventsByNode: (nodeName: string, limit = 100) =>
    fetchJson<BackendEvent[]>(
      `/events/forecasted/by_node/${encodeURIComponent(nodeName)}?limit=${clampLimit(limit)}`
    ),
  getSupplierForecast: (nodeName: string) =>
    fetchJson<BackendHybridForecastPoint[]>(
      `/suppliers/${encodeURIComponent(nodeName)}/hybrid_forecast`
    ),
  getSummary: () => fetchJson<BackendSummary>('/summary'),
  triggerRssIngest: async () => {
    const response = await fetch(`${API_BASE_URL}/admin/rss-ingest/trigger`, {
      method: 'POST',
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Failed to trigger RSS ingestion: ${detail || response.statusText}`);
    }
    return response.json();
  },
  getRssIngestStatus: () => fetchJson<RssIngestStatus>('/admin/rss-ingest/status'),
};
