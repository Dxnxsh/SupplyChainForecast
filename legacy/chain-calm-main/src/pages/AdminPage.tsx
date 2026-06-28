import { useState, useEffect } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw, Database, Users, Activity, CheckCircle, AlertCircle, Rss,
} from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';
import { RiskBadge } from '@/components/dashboard/RiskBadge';

export default function AdminPage() {
  const [isUpdating, setIsUpdating] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const queryClient = useQueryClient();
  const shouldReduceMotion = useReducedMotion();

  const suppliersQuery = useQuery({ queryKey: ['suppliers'], queryFn: api.getSuppliers });
  const summaryQuery = useQuery({ queryKey: ['summary'], queryFn: api.getSummary });
  const statusQuery = useQuery({ queryKey: ['rssStatus'], queryFn: api.getRssIngestStatus, refetchInterval: 1000 });

  const isCurrentlyIngesting = isIngesting || (statusQuery.data?.is_running ?? false);
  const [prevRunning, setPrevRunning] = useState(false);

  useEffect(() => {
    const isRunning = statusQuery.data?.is_running ?? false;
    if (prevRunning && !isRunning) { setIsIngesting(false); handleTriggerUpdate(); }
    setPrevRunning(isRunning);
  }, [statusQuery.data?.is_running, prevRunning]);

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);

  const handleTriggerIngest = async () => {
    setIsIngesting(true);
    try { await api.triggerRssIngest(); }
    catch (e) { if (import.meta.env.DEV) console.error(e); setIsIngesting(false); }
  };

  const handleTriggerUpdate = async () => {
    setIsUpdating(true);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['suppliers'] }),
      queryClient.invalidateQueries({ queryKey: ['summary'] }),
      queryClient.invalidateQueries({ queryKey: ['events'] }),
      queryClient.invalidateQueries({ queryKey: ['forecast'] }),
    ]);
    setIsUpdating(false);
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      <Header title="Admin" subtitle="SYSTEM CONTROL" />

      <div className="flex-1 p-5 overflow-auto space-y-5">
        {(suppliersQuery.isError || summaryQuery.isError) && (
          <div className="rounded border border-risk-high/30 bg-risk-high/8 px-3 py-2 text-xs font-mono text-risk-high">
            BACKEND UNREACHABLE — check API server on port 8000
          </div>
        )}

        {/* System status strip */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-border rounded overflow-hidden">
          {[
            {
              label: 'DATABASE',
              icon: Database,
              value: suppliersQuery.isError ? 'OFFLINE' : 'ONLINE',
              valueColor: suppliersQuery.isError ? 'text-risk-high' : 'text-risk-low',
              dot: suppliersQuery.isError ? 'bg-risk-high' : 'bg-risk-low',
            },
            {
              label: 'SUPPLIERS',
              icon: Users,
              value: String(suppliers.length),
              valueColor: 'text-foreground',
              dot: null,
            },
            {
              label: 'EVENTS',
              icon: Activity,
              value: String(summaryQuery.data?.total_events ?? '—'),
              valueColor: 'text-foreground',
              dot: null,
            },
            {
              label: 'SYSTEM',
              icon: Activity,
              value: summaryQuery.isError ? 'DEGRADED' : 'OPERATIONAL',
              valueColor: summaryQuery.isError ? 'text-risk-high' : 'text-risk-low',
              dot: summaryQuery.isError ? 'bg-risk-high' : 'bg-risk-low',
            },
          ].map(({ label, icon: Icon, value, valueColor, dot }, i) => (
            <motion.div
              key={label}
              initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={shouldReduceMotion ? {} : { delay: i * 0.05, duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
              className="bg-card px-4 py-3 flex items-center justify-between"
            >
              <div>
                <p className="text-xs font-mono text-muted-foreground tracking-widest">{label}</p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  {dot && <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />}
                  <p className={`text-sm font-mono font-bold tabular-nums ${valueColor}`}>{value}</p>
                </div>
              </div>
              <Icon className="w-4 h-4 text-muted-foreground/30" />
            </motion.div>
          ))}
        </div>

        {/* Actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* RSS Ingest */}
          <motion.div
            initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={shouldReduceMotion ? {} : { delay: 0.1, duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
            className="bg-card border border-border rounded p-4"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Rss className={`w-3.5 h-3.5 ${isCurrentlyIngesting ? 'text-primary animate-pulse' : 'text-muted-foreground'}`} />
                <span className="text-xs font-mono tracking-widest uppercase text-muted-foreground">RSS Ingest</span>
              </div>
              <Button
                size="sm"
                onClick={handleTriggerIngest}
                disabled={isCurrentlyIngesting}
                className="h-7 px-3 text-xs font-mono tracking-wider"
                variant="default"
              >
                {isCurrentlyIngesting ? 'RUNNING…' : 'TRIGGER'}
              </Button>
            </div>

            {isCurrentlyIngesting ? (
              <div className="space-y-2">
                <div className="flex justify-between text-xs font-mono text-muted-foreground">
                  <span className="truncate mr-2">{statusQuery.data?.current_step || 'INITIALISING…'}</span>
                  <span className="tabular-nums">{statusQuery.data?.progress_percent || 0}%</span>
                </div>
                <Progress value={statusQuery.data?.progress_percent || 0} className="h-1" />
                {(statusQuery.data?.total_items ?? 0) > 0 && (
                  <p className="text-xs font-mono text-muted-foreground text-right tabular-nums">
                    {statusQuery.data?.items_processed} / {statusQuery.data?.total_items} items
                  </p>
                )}
              </div>
            ) : statusQuery.data?.error ? (
              <p className="text-xs font-mono text-risk-high bg-risk-high/10 p-2 rounded border border-risk-high/20">
                ERR: {statusQuery.data.error}
              </p>
            ) : (
              <p className="text-xs font-mono text-muted-foreground">
                Fetches live news feeds and enriches events via the backend NLP pipeline.
              </p>
            )}
          </motion.div>

          {/* Refresh */}
          <motion.div
            initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={shouldReduceMotion ? {} : { delay: 0.15, duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
            className="bg-card border border-border rounded p-4"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <RefreshCw className={`w-3.5 h-3.5 ${isUpdating ? 'animate-spin text-primary' : 'text-muted-foreground'}`} />
                <span className="text-xs font-mono tracking-widest uppercase text-muted-foreground">Query Cache</span>
              </div>
              <Button
                size="sm"
                onClick={handleTriggerUpdate}
                disabled={isUpdating}
                variant="outline"
                className="h-7 px-3 text-xs font-mono tracking-wider"
              >
                {isUpdating ? 'REFRESHING…' : 'REFRESH'}
              </Button>
            </div>
            <p className="text-xs font-mono text-muted-foreground">
              Invalidates all TanStack Query caches and re-fetches suppliers, events, and forecasts.
            </p>
          </motion.div>
        </div>

        {/* Supplier table */}
        <motion.div
          initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={shouldReduceMotion ? {} : { delay: 0.2, duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
          className="bg-card border border-border rounded overflow-hidden"
        >
          <div className="px-4 py-2.5 border-b border-border flex items-center justify-between">
            <span className="text-xs font-mono tracking-widest uppercase text-muted-foreground">Supplier Registry</span>
            <Button size="sm" onClick={handleTriggerUpdate} disabled={isUpdating}
              variant="ghost" className="h-6 px-2 text-xs font-mono text-muted-foreground">
              <RefreshCw className={`w-3 h-3 mr-1 ${isUpdating ? 'animate-spin' : ''}`} />
              REFRESH
            </Button>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent border-border">
                  {['Name', 'Country', 'Exposure', 'Level', 'Crit'].map(h => (
                    <TableHead key={h}>
                      <span className="text-xs font-mono tracking-widest uppercase text-muted-foreground">{h}</span>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {suppliersQuery.isLoading &&
                  Array.from({ length: 4 }).map((_, i) => (
                    <TableRow key={`skel-${i}`} className="border-border">
                      {[55, 35, 70, 25, 15].map((w, j) => (
                        <TableCell key={j}>
                          <div className="h-3 bg-secondary/50 rounded animate-pulse" style={{ width: `${w}%` }} />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                {!suppliersQuery.isLoading && suppliers.map(supplier => (
                  <TableRow key={supplier.id} className="border-border hover:bg-secondary/20 transition-colors">
                    <TableCell className="font-medium text-sm">{supplier.name}</TableCell>
                    <TableCell className="text-xs font-mono text-muted-foreground">{supplier.country}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Progress value={supplier.riskScore} className="w-14 h-1" aria-label={`Exposure: ${supplier.riskScore}%`} />
                        <span className="text-xs font-mono tabular-nums">{supplier.riskScore}%</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <RiskBadge level={supplier.riskLevel} size="sm" />
                    </TableCell>
                    <TableCell>
                      <span className="text-xs font-mono tabular-nums">
                        {supplier.criticality}<span className="text-muted-foreground">/5</span>
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
