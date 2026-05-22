import { useMemo, useRef, useEffect, useCallback, useState, type MouseEvent } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { Header } from '@/components/layout/Header';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  Line,
  ReferenceLine,
} from 'recharts';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';

const PX_PER_DAY = 72;
const HISTORY_DAYS = 60;

function isoYesterdayUtc(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ResilienceHistoryPage() {
  const suppliersQuery = useQuery({
    queryKey: ['suppliers'],
    queryFn: () => api.getSuppliers(),
  });

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);
  const [selectedSupplierId, setSelectedSupplierId] = useState<string>('');
  const [snapshotDate, setSnapshotDate] = useState<string>(isoYesterdayUtc);
  const [showOverlay, setShowOverlay] = useState(false);

  const effectiveSupplierId = selectedSupplierId || suppliers[0]?.id || '';
  const selectedSupplier = suppliers.find((s) => s.id === effectiveSupplierId);

  const historyQuery = useQuery({
    queryKey: ['risk-history', effectiveSupplierId],
    queryFn: () => api.getRiskHistory(effectiveSupplierId, HISTORY_DAYS),
    enabled: Boolean(effectiveSupplierId),
  });

  const traceQuery = useQuery({
    queryKey: ['forecast-trace', effectiveSupplierId],
    queryFn: () => api.getForecastTrace(effectiveSupplierId, HISTORY_DAYS),
    enabled: Boolean(effectiveSupplierId),
  });

  const forecastQuery = useQuery({
    queryKey: ['forecast', 'xgboost', effectiveSupplierId],
    queryFn: () => api.getSupplierForecast(effectiveSupplierId),
    enabled: Boolean(effectiveSupplierId),
  });

  const snapshotQuery = useQuery({
    queryKey: ['forecast-snapshot', effectiveSupplierId, snapshotDate],
    queryFn: () => api.getForecastSnapshot(effectiveSupplierId, snapshotDate, true),
    enabled: Boolean(effectiveSupplierId) && showOverlay && Boolean(snapshotDate),
  });

  const todayStr = todayIso();

  const chartData = useMemo(() => {
    // Build a map from the trace: ds → { yhat, yhat_lower, yhat_upper }
    const traceMap: Record<string, { yhat: number; yhat_lower: number; yhat_upper: number }> =
      Object.fromEntries(
        (traceQuery.data ?? []).map((p) => [p.ds, { yhat: p.yhat, yhat_lower: p.yhat_lower, yhat_upper: p.yhat_upper }])
      );

    const histRaw = (historyQuery.data ?? []).map((p) => {
      const trace = traceMap[p.ds] ?? null;
      return {
        ds: p.ds,
        y_actual: p.y_actual,
        yhat: trace ? trace.yhat : null as number | null,
        yhat_lower: trace ? trace.yhat_lower : null as number | null,
        yhat_upper: trace ? trace.yhat_upper : null as number | null,
        snapshot_yhat: null as number | null,
        isForecast: false,
      };
    });

    const forecastRaw = (forecastQuery.data ?? []).map((p) => ({
      ds: typeof p.ds === 'string' ? p.ds : String(p.ds),
      y_actual: null as number | null,
      yhat: p.yhat,
      yhat_lower: p.yhat_lower,
      yhat_upper: p.yhat_upper,
      snapshot_yhat: null as number | null,
      isForecast: true,
    }));

    // Bridge: if the last history point has no trace entry, anchor the purple
    // line to the realized value so both lines meet at Today without a gap.
    const lastHist = histRaw.length > 0 ? histRaw[histRaw.length - 1] : null;
    if (lastHist && lastHist.yhat === null) {
      const anchorValue = lastHist.y_actual ?? 0;
      lastHist.yhat = anchorValue;
      lastHist.yhat_lower = anchorValue;
      lastHist.yhat_upper = anchorValue;
    }

    const snapshotMap: Record<string, number> = Object.fromEntries(
      (snapshotQuery.data?.points ?? []).map((p) => [p.ds, p.yhat])
    );

    const merged = [...histRaw, ...forecastRaw].sort((a, b) => a.ds.localeCompare(b.ds));
    return merged.map((p) => ({ ...p, snapshot_yhat: snapshotMap[p.ds] ?? null }));
  }, [historyQuery.data, traceQuery.data, forecastQuery.data, snapshotQuery.data]);

  const forecastPeak = useMemo(() => {
    const forecastPoints = chartData.filter((p) => p.isForecast && p.yhat !== null);
    if (!forecastPoints.length) return null;
    return forecastPoints.reduce((max, p) => (p.yhat! > max.yhat! ? p : max));
  }, [chartData]);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef({ active: false, startX: 0, scrollLeft: 0 });

  const onMouseDown = useCallback((e: MouseEvent<HTMLDivElement>) => {
    const el = scrollContainerRef.current;
    if (!el) return;
    dragRef.current = { active: true, startX: e.pageX - el.offsetLeft, scrollLeft: el.scrollLeft };
    el.style.cursor = 'grabbing';
    el.style.userSelect = 'none';
  }, []);

  const onMouseMove = useCallback((e: MouseEvent<HTMLDivElement>) => {
    if (!dragRef.current.active) return;
    const el = scrollContainerRef.current;
    if (!el) return;
    const x = e.pageX - el.offsetLeft;
    const walk = (x - dragRef.current.startX) * 1.2;
    el.scrollLeft = dragRef.current.scrollLeft - walk;
  }, []);

  const onMouseUp = useCallback(() => {
    dragRef.current.active = false;
    const el = scrollContainerRef.current;
    if (el) { el.style.cursor = 'grab'; el.style.userSelect = ''; }
  }, []);

  const scrollToToday = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const todayIndex = chartData.findIndex((p) => p.ds === todayStr);
    if (todayIndex < 0) return;
    const targetLeft = todayIndex * PX_PER_DAY - el.clientWidth / 2 + PX_PER_DAY / 2;
    el.scrollLeft = Math.max(0, targetLeft);
  }, [chartData, todayStr]);

  useEffect(() => {
    scrollToToday();
  }, [scrollToToday]);

  const isLoading =
    suppliersQuery.isLoading || historyQuery.isLoading || traceQuery.isLoading || forecastQuery.isLoading;

  const hasError =
    suppliersQuery.isError ||
    forecastQuery.isError ||
    (showOverlay && snapshotQuery.isError);

  const chartWidth = Math.max(chartData.length * PX_PER_DAY, 800);

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      <Header
        title="Forecast"
        subtitle="14-day XGBoost risk forecast — history and future on one timeline"
      />

      <div className="flex-1 p-6 overflow-auto">
        {hasError && (
          <div className="mb-4 rounded-lg border border-risk-high/40 bg-risk-high/10 px-4 py-3 text-sm text-risk-high">
            Could not load forecast data from the backend.
            {showOverlay && snapshotQuery.isError && (
              <span className="block mt-1 text-xs opacity-90">
                For the compare overlay, pick a date with at least two days of historical
                risk_score for this node, or wait for on-demand generation to finish.
              </span>
            )}
          </div>
        )}

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-4 mb-6">
          <span className="text-sm text-muted-foreground">Select Supplier:</span>
          <Select value={effectiveSupplierId} onValueChange={setSelectedSupplierId}>
            <SelectTrigger className="w-64 bg-secondary/50">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {suppliers.map((supplier) => (
                <SelectItem key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button variant="outline" size="sm" onClick={scrollToToday}>
            Today
          </Button>

          <div className="flex items-center gap-2 ml-auto">
            <Button
              type="button"
              variant={showOverlay ? 'secondary' : 'outline'}
              size="sm"
              onClick={() => setShowOverlay((v) => !v)}
            >
              {showOverlay ? 'Hide overlay' : 'Compare snapshot'}
            </Button>
            {showOverlay && (
              <>
                <span className="text-sm text-muted-foreground">Origin:</span>
                <input
                  type="date"
                  className="h-9 rounded-md border border-border bg-secondary/50 px-3 text-sm text-foreground"
                  value={snapshotDate}
                  max={todayStr}
                  onChange={(e) => setSnapshotDate(e.target.value)}
                />
              </>
            )}
          </div>

          {isLoading && (
            <span className="text-sm text-muted-foreground">Loading…</span>
          )}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-xl p-5"
          >
            <p className="text-sm text-muted-foreground">Current exposure (live)</p>
            <p className="text-3xl font-bold text-risk-high mt-1">
              {selectedSupplier?.riskScore}%
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card rounded-xl p-5"
          >
            <p className="text-sm text-muted-foreground">Forecast peak</p>
            {forecastPeak ? (
              <>
                <p className="text-3xl font-bold text-primary mt-1">
                  {forecastPeak.yhat!.toFixed(1)}
                </p>
                <p className="text-xs text-muted-foreground mt-1">{forecastPeak.ds}</p>
              </>
            ) : (
              <p className="text-3xl font-bold text-muted-foreground mt-1">—</p>
            )}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-card rounded-xl p-5"
          >
            <p className="text-sm text-muted-foreground">MAE (snapshot overlay)</p>
            <p className="text-3xl font-bold text-primary mt-1">
              {snapshotQuery.data?.mae != null ? snapshotQuery.data.mae.toFixed(2) : '—'}
            </p>
            {snapshotQuery.data && (
              <p className="text-xs text-muted-foreground mt-1">
                {snapshotQuery.data.completed_days} / {snapshotQuery.data.horizon_days} days
                {snapshotQuery.data.generated_on_demand ? ' · computed on demand' : ''}
              </p>
            )}
          </motion.div>
        </div>

        {/* Chart */}
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-card rounded-xl p-5"
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">
              Risk Timeline — scroll left for history, right for forecast
            </h3>
            {/* Static legend outside the scrollable area */}
            <div className="flex items-center gap-4 text-xs text-muted-foreground shrink-0">
              <span className="flex items-center gap-1.5">
                <span style={{ display: 'inline-block', width: 16, height: 2, background: 'hsl(142, 70%, 45%)', borderRadius: 1 }} />
                Realized avg risk
              </span>
              <span className="flex items-center gap-1.5">
                <span style={{ display: 'inline-block', width: 16, height: 2, background: 'hsl(250, 60%, 60%)', borderRadius: 1 }} />
                Predicted (XGBoost)
              </span>
              {showOverlay && (
                <span className="flex items-center gap-1.5">
                  <span style={{ display: 'inline-block', width: 16, height: 2, background: 'hsl(30, 80%, 55%)', borderRadius: 1, borderTop: '2px dashed hsl(30, 80%, 55%)' }} />
                  Snapshot ({snapshotDate})
                </span>
              )}
            </div>
          </div>

          <div
            ref={scrollContainerRef}
            style={{ overflowX: 'auto', width: '100%', cursor: 'grab' }}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onMouseLeave={onMouseUp}
          >
            <div style={{ width: chartWidth, height: 320 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="hsl(217, 33%, 18%)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="ds"
                    stroke="hsl(215, 20%, 55%)"
                    tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 11 }}
                    tickFormatter={(v) => String(v).slice(5)}
                    tickLine={false}
                    axisLine={false}
                    dy={8}
                    interval={2}
                  />
                  <YAxis
                    stroke="hsl(215, 20%, 55%)"
                    tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 11 }}
                    domain={[0, 'auto']}
                    tickLine={false}
                    axisLine={false}
                    dx={-8}
                    width={40}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(222, 47%, 10%)',
                      border: '1px solid hsl(217, 33%, 18%)',
                      borderRadius: '8px',
                      color: 'hsl(210, 40%, 98%)',
                    }}
                    itemStyle={{ color: 'hsl(210, 40%, 98%)' }}
                    labelStyle={{ color: 'hsl(215, 20%, 65%)', marginBottom: '6px' }}
                    formatter={(value: number | null, name: string) =>
                      value != null ? [value.toFixed(2), name] : [null, name]
                    }
                  />

                  {/* Realized history — green */}
                  <Line
                    type="monotone"
                    dataKey="y_actual"
                    name="Realized avg risk"
                    stroke="hsl(142, 70%, 45%)"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />

                  {/* XGBoost predicted — purple (runs through history AND future) */}
                  <Line
                    type="monotone"
                    dataKey="yhat"
                    name="Predicted (XGBoost)"
                    stroke="hsl(250, 60%, 60%)"
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />

                  {/* Confidence bound lines — dotted */}
                  <Line
                    type="monotone"
                    dataKey="yhat_upper"
                    name="Upper bound"
                    stroke="hsl(250, 60%, 60%)"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                    strokeOpacity={0.5}
                    dot={false}
                    legendType="none"
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="yhat_lower"
                    name="Lower bound"
                    stroke="hsl(250, 60%, 60%)"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                    strokeOpacity={0.5}
                    dot={false}
                    legendType="none"
                    connectNulls={false}
                  />

                  {/* Compare overlay */}
                  {showOverlay && (
                    <Line
                      type="monotone"
                      dataKey="snapshot_yhat"
                      name={`Snapshot (${snapshotDate})`}
                      stroke="hsl(30, 80%, 55%)"
                      strokeWidth={1.5}
                      strokeDasharray="5 3"
                      dot={false}
                      connectNulls
                    />
                  )}

                  {/* Today marker */}
                  <ReferenceLine
                    x={todayStr}
                    stroke="hsl(215, 20%, 55%)"
                    strokeDasharray="3 3"
                    label={{
                      value: 'Today',
                      position: 'insideTopRight',
                      fill: 'hsl(215, 20%, 65%)',
                      fontSize: 11,
                    }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
