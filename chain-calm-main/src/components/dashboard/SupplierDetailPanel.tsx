import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, MapPin, AlertCircle, Calendar, MapPinned, Sparkles, Loader2, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Supplier, DisruptionEvent, BackendHybridForecastPoint } from '@/types/supplier';
import { RiskBadge } from './RiskBadge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { api } from '@/lib/api';
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
import { cn } from '@/lib/utils';

interface SupplierDetailPanelProps {
  supplier: Supplier | null;
  events?: DisruptionEvent[];
  isLoading?: boolean;
  onClose: () => void;
}

export function SupplierDetailPanel({
  supplier,
  events = [],
  isLoading = false,
  onClose,
}: SupplierDetailPanelProps) {
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [aiModel, setAiModel] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const forecastQuery = useQuery({
    queryKey: ['forecast', 'hybrid', supplier?.id],
    queryFn: () => api.getSupplierForecast(supplier?.id || ''),
    enabled: !!supplier?.id,
  });

  const forecastData = forecastQuery.data || [];
  const lastRisk = forecastData[forecastData.length - 1]?.yhat;
  const firstRisk = forecastData[0]?.yhat;
  const trend = lastRisk > firstRisk ? 'up' : (lastRisk < firstRisk ? 'down' : 'stable');

  useEffect(() => {
    setAiSummary(null);
    setAiModel(null);
    setAiError(null);
    setAiLoading(false);
  }, [supplier?.id]);

  const handleAiSummary = async () => {
    if (!supplier) return;
    setAiLoading(true);
    setAiError(null);
    try {
      const res = await api.postSupplierAiSummary(supplier.id);
      setAiSummary(res.summary);
      setAiModel(res.model_used);
    } catch (e) {
      setAiSummary(null);
      setAiModel(null);
      setAiError(e instanceof Error ? e.message : 'Summary request failed');
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {supplier && (
        <motion.div
          initial={{ x: '100%', opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: '100%', opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="w-96 h-full bg-card border-l border-border overflow-y-auto"
        >
          {/* Header */}
          <div className="p-5 border-b border-border sticky top-0 bg-card/95 backdrop-blur-sm z-10">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-semibold text-foreground">
                  {supplier.name}
                </h2>
                <div className="flex items-center gap-2 mt-1 text-muted-foreground">
                  <MapPin className="w-4 h-4" />
                  <span className="text-sm">{supplier.country}</span>
                </div>
              </div>
              <Button variant="ghost" size="icon" onClick={onClose}>
                <X className="w-5 h-5" />
              </Button>
            </div>
            <div className="mt-3">
              <RiskBadge level={supplier.riskLevel} />
            </div>
          </div>

          {/* Real backend fields */}
          <div className="p-5 space-y-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground">Exposure</span>
                <span className="text-sm text-muted-foreground">{supplier.riskScore}%</span>
              </div>
              <Progress value={supplier.riskScore} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                0–100 roll-up from recent events (prefers model impact when present).
              </p>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground">Criticality</span>
                <span className="text-sm text-muted-foreground">{supplier.criticality}</span>
              </div>
              <Progress value={(supplier.criticality / 5) * 100} className="h-2" />
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground">Coordinates</span>
                <span className="text-sm text-muted-foreground">
                  {supplier.coordinates[1].toFixed(2)}, {supplier.coordinates[0].toFixed(2)}
                </span>
              </div>
              <div className="text-sm text-muted-foreground flex items-center gap-2">
                <MapPinned className="w-4 h-4" />
                Real supplier location from backend
              </div>
            </div>

            {forecastData.length > 0 && (
              <div className="p-4 rounded-xl border border-primary/20 bg-primary/5 shadow-inner">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex flex-col">
                    <span className="text-[10px] text-muted-foreground uppercase tracking-[0.15em] font-bold">Risk Trajectory</span>
                    <span className="text-xs text-muted-foreground">Next 14 Days</span>
                  </div>
                  <div className="flex items-center gap-2 px-2 py-1 rounded-full bg-background/50 border border-border">
                    {trend === 'up' && <TrendingUp className="w-3 h-3 text-risk-high" />}
                    {trend === 'down' && <TrendingDown className="w-3 h-3 text-risk-low" />}
                    {trend === 'stable' && <Minus className="w-3 h-3 text-muted-foreground" />}
                    <span className={cn(
                      "text-[10px] font-bold uppercase tracking-wider",
                      trend === 'up' && "text-risk-high",
                      trend === 'down' && "text-risk-low",
                      trend === 'stable' && "text-muted-foreground"
                    )}>
                      {trend}
                    </span>
                  </div>
                </div>
                <div className="h-20 w-full relative group">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={forecastData}>
                      <YAxis domain={['auto', 'auto']} hide />
                      <Line 
                        type="monotone" 
                        dataKey="yhat" 
                        stroke={trend === 'up' ? 'hsl(0, 84%, 60%)' : (trend === 'down' ? 'hsl(142, 76%, 46%)' : '#94a3b8')} 
                        strokeWidth={3} 
                        dot={false}
                        className="drop-shadow-[0_0_8px_rgba(255,255,255,0.2)]"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            <div className="rounded-lg border border-border bg-secondary/30 p-3 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-foreground flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-primary" />
                  AI Intelligence Summary
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  disabled={aiLoading}
                  onClick={handleAiSummary}
                  className="shrink-0"
                >
                  {aiLoading ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                      Synthesizing…
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5 mr-1" />
                      Generate
                    </>
                  )}
                </Button>
              </div>
              
              {aiError && (
                <p className="text-xs text-risk-high bg-risk-high/10 p-2 rounded border border-risk-high/20">
                  {aiError}
                </p>
              )}
              
              {aiSummary && (
                <div className="text-sm text-foreground leading-relaxed whitespace-pre-wrap border-t border-border pt-3 mt-1 italic opacity-90">
                  "{aiSummary}"
                </div>
              )}
              
              {aiModel && (
                <p className="text-[10px] text-muted-foreground pt-1 text-right">
                  Model: {aiModel}
                </p>
              )}
              
              {!aiSummary && !aiLoading && !aiError && (
                <p className="text-xs text-muted-foreground">
                  Generate an AI-powered summary of recent events and their projected impact on this node.
                </p>
              )}
            </div>
          </div>

          <Separator />

          {/* Recent Disruptions */}
          <div className="p-5">
            <h3 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              Recent Disruptions
            </h3>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading disruptions...</p>
            ) : events.length > 0 ? (
              <div className="space-y-3">
                {events.map((event) => (
                  <div
                    key={event.id}
                    className="p-3 rounded-lg bg-secondary/50 border border-border"
                  >
                    <div className="flex items-start justify-between">
                      <p className="text-sm font-medium text-foreground">{event.title}</p>
                      <RiskBadge level={event.severity} size="sm" showLabel={false} />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{event.description}</p>
                    {(typeof event.riskScore === 'number' || typeof event.riskRelevanceScore === 'number' || typeof event.riskSeverityScore === 'number') && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {typeof event.impactScore === 'number' && (
                          <span className="inline-flex items-center rounded-full bg-risk-medium/15 px-2 py-0.5 text-[11px] font-medium text-risk-medium">
                            {typeof event.predictedImpactScore === 'number' ? 'Impact (Model)' : 'Impact'} {Math.round(event.impactScore)}%
                          </span>
                        )}
                        {typeof event.predictedImpactScore === 'number' && (
                          <span className="inline-flex items-center rounded-full bg-secondary/70 px-2 py-0.5 text-[11px] font-medium text-secondary-foreground">
                            Model
                          </span>
                        )}
                        {typeof event.riskScore === 'number' && (
                          <span className="inline-flex items-center rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-medium text-primary">
                            Risk {Math.round(event.riskScore)}%
                          </span>
                        )}
                        {typeof event.riskRelevanceScore === 'number' && (
                          <span className="inline-flex items-center rounded-full bg-secondary/70 px-2 py-0.5 text-[11px] font-medium text-secondary-foreground">
                            Relevance {Math.round(event.riskRelevanceScore)}%
                          </span>
                        )}
                        {typeof event.riskSeverityScore === 'number' && (
                          <span className="inline-flex items-center rounded-full bg-secondary/70 px-2 py-0.5 text-[11px] font-medium text-secondary-foreground">
                            Severity {Math.round(event.riskSeverityScore)}%
                          </span>
                        )}
                      </div>
                    )}
                    <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                      <Calendar className="w-3 h-3" />
                      {event.predictedDate ?? event.date}
                      {event.isPredictive && (
                        <span className="px-2 py-0.5 rounded bg-primary/20 text-primary">
                          Predictive
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No recent disruptions</p>
            )}
          </div>

          {/* Last Updated */}
          <div className="p-5 border-t border-border">
            <p className="text-xs text-muted-foreground">
              Backend-sourced supplier record
            </p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
