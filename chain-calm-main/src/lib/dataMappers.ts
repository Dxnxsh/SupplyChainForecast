import { BackendEvent, BackendSupplier } from '@/lib/api';
import { DisruptionEvent, RiskLevel, Supplier } from '@/types/supplier';

const riskLevelFromScore = (score: number): RiskLevel => {
  if (score <= 30) return 'low';
  if (score <= 60) return 'medium';
  if (score <= 80) return 'high';
  return 'critical';
};

/** Buckets for supplier node exposure (0–100 roll-up). Wider than event scores so the map is not all red when many nodes sit in the 70–95 range. */
const supplierExposureLevel = (exposure: number): RiskLevel => {
  if (exposure <= 8) return 'low';
  if (exposure <= 18) return 'medium';
  if (exposure <= 30) return 'high';
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

const getEffectiveImpactScore = (event: BackendEvent): number | undefined => {
  if (event.predicted_impact_score != null) return event.predicted_impact_score;
  if (event.impact_score != null) return event.impact_score;
  return undefined;
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
    riskLevel: supplierExposureLevel(riskScore),
    products: supplier.products ?? [],
  };
};

export const mapDisruptionEvent = (event: BackendEvent): DisruptionEvent => {
  const impactScore = getEffectiveImpactScore(event);
  const severityScore = impactScore ?? event.risk_severity_score ?? event.risk_score ?? 0;
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
    impactScore,
    predictedImpactScore: event.predicted_impact_score ?? undefined,
    isPredictive: event.temporal_info?.is_predictive,
    predictedDate: event.temporal_info?.predicted_date,
  };
};
