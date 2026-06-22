import { useMemo, useRef, useEffect, useCallback, useState, type MouseEvent } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
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
  Area,
  ReferenceLine,
  ReferenceArea,
} from 'recharts';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';

const PX_PER_DAY = 72;
const HISTORY_DAYS = 60;

function isoYesterdayUtc(): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function todayIso(): string {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

const RISK_GREEN = 'hsl(152, 72%, 42%)';
const FORECAST_BLUE = 'hsl(200, 85%, 55%)';
const SNAPSHOT_AMBER = 'hsl(38, 85%, 52%)';
const RISK_RED = 'hsl(0, 75%, 50%)';
const BAND_LOW_MAX = 1.5;
const BAND_MED_MAX = 2.2;

export default function ResilienceHistoryPage() {
  const shouldReduceMotion = useReducedMotion();
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

      <div className="flex-1 p-5 overflow-auto">
        {hasError && (
          <div className="mb-4 rounded border border-risk-high/30 bg-risk-high/8 px-3 py-2 text-xs font-mono text-risk-high">
            BACKEND UNREACHABLE — forecast data unavailable
            {showOverlay && snapshotQuery.isError && (
              <span className="block mt-1 opacity-80">
                SNAPSHOT: pick a date with ≥2 historical days for this node
              </span>
            )}
          </div>
        )}

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-3 mb-5">
          <label className="text-xs font-mono text-muted-foreground tracking-widest uppercase whitespace-nowrap">Node</label>
          <Select value={effectiveSupplierId} onValueChange={setSelectedSupplierId}>
            <SelectTrigger className="h-7 w-56 bg-secondary/50 text-xs font-mono border-border" aria-label="Select supplier">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {suppliers.map((supplier) => (
                <SelectItem key={supplier.id} value={supplier.id} className="text-xs font-mono">
                  {supplier.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button variant="outline" size="sm" onClick={scrollToToday}
            className="h-7 px-3 text-xs font-mono tracking-wider">
            TODAY
          </Button>

          <div className="flex items-center gap-2 ml-auto">
            <Button
              type="button"
              variant={showOverlay ? 'secondary' : 'outline'}
              size="sm"
              onClick={() => setShowOverlay((v) => !v)}
              className="h-7 px-3 text-xs font-mono tracking-wider"
            >
              {showOverlay ? 'HIDE OVERLAY' : 'COMPARE'}
            </Button>
            {showOverlay && (
              <>
                <label className="text-xs font-mono text-muted-foreground tracking-widest">ORIGIN</label>
                <input
                  type="date"
                  aria-label="Snapshot origin date"
                  className="h-7 rounded border border-border bg-secondary/50 px-2 text-xs font-mono text-foreground"
                  value={snapshotDate}
                  max={todayStr}
                  onChange={(e) => setSnapshotDate(e.target.value)}
                />
              </>
            )}
          </div>

          {isLoading && (
            <span className="text-xs font-mono text-muted-foreground animate-pulse">LOADING…</span>
          )}
        </div>

        {/* Stats — horizontal strip matching the map page */}
        <div className="grid grid-cols-3 gap-px bg-border rounded overflow-hidden mb-5">
          {[
            {
              label: 'EXPOSURE · LIVE',
              value: selectedSupplier?.riskScore != null ? `${selectedSupplier.riskScore}%` : '—',
              color: 'text-risk-high',
              delay: 0,
            },
            {
              label: 'FORECAST PEAK',
              value: forecastPeak ? forecastPeak.yhat!.toFixed(1) : '—',
              sub: forecastPeak?.ds,
              color: 'text-primary',
              delay: 0.05,
            },
            {
              label: 'MAE · SNAPSHOT',
              value: snapshotQuery.data?.mae != null ? snapshotQuery.data.mae.toFixed(2) : '—',
              sub: snapshotQuery.data
                ? `${snapshotQuery.data.completed_days}/${snapshotQuery.data.horizon_days} days${snapshotQuery.data.generated_on_demand ? ' · on demand' : ''}`
                : undefined,
              color: 'text-primary',
              delay: 0.1,
            },
          ].map(({ label, value, sub, color, delay }) => (
            <motion.div
              key={label}
              initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={shouldReduceMotion ? {} : { delay, duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
              className="bg-card px-4 py-3"
            >
              <p className="text-xs font-mono text-muted-foreground tracking-widest">{label}</p>
              <p className={`text-4xl font-bold font-mono tabular-nums leading-none mt-1 ${color}`}>{value}</p>
              {sub && <p className="text-xs font-mono text-muted-foreground mt-1.5">{sub}</p>}
            </motion.div>
          ))}
        </div>

        {/* Chart */}
        <motion.div
          initial={shouldReduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
          className="bg-card border border-border rounded p-4"
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono text-muted-foreground tracking-widest uppercase">
              Risk Timeline — drag to scroll
            </span>
            <div className="flex items-center gap-4 shrink-0">
              {[
                { color: RISK_GREEN, label: 'REALIZED' },
                { color: FORECAST_BLUE, label: 'XGBOOST' },
                ...(showOverlay ? [{ color: SNAPSHOT_AMBER, label: `SNAP ${snapshotDate}` }] : []),
              ].map(({ color, label }) => (
                <span key={label} className="flex items-center gap-1.5">
                  <span style={{ display: 'inline-block', width: 12, height: 2, background: color, borderRadius: 1 }} />
                  <span className="text-xs font-mono text-muted-foreground tracking-wider">{label}</span>
                </span>
              ))}
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
                    strokeDasharray="2 4"
                    stroke="hsl(240, 5%, 15%)"
                    vertical={false}
                  />
                  {/* Risk zone bands — low / medium / high calibrated to yhat range */}
                  <ReferenceArea y1={0} y2={BAND_LOW_MAX} fill={RISK_GREEN} fillOpacity={0.05} />
                  <ReferenceArea y1={BAND_LOW_MAX} y2={BAND_MED_MAX} fill={SNAPSHOT_AMBER} fillOpacity={0.05} />
                  <ReferenceArea y1={BAND_MED_MAX} fill={RISK_RED} fillOpacity={0.05} />
                  <XAxis
                    dataKey="ds"
                    stroke="hsl(240, 5%, 28%)"
                    tick={{ fill: 'hsl(240, 5%, 40%)', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                    tickFormatter={(v) => {
                      const d = new Date(String(v));
                      return isNaN(d.getTime()) ? String(v) : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                    }}
                    tickLine={false}
                    axisLine={false}
                    dy={8}
                    interval={2}
                  />
                  <YAxis
                    stroke="hsl(240, 5%, 28%)"
                    tick={{ fill: 'hsl(240, 5%, 40%)', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
                    domain={[0, 'auto']}
                    tickLine={false}
                    axisLine={false}
                    dx={-8}
                    width={36}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(240, 7%, 8%)',
                      border: '1px solid hsl(240, 5%, 18%)',
                      borderRadius: '3px',
                      color: 'hsl(40, 20%, 92%)',
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '11px',
                    }}
                    itemStyle={{ color: 'hsl(40, 20%, 92%)' }}
                    labelStyle={{ color: 'hsl(240, 5%, 50%)', marginBottom: '4px', fontSize: '10px' }}
                    formatter={(value: number | null, name: string) =>
                      value != null ? [value.toFixed(2), name] : [null, name]
                    }
                  />

                  {/* Confidence interval — filled band behind the lines */}
                  <Area
                    type="monotone"
                    dataKey="yhat_upper"
                    stroke="none"
                    fill={FORECAST_BLUE}
                    fillOpacity={0.08}
                    legendType="none"
                    connectNulls={false}
                    activeDot={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="yhat_lower"
                    stroke="none"
                    fill={FORECAST_BLUE}
                    fillOpacity={0}
                    legendType="none"
                    connectNulls={false}
                    activeDot={false}
                  />

                  {/* Realized history */}
                  <Line
                    type="monotone"
                    dataKey="y_actual"
                    name="Realized avg risk"
                    stroke={RISK_GREEN}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />

                  {/* XGBoost predicted — primary blue */}
                  <Line
                    type="monotone"
                    dataKey="yhat"
                    name="Predicted (XGBoost)"
                    stroke={FORECAST_BLUE}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />

                  {/* Compare overlay */}
                  {showOverlay && (
                    <Line
                      type="monotone"
                      dataKey="snapshot_yhat"
                      name={`Snapshot (${snapshotDate})`}
                      stroke={SNAPSHOT_AMBER}
                      strokeWidth={1.5}
                      strokeDasharray="5 3"
                      dot={false}
                      connectNulls
                    />
                  )}

                  {/* Today marker */}
                  <ReferenceLine
                    x={todayStr}
                    stroke="hsl(240, 5%, 35%)"
                    strokeDasharray="2 4"
                    label={{
                      value: 'TODAY',
                      position: 'insideTopRight',
                      fill: 'hsl(240, 5%, 45%)',
                      fontSize: 9,
                      fontFamily: 'JetBrains Mono, monospace',
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
