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
  predicted_impact_score?: number | null;
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

export interface NodeAiSummaryResponse {
  summary: string;
  model_used: string;
  node_name: string;
}

export interface ForecastSnapshotPoint {
  ds: string;
  yhat: number;
  yhat_lower: number;
  yhat_upper: number;
  y_actual: number | null;
}

export interface ForecastSnapshotResponse {
  node_name: string;
  forecast_date: string;
  points: ForecastSnapshotPoint[];
  generated_on_demand: boolean;
  mae: number | null;
  completed_days: number;
  horizon_days: number;
}

const asOfParam = (asOf?: string | null) =>
  asOf && asOf.length > 0 ? `&as_of=${encodeURIComponent(asOf)}` : '';

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
  getSuppliers: (asOf?: string | null) =>
    fetchJson<BackendSupplier[]>(
      `/suppliers${asOf && asOf.length > 0 ? `?as_of=${encodeURIComponent(asOf)}` : ''}`
    ),
  getLatestEvents: (count = 100, asOf?: string | null) =>
    fetchJson<BackendEvent[]>(
      `/events/latest?count=${clampLimit(count)}${asOfParam(asOf)}`
    ),
  getEventsByNode: (nodeName: string, limit = 200, asOf?: string | null) =>
    fetchJson<BackendEvent[]>(
      `/events/by_node/${encodeURIComponent(nodeName)}?limit=${clampLimit(limit)}${asOfParam(asOf)}`
    ),
  getForecastedEvents: (count = 100, asOf?: string | null) =>
    fetchJson<BackendEvent[]>(
      `/events/forecasted?count=${clampLimit(count)}${asOfParam(asOf)}`
    ),
  getForecastedEventsByNode: (nodeName: string, limit = 100, asOf?: string | null) =>
    fetchJson<BackendEvent[]>(
      `/events/forecasted/by_node/${encodeURIComponent(nodeName)}?limit=${clampLimit(limit)}${asOfParam(asOf)}`
    ),
  getSupplierForecast: (nodeName: string) =>
    fetchJson<BackendHybridForecastPoint[]>(
      `/suppliers/${encodeURIComponent(nodeName)}/hybrid_forecast`
    ),
  getSummary: (asOf?: string | null) =>
    fetchJson<BackendSummary>(`/summary${asOf && asOf.length > 0 ? `?as_of=${encodeURIComponent(asOf)}` : ''}`),
  getForecastSnapshotDates: (nodeName?: string | null) => {
    const q =
      nodeName && nodeName.length > 0
        ? `?node_name=${encodeURIComponent(nodeName)}`
        : '';
    return fetchJson<{ dates: string[] }>(`/forecast-snapshots/dates${q}`);
  },
  getForecastSnapshot: (
    nodeName: string,
    snapshotDate: string,
    includeActuals = true
  ) =>
    fetchJson<ForecastSnapshotResponse>(
      `/suppliers/${encodeURIComponent(nodeName)}/forecast_snapshot?date=${encodeURIComponent(snapshotDate)}&include_actuals=${includeActuals}`
    ),
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
  postSupplierAiSummary: async (nodeName: string, model?: string | null) => {
    const response = await fetch(
      `${API_BASE_URL}/suppliers/${encodeURIComponent(nodeName)}/ai-summary`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(model ? { model } : {}),
      }
    );
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(
        `AI summary failed (${response.status}): ${detail || response.statusText}`
      );
    }
    return response.json() as Promise<NodeAiSummaryResponse>;
  },
};
