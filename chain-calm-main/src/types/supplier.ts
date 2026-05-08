export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface Supplier {
  id: string;
  name: string;
  country: string;
  coordinates: [number, number];
  riskScore: number;
  criticality: number;
  riskLevel: RiskLevel;
}

export interface DisruptionEvent {
  id: string;
  supplierId: string;
  title: string;
  description: string;
  date: string;
  severity: RiskLevel;
  riskScore?: number;
  riskRelevanceScore?: number;
  riskSeverityScore?: number;
  impactScore?: number;
  predictedImpactScore?: number;
  isPredictive?: boolean;
  predictedDate?: string;
}

export interface ResilienceHistory {
  date: string;
  riskScore: number;
  resilienceScore: number;
}
