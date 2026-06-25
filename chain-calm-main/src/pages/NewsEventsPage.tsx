import { useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { ExternalLink, Calendar, MapPin, ChevronDown } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/Header';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';
import { formatBackendDate } from '@/lib/dateUtils';

export default function NewsEventsPage() {
  const shouldReduceMotion = useReducedMotion();
  const [expandedCards, setExpandedCards] = useState<Set<string | number>>(new Set());
  const subtleBadgeClass = 'text-xs font-mono bg-secondary/50 text-muted-foreground border border-border/50 px-1.5 py-0.5 rounded';

  const toggleExpand = (id: string | number) => {
    setExpandedCards((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const suppliersQuery = useQuery({
    queryKey: ['suppliers'],
    queryFn: api.getSuppliers,
  });

  const latestEventsQuery = useQuery({
    queryKey: ['events', 'latest', 120],
    queryFn: () => api.getLatestEvents(120),
  });

  const forecastedEventsQuery = useQuery({
    queryKey: ['events', 'forecasted', 120],
    queryFn: () => api.getForecastedEvents(120),
  });

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);
  const latestEvents = latestEventsQuery.data ?? [];
  const forecastedEvents = forecastedEventsQuery.data ?? [];

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      <Header
        title="News & Events"
        subtitle="Related news and disruption events"
      />

      <div className="flex-1 p-5 overflow-auto">
        {(suppliersQuery.isError || latestEventsQuery.isError || forecastedEventsQuery.isError) && (
          <div className="mb-4 rounded border border-risk-high/30 bg-risk-high/8 px-3 py-2 text-xs font-mono text-risk-high">
            BACKEND UNREACHABLE — could not load news and events
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* News Articles */}
          <div>
            <div className="flex items-center justify-between pb-2.5 mb-4 border-b border-border">
              <span className="text-xs font-mono tracking-widest uppercase text-muted-foreground">Latest Events</span>
              {!latestEventsQuery.isLoading && (
                <span className="text-xs font-mono text-muted-foreground tabular-nums">{latestEvents.length}</span>
              )}
            </div>
            <div className="space-y-3">
              {latestEvents.map((event, index) => {
                const matchedNodeRaw = event.matched_node;
                const supplier = suppliers.find((s) =>
                  Array.isArray(matchedNodeRaw)
                    ? (matchedNodeRaw as string[]).includes(s.id)
                    : s.id === matchedNodeRaw
                );
                const hasModelImpact = typeof event.predicted_impact_score === 'number';
                const effectiveImpact = hasModelImpact
                  ? event.predicted_impact_score
                  : event.impact_score;
                const primaryDate = formatBackendDate(event.article_timestamp);
                const fallbackDate = event.temporal_info?.predicted_date
                  ? formatBackendDate(event.temporal_info.predicted_date)
                  : null;
                const displayDate = primaryDate !== 'Unknown date'
                  ? primaryDate
                  : (fallbackDate && fallbackDate !== 'Unknown date' ? fallbackDate : null);
                const isExpanded = expandedCards.has(event.id);
                const hasSecondary =
                  hasModelImpact ||
                  typeof event.risk_relevance_score === 'number' ||
                  typeof event.risk_severity_score === 'number';
                const delay = shouldReduceMotion ? 0 : Math.min(index * 0.05, 0.25);

                return (
                  <motion.div
                    key={event.id}
                    initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay }}
                    className="bg-card border border-border rounded p-4 hover:border-primary/30 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="text-xs font-mono text-primary truncate tracking-wider">
                            {event.article_source ?? 'UNKNOWN SOURCE'}
                          </span>
                          {displayDate && (
                            <>
                              <span className="text-muted-foreground/40">·</span>
                              <span className="text-xs font-mono text-muted-foreground flex items-center gap-1 shrink-0">
                                <Calendar className="w-2.5 h-2.5" />
                                {displayDate}
                              </span>
                            </>
                          )}
                        </div>
                        <h3 className="text-sm font-medium text-foreground mb-2 leading-snug">
                          {event.article_title ?? 'Untitled event'}
                        </h3>
                        <div className="flex flex-wrap gap-1.5">
                          {supplier && (
                            <span className="text-xs font-mono bg-secondary/60 text-foreground border border-border px-1.5 py-0.5 rounded">
                              {supplier.name}
                            </span>
                          )}
                          {event.potential_event_types?.[0] && (
                            <span className="text-xs font-mono text-muted-foreground border border-border/60 px-1.5 py-0.5 rounded">
                              {event.potential_event_types[0].replace(/_/g, ' ')}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col items-end shrink-0">
                        {/* Risk numeral + label — tight unit */}
                        <div className="flex flex-col items-end gap-0.5">
                          <span className="text-lg font-bold font-mono tabular-nums text-primary leading-none">
                            {Math.round(event.risk_score ?? 0)}%
                          </span>
                          <span className="text-xs font-mono text-muted-foreground tracking-widest">RISK</span>
                        </div>
                        {typeof effectiveImpact === 'number' && (
                          <span className="text-xs font-mono bg-risk-medium/12 text-risk-medium border border-risk-medium/30 px-1.5 py-0.5 rounded mt-2">
                            IMP {Math.round(effectiveImpact)}%
                          </span>
                        )}
                        <div className="flex items-center gap-2 mt-3">
                          {hasSecondary && (
                            <button
                              onClick={() => toggleExpand(event.id)}
                              className="text-xs font-mono text-muted-foreground hover:text-foreground flex items-center gap-0.5 transition-colors"
                            >
                              <motion.span
                                animate={{ rotate: isExpanded ? 180 : 0 }}
                                transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
                                style={{ display: 'flex' }}
                              >
                                <ChevronDown className="w-3 h-3" />
                              </motion.span>
                              MORE
                            </button>
                          )}
                          {event.article_url && event.article_url !== '#' && (
                            <a href={event.article_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-primary transition-colors">
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Secondary signals — animated expand/collapse */}
                    <AnimatePresence initial={false}>
                      {isExpanded && hasSecondary && (
                        <motion.div
                          key="detail"
                          initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
                          transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
                          style={{ overflow: 'hidden' }}
                        >
                          <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-border">
                            {hasModelImpact && <span className={subtleBadgeClass}>MODEL</span>}
                            {typeof event.risk_relevance_score === 'number' && (
                              <span className={subtleBadgeClass}>REL {Math.round(event.risk_relevance_score)}%</span>
                            )}
                            {typeof event.risk_severity_score === 'number' && (
                              <span className={subtleBadgeClass}>SEV {Math.round(event.risk_severity_score)}%</span>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    {event.event_text_segment && (
                      <p className="text-sm text-muted-foreground mt-3 pt-3 border-t border-border/60 leading-relaxed">
                        {event.event_text_segment}
                      </p>
                    )}
                  </motion.div>
                );
              })}
              {latestEventsQuery.isLoading &&
                Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="bg-card border border-border rounded-xl p-4 space-y-3">
                    <div className="flex justify-between gap-4">
                      <div className="flex-1 space-y-2">
                        <div className="h-3 bg-secondary/50 rounded animate-pulse w-1/3" />
                        <div className="h-3.5 bg-secondary/50 rounded animate-pulse w-5/6" />
                        <div className="h-3.5 bg-secondary/50 rounded animate-pulse w-3/4" />
                      </div>
                      <div className="space-y-1.5">
                        <div className="h-5 w-10 bg-secondary/50 rounded animate-pulse" />
                        <div className="h-3 w-8 bg-secondary/50 rounded animate-pulse mx-auto" />
                      </div>
                    </div>
                  </div>
                ))}
              {!latestEventsQuery.isLoading && latestEvents.length === 0 && (
                <div className="py-10 text-center">
                  <p className="text-xs font-mono text-muted-foreground tracking-widest">NO EVENTS</p>
                </div>
              )}
            </div>
          </div>

          {/* Disruption Events */}
          <div>
            <div className="flex items-center justify-between pb-2.5 mb-4 border-b border-border">
              <span className="text-xs font-mono tracking-widest uppercase text-muted-foreground">Forecasted Events</span>
              {!forecastedEventsQuery.isLoading && (
                <span className="text-xs font-mono text-muted-foreground tabular-nums">{forecastedEvents.length}</span>
              )}
            </div>
            <div className="space-y-3">
              {forecastedEvents.map((event, index) => {
                const matchedNodeRaw = event.matched_node;
                const supplier = suppliers.find((s) =>
                  Array.isArray(matchedNodeRaw)
                    ? (matchedNodeRaw as string[]).includes(s.id)
                    : s.id === matchedNodeRaw
                );
                const hasModelImpact = typeof event.predicted_impact_score === 'number';
                const effectiveImpact = hasModelImpact
                  ? event.predicted_impact_score
                  : event.impact_score;
                const isExpanded = expandedCards.has(`f-${event.id}`);
                const hasSecondary =
                  hasModelImpact ||
                  typeof event.risk_relevance_score === 'number' ||
                  typeof event.risk_severity_score === 'number';
                const delay = shouldReduceMotion ? 0 : Math.min(index * 0.05, 0.25);

                return (
                  <motion.div
                    key={event.id}
                    initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay }}
                    className="bg-card border border-border rounded p-4 hover:border-primary/30 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-4 mb-2">
                      <div className="flex-1 min-w-0">
                        <h3 className="text-sm font-medium text-foreground leading-snug">
                          {event.article_title ?? event.temporal_info?.event_description ?? 'Forecasted event'}
                        </h3>
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                          {event.event_text_segment ?? 'Forecast generated from backend predictive pipeline.'}
                        </p>
                      </div>
                      <div className="flex flex-col items-end shrink-0">
                        <div className="flex flex-col items-end gap-0.5">
                          <span className="text-lg font-bold font-mono tabular-nums text-risk-medium leading-none">
                            {Math.round(event.risk_score ?? 0)}%
                          </span>
                          <span className="text-xs font-mono text-muted-foreground tracking-widest">RISK</span>
                        </div>
                        {typeof effectiveImpact === 'number' && (
                          <span className="text-xs font-mono bg-risk-medium/12 text-risk-medium border border-risk-medium/30 px-1.5 py-0.5 rounded mt-2">
                            IMP {Math.round(effectiveImpact)}%
                          </span>
                        )}
                        {hasSecondary && (
                          <button
                            onClick={() => toggleExpand(`f-${event.id}`)}
                            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-0.5 transition-colors mt-3"
                          >
                            <motion.span
                              animate={{ rotate: isExpanded ? 180 : 0 }}
                              transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
                              style={{ display: 'flex' }}
                            >
                              <ChevronDown className="w-3 h-3" />
                            </motion.span>
                            Detail
                          </button>
                        )}
                      </div>
                    </div>

                    <AnimatePresence initial={false}>
                      {isExpanded && hasSecondary && (
                        <motion.div
                          key="fdetail"
                          initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, height: 0 }}
                          transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
                          style={{ overflow: 'hidden' }}
                        >
                          <div className="flex flex-wrap gap-1.5 py-2.5 border-t border-b border-border mb-2">
                            {hasModelImpact && <span className={subtleBadgeClass}>MODEL</span>}
                            {typeof event.risk_relevance_score === 'number' && (
                              <span className={subtleBadgeClass}>REL {Math.round(event.risk_relevance_score)}%</span>
                            )}
                            {typeof event.risk_severity_score === 'number' && (
                              <span className={subtleBadgeClass}>SEV {Math.round(event.risk_severity_score)}%</span>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        {supplier && (
                          <span className="text-xs font-mono bg-secondary/60 text-foreground border border-border px-1.5 py-0.5 rounded">
                            {supplier.name}
                          </span>
                        )}
                        {!supplier && (
                          <span className="text-xs font-mono text-muted-foreground flex items-center gap-1">
                            <MapPin className="w-2.5 h-2.5" />
                            {Array.isArray(matchedNodeRaw) ? matchedNodeRaw[0] : (matchedNodeRaw ?? 'UNASSIGNED')}
                          </span>
                        )}
                      </div>
                      {event.temporal_info?.predicted_date && (
                        <span className="text-xs font-mono bg-primary/12 text-primary border border-primary/25 px-1.5 py-0.5 rounded">
                          {event.temporal_info.predicted_date}
                        </span>
                      )}
                    </div>
                  </motion.div>
                );
              })}
              {forecastedEventsQuery.isLoading &&
                Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="bg-card border border-border rounded-xl p-4 space-y-3">
                    <div className="flex justify-between gap-4">
                      <div className="flex-1 space-y-2">
                        <div className="h-3.5 bg-secondary/50 rounded animate-pulse w-5/6" />
                        <div className="h-3 bg-secondary/50 rounded animate-pulse w-3/4" />
                        <div className="h-3 bg-secondary/50 rounded animate-pulse w-2/3" />
                      </div>
                      <div className="space-y-1.5">
                        <div className="h-5 w-10 bg-secondary/50 rounded animate-pulse" />
                        <div className="h-3 w-8 bg-secondary/50 rounded animate-pulse mx-auto" />
                      </div>
                    </div>
                  </div>
                ))}
              {!forecastedEventsQuery.isLoading && forecastedEvents.length === 0 && (
                <div className="py-10 text-center">
                  <p className="text-xs font-mono text-muted-foreground tracking-widest">NO FORECASTS</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
