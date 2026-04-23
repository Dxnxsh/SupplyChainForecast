import { motion } from 'framer-motion';
import { ExternalLink, Calendar, MapPin } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/Header';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';
import { formatBackendDate } from '@/lib/dateUtils';

export default function NewsEventsPage() {
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

      <div className="flex-1 p-6 overflow-auto">
        {(suppliersQuery.isError || latestEventsQuery.isError || forecastedEventsQuery.isError) && (
          <div className="mb-4 rounded-lg border border-risk-high/40 bg-risk-high/10 px-4 py-3 text-sm text-risk-high">
            Could not load live news and events from the backend.
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* News Articles */}
          <div>
            <h2 className="text-lg font-semibold text-foreground mb-4">Latest Events</h2>
            <div className="space-y-4">
              {latestEvents.map((event, index) => {
                const supplier = suppliers.find((s) => s.id === event.matched_node);
                const primaryDate = formatBackendDate(event.article_timestamp);
                const fallbackDate = event.temporal_info?.predicted_date
                  ? formatBackendDate(event.temporal_info.predicted_date)
                  : null;
                const displayDate = primaryDate !== 'Unknown date'
                  ? primaryDate
                  : (fallbackDate && fallbackDate !== 'Unknown date' ? fallbackDate : null);

                return (
                  <motion.div
                    key={event.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.1 }}
                    className="glass-card rounded-xl p-5 hover:border-primary/30 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-xs font-medium text-primary">
                            {event.article_source ?? 'Unknown Source'}
                          </span>
                          {displayDate && (
                            <>
                              <span className="text-xs text-muted-foreground">•</span>
                              <span className="text-xs text-muted-foreground flex items-center gap-1">
                                <Calendar className="w-3 h-3" />
                                {displayDate}
                              </span>
                            </>
                          )}
                        </div>
                        <h3 className="font-medium text-foreground mb-2">
                          {event.article_title ?? 'Untitled event'}
                        </h3>
                        <div className="flex flex-wrap gap-2">
                          {supplier && <Badge variant="secondary" className="text-xs">{supplier.name}</Badge>}
                          {event.potential_event_types?.[0] && (
                            <Badge variant="outline" className="text-xs border-border">
                              {event.potential_event_types[0].replace(/_/g, ' ')}
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-2 text-right">
                        <Badge className="bg-primary/15 text-primary border-0">Risk {Math.round(event.risk_score ?? 0)}%</Badge>
                        {typeof event.impact_score === 'number' && (
                          <Badge className="bg-risk-medium/15 text-risk-medium border-0">Impact {Math.round(event.impact_score)}%</Badge>
                        )}
                        {event.article_url && event.article_url !== '#' && (
                          <a href={event.article_url} target="_blank" rel="noreferrer" className="text-muted-foreground hover:text-foreground">
                            <ExternalLink className="w-4 h-4" />
                          </a>
                        )}
                      </div>
                    </div>
                    {event.event_text_segment && (
                      <p className="text-sm text-muted-foreground mt-3">{event.event_text_segment}</p>
                    )}
                  </motion.div>
                );
              })}
              {latestEventsQuery.isLoading && (
                <p className="text-sm text-muted-foreground">Loading latest events...</p>
              )}
            </div>
          </div>

          {/* Disruption Events */}
          <div>
            <h2 className="text-lg font-semibold text-foreground mb-4">Forecasted Events</h2>
            <div className="space-y-4">
              {forecastedEvents.map((event, index) => {
                const supplier = suppliers.find((s) => s.id === event.matched_node);

                return (
                  <motion.div
                    key={event.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.1 }}
                    className="glass-card rounded-xl p-5 transition-colors border-risk-high/20"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h3 className="font-medium text-foreground">
                          {event.article_title ?? event.temporal_info?.event_description ?? 'Forecasted event'}
                        </h3>
                        <p className="text-sm text-muted-foreground mt-1">
                          {event.event_text_segment ?? 'Forecast generated from backend predictive pipeline.'}
                        </p>
                      </div>
                      <Badge className="bg-risk-medium/15 text-risk-medium border-0">
                        Risk {Math.round(event.risk_score ?? 0)}%
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {supplier && (
                          <Badge variant="secondary" className="text-xs">
                            {supplier.name}
                          </Badge>
                        )}
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                          <MapPin className="w-3 h-3" />
                          {event.matched_node ?? 'Unassigned node'}
                        </span>
                      </div>
                      {event.temporal_info?.predicted_date && (
                        <Badge className="bg-primary/15 text-primary border-0">
                          Predicts {event.temporal_info.predicted_date}
                        </Badge>
                      )}
                    </div>
                  </motion.div>
                );
              })}
              {forecastedEventsQuery.isLoading && (
                <p className="text-sm text-muted-foreground">Loading forecasted events...</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
