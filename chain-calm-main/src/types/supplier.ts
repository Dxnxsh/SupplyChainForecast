export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface Supplier {
  id: string;
  name: string;
  country: string;
  coordinates: [number, number];
  riskScore: number;
  criticality: number;
  riskLevel: RiskLevel;
  products?: string[];
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

export interface ColoredEdge {
  from: [number, number];
  to: [number, number];
  fromId: string;
  toId: string;
  sourceRiskLevel: RiskLevel;
  isPulsing: boolean;
  isActive: boolean;
}
