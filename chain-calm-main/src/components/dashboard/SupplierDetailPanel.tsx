import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, MapPin, AlertCircle, Calendar, Sparkles, Loader2, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Supplier, DisruptionEvent } from '@/types/supplier';
import { RiskBadge } from './RiskBadge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { api } from '@/lib/api';
import { useQuery } from '@tanstack/react-query';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
import { cn } from '@/lib/utils';

const TREND_COLORS = {
  up: 'hsl(4, 82%, 58%)',
  down: 'hsl(152, 72%, 42%)',
  stable: 'hsl(240, 5%, 48%)',
};

interface SupplierDetailPanelProps {
  supplier: Supplier | null;
  events?: DisruptionEvent[];
  isLoading?: boolean;
  onClose: () => void;
}

export function SupplierDetailPanel({ supplier, events = [], isLoading = false, onClose }: SupplierDetailPanelProps) {
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
  const trend: 'up' | 'down' | 'stable' = lastRisk > firstRisk ? 'up' : lastRisk < firstRisk ? 'down' : 'stable';

  useEffect(() => {
    setAiSummary(null); setAiModel(null); setAiError(null); setAiLoading(false);
  }, [supplier?.id]);

  const handleAiSummary = async () => {
    if (!supplier) return;
    setAiLoading(true); setAiError(null);
    try {
      const res = await api.postSupplierAiSummary(supplier.id);
      setAiSummary(res.summary); setAiModel(res.model_used);
    } catch (e) {
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
          transition={{ ease: [0.25, 1, 0.5, 1], duration: 0.28 }}
          className="w-80 h-full bg-card border-l border-border overflow-y-auto flex-shrink-0"
        >
          {/* Sticky header */}
          <div className="px-4 py-3 border-b border-border sticky top-0 bg-card/95 backdrop-blur-sm z-10">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="font-bold text-foreground leading-tight truncate">{supplier.name}</h2>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <MapPin className="w-3 h-3 text-muted-foreground shrink-0" />
                  <span className="text-xs font-mono text-muted-foreground">{supplier.country}</span>
                </div>
              </div>
              <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors mt-0.5 shrink-0" aria-label="Close panel">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="mt-2">
              <RiskBadge level={supplier.riskLevel} size="sm" />
            </div>
          </div>

          {/* Metrics */}
          <div className="px-4 py-4 space-y-4 border-b border-border">
            <div>
              <div className="flex items-end justify-between mb-1.5">
                <span className="text-xs font-mono text-muted-foreground tracking-widest uppercase">Exposure</span>
                <span className="text-3xl font-bold font-mono tabular-nums leading-none text-foreground">{supplier.riskScore}%</span>
              </div>
              <Progress value={supplier.riskScore} className="h-1" aria-label={`Exposure: ${supplier.riskScore}%`} />
            </div>
            <div>
              <div className="flex items-end justify-between mb-1.5">
                <span className="text-xs font-mono text-muted-foreground tracking-widest uppercase">Criticality</span>
                <span className="text-xl font-bold font-mono tabular-nums leading-none text-foreground">
                  {supplier.criticality}<span className="text-xs font-normal text-muted-foreground">/5</span>
                </span>
              </div>
              <Progress value={(supplier.criticality / 5) * 100} className="h-1" aria-label={`Criticality: ${supplier.criticality}/5`} />
            </div>
          </div>

          {/* Forecast sparkline */}
          {forecastData.length > 0 && (
            <div className="px-4 py-4 border-b border-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono text-muted-foreground tracking-widest uppercase">14-Day Trajectory</span>
                <div className="flex items-center gap-1">
                  {trend === 'up' && <TrendingUp className="w-3 h-3 text-risk-high" />}
                  {trend === 'down' && <TrendingDown className="w-3 h-3 text-risk-low" />}
                  {trend === 'stable' && <Minus className="w-3 h-3 text-muted-foreground" />}
                  <span className={cn('text-xs font-mono font-bold uppercase',
                    trend === 'up' && 'text-risk-high',
                    trend === 'down' && 'text-risk-low',
                    trend === 'stable' && 'text-muted-foreground'
                  )}>{trend}</span>
                </div>
              </div>
              <div className="h-16 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={forecastData}>
                    <YAxis domain={['auto', 'auto']} hide />
                    <Line type="monotone" dataKey="yhat" stroke={TREND_COLORS[trend]} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* AI Summary */}
          <div className="px-4 py-4 border-b border-border">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono text-muted-foreground tracking-widest uppercase flex items-center gap-1.5">
                <Sparkles className="w-3 h-3 text-primary" />
                Intel Summary
              </span>
              <Button type="button" size="sm" variant="outline" disabled={aiLoading} onClick={handleAiSummary}
                className="h-6 px-2 text-xs font-mono shrink-0">
                {aiLoading ? <><Loader2 className="w-3 h-3 mr-1 animate-spin" />Working…</> : 'Generate'}
              </Button>
            </div>
            {aiError && (
              <p className="text-xs font-mono text-risk-high bg-risk-high/10 p-2 rounded border border-risk-high/20">{aiError}</p>
            )}
            {aiSummary && (
              <p className="text-sm text-foreground/85 leading-relaxed mt-2 font-sans">{aiSummary}</p>
            )}
            {aiModel && (
              <p className="text-xs font-mono text-muted-foreground mt-2 text-right">via {aiModel}</p>
            )}
            {!aiSummary && !aiLoading && !aiError && (
              <p className="text-xs font-mono text-muted-foreground">AI-synthesised risk narrative for this node.</p>
            )}
          </div>

          {/* Recent Disruptions */}
          <div className="px-4 py-4">
            <h3 className="text-xs font-mono text-muted-foreground tracking-widest uppercase mb-3 flex items-center gap-1.5">
              <AlertCircle className="w-3 h-3" />
              Recent Disruptions
            </h3>
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="p-3 rounded border border-border space-y-2">
                    <div className="h-3 bg-secondary/50 rounded animate-pulse w-5/6" />
                    <div className="h-2.5 bg-secondary/50 rounded animate-pulse w-3/4" />
                    <div className="h-2.5 bg-secondary/50 rounded animate-pulse w-1/2" />
                  </div>
                ))}
              </div>
            ) : events.length > 0 ? (
              <div className="space-y-2">
                {events.map(event => (
                  <div key={event.id} className="p-3 rounded border border-border bg-secondary/20 hover:bg-secondary/40 transition-colors">
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <p className="text-xs font-medium text-foreground leading-snug">{event.title}</p>
                      <RiskBadge level={event.severity} size="sm" showLabel={false} />
                    </div>
                    {event.description && (
                      <p className="text-sm text-muted-foreground leading-relaxed mb-2">{event.description}</p>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      {typeof event.riskScore === 'number' && (
                        <span className="text-xs font-mono bg-primary/12 text-primary border border-primary/25 px-1.5 py-0.5 rounded">
                          RISK {Math.round(event.riskScore)}%
                        </span>
                      )}
                      {typeof event.impactScore === 'number' && (
                        <span className="text-xs font-mono bg-risk-medium/12 text-risk-medium border border-risk-medium/25 px-1.5 py-0.5 rounded">
                          IMPACT {Math.round(event.impactScore)}%
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 mt-2 text-xs font-mono text-muted-foreground">
                      <Calendar className="w-2.5 h-2.5" />
                      {event.predictedDate ?? event.date}
                      {event.isPredictive && (
                        <span className="bg-primary/15 text-primary px-1.5 py-0.5 rounded ml-1">PREDICTIVE</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs font-mono text-muted-foreground">No recent disruptions recorded.</p>
            )}
          </div>

          <div className="px-4 py-3 border-t border-border">
            <p className="text-xs font-mono text-muted-foreground">Refreshes with each RSS cycle.</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
