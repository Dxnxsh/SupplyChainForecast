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

export interface BackendForecastPoint {
  ds: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
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
    fetchJson<BackendForecastPoint[]>(
      `/suppliers/${encodeURIComponent(nodeName)}/forecast`
    ),
  getSummary: () => fetchJson<BackendSummary>('/summary'),
};
