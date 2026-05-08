import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, MapPin, AlertCircle, Calendar, MapPinned, Sparkles, Loader2 } from 'lucide-react';
import { Supplier, DisruptionEvent } from '@/types/supplier';
import { RiskBadge } from './RiskBadge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { api } from '@/lib/api';

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

            <div className="rounded-lg border border-border bg-secondary/30 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-foreground flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-primary" />
                  AI summary
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
                      Working…
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5 mr-1" />
                      Generate
                    </>
                  )}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Runs only when you click Generate. Uses OpenRouter on the server (
                <code className="text-[10px]">OPENROUTER_API_KEY</code>).
              </p>
              {aiError && (
                <p className="text-xs text-risk-high whitespace-pre-wrap">{aiError}</p>
              )}
              {aiSummary && (
                <div className="text-sm text-foreground whitespace-pre-wrap border-t border-border pt-2 mt-1">
                  {aiSummary}
                </div>
              )}
              {aiModel && (
                <p className="text-[10px] text-muted-foreground">Model: {aiModel}</p>
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
