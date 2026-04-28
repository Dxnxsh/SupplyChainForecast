import { BackendEvent, BackendSupplier } from '@/lib/api';
import {
  DisruptionEvent,
  NewsArticle,
  RiskLevel,
  Supplier,
} from '@/types/supplier';

const riskLevelFromScore = (score: number): RiskLevel => {
  if (score <= 30) return 'low';
  if (score <= 60) return 'medium';
  if (score <= 80) return 'high';
  return 'critical';
};

const normalizeName = (nodeName: string) => nodeName.replace(/_/g, ' ');

const toIsoStringOrNow = (value?: string | null): string => {
  if (!value) return new Date().toISOString();
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return new Date().toISOString();
  return parsed.toISOString();
};

const dateOnly = (value?: string | null): string => {
  if (!value) return new Date().toISOString().slice(0, 10);
  return toIsoStringOrNow(value).slice(0, 10);
};

export const mapSupplier = (supplier: BackendSupplier): Supplier => {
  const riskScore = Math.round(supplier.current_risk_score ?? 0);

  return {
    id: supplier.node_name,
    name: normalizeName(supplier.node_name),
    country: supplier.country ?? 'Unknown',
    coordinates: [supplier.longitude, supplier.latitude],
    riskScore,
    criticality: supplier.criticality,
    riskLevel: riskLevelFromScore(riskScore),
  };
};

export const mapNewsArticle = (event: BackendEvent): NewsArticle => {
  return {
    id: String(event.id),
    title:
      event.article_title ??
      event.temporal_info?.event_description ??
      event.event_text_segment ??
      'Supply chain event update',
    source: event.article_source ?? 'Unknown Source',
    publishedAt: toIsoStringOrNow(event.article_timestamp),
    url: event.article_url || '#',
    matchedNode: event.matched_node ?? undefined,
    riskScore: event.risk_score ?? undefined,
    riskRelevanceScore: event.risk_relevance_score ?? undefined,
    riskSeverityScore: event.risk_severity_score ?? undefined,
    impactScore: event.impact_score ?? undefined,
    isPredictive: event.temporal_info?.is_predictive,
    predictedDate: event.temporal_info?.predicted_date,
    eventText: event.event_text_segment ?? undefined,
  };
};

export const mapDisruptionEvent = (event: BackendEvent): DisruptionEvent => {
  const severityScore = event.impact_score ?? event.risk_severity_score ?? event.risk_score ?? 0;
  const eventType = event.potential_event_types?.[0]?.replace(/_/g, ' ');
  const title =
    event.article_title ??
    eventType ??
    event.temporal_info?.event_description ??
    'Disruption Event';

  return {
    id: String(event.id),
    supplierId: event.matched_node ?? 'unknown',
    title,
    description: event.event_text_segment ?? 'No additional details provided.',
    date: dateOnly(event.temporal_info?.predicted_date ?? event.article_timestamp),
    severity: riskLevelFromScore(severityScore),
    riskScore: event.risk_score ?? undefined,
    riskRelevanceScore: event.risk_relevance_score ?? undefined,
    riskSeverityScore: event.risk_severity_score ?? undefined,
    isPredictive: event.temporal_info?.is_predictive,
    predictedDate: event.temporal_info?.predicted_date,
  };
};
