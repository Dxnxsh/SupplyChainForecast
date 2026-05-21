import { useMemo, useState } from 'react';
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
  Area,
  AreaChart,
  ComposedChart,
  Line,
  Legend,
} from 'recharts';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';

function isoYesterdayUtc(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

type ForecastMode = 'live' | 'compare';

export default function ResilienceHistoryPage() {
  const suppliersQuery = useQuery({
    queryKey: ['suppliers'],
    queryFn: () => api.getSuppliers(),
  });

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);
  const [selectedSupplierId, setSelectedSupplierId] = useState<string>('');
  const [forecastMode, setForecastMode] = useState<ForecastMode>('live');
  const [snapshotDate, setSnapshotDate] = useState<string>(isoYesterdayUtc);

  const effectiveSupplierId = selectedSupplierId || suppliers[0]?.id || '';

  const forecastQuery = useQuery({
    queryKey: ['forecast', 'hybrid', effectiveSupplierId],
    queryFn: () => api.getSupplierForecast(effectiveSupplierId),
    enabled: Boolean(effectiveSupplierId) && forecastMode === 'live',
  });

  const snapshotDatesQuery = useQuery({
    queryKey: ['forecast-snapshot-dates', effectiveSupplierId],
    queryFn: () => api.getForecastSnapshotDates(effectiveSupplierId),
    enabled: Boolean(effectiveSupplierId) && forecastMode === 'compare',
  });

  const snapshotQuery = useQuery({
    queryKey: ['forecast-snapshot', effectiveSupplierId, snapshotDate],
    queryFn: () => api.getForecastSnapshot(effectiveSupplierId, snapshotDate, true),
    enabled: Boolean(effectiveSupplierId) && forecastMode === 'compare' && Boolean(snapshotDate),
  });

  const selectedSupplier = suppliers.find((s) => s.id === effectiveSupplierId);
  const forecastData = forecastQuery.data ?? [];

  const compareChartData = useMemo(() => {
    const pts = snapshotQuery.data?.points ?? [];
    return pts.map((p) => ({
      ds: p.ds,
      predicted: p.yhat,
      actual: p.y_actual,
      lower: p.yhat_lower,
      upper: p.yhat_upper,
    }));
  }, [snapshotQuery.data]);

  const loadingCompare =
    forecastMode === 'compare' &&
    Boolean(effectiveSupplierId) &&
    (snapshotQuery.isLoading || snapshotQuery.isFetching);

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      <Header
        title="Forecast"
        subtitle={
          forecastMode === 'live'
            ? 'Hybrid supplier risk forecast (latest pipeline output)'
            : 'XGBoost snapshot vs realized daily risk (UTC)'
        }
      />

      <div className="flex-1 p-6 overflow-auto">
        {(suppliersQuery.isError ||
          (forecastMode === 'live' && forecastQuery.isError) ||
          (forecastMode === 'compare' && snapshotQuery.isError)) && (
          <div className="mb-4 rounded-lg border border-risk-high/40 bg-risk-high/10 px-4 py-3 text-sm text-risk-high">
            Could not load forecast data from the backend.
            {forecastMode === 'compare' && snapshotQuery.isError && (
              <span className="block mt-1 text-xs opacity-90">
                For compare mode, pick a date with at least two days of historical risk_score for this
                node, or wait for on-demand generation to finish.
              </span>
            )}
          </div>
        )}

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

          <div className="flex rounded-lg border border-border overflow-hidden">
            <Button
              type="button"
              variant={forecastMode === 'live' ? 'secondary' : 'ghost'}
              size="sm"
              className="rounded-none"
              onClick={() => setForecastMode('live')}
            >
              Live (hybrid)
            </Button>
            <Button
              type="button"
              variant={forecastMode === 'compare' ? 'secondary' : 'ghost'}
              size="sm"
              className="rounded-none border-l border-border"
              onClick={() => setForecastMode('compare')}
            >
              Compare snapshot
            </Button>
          </div>

          {forecastMode === 'compare' && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Forecast origin:</span>
              <input
                type="date"
                className="h-9 rounded-md border border-border bg-secondary/50 px-3 text-sm text-foreground"
                value={snapshotDate}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setSnapshotDate(e.target.value)}
              />
              {snapshotDatesQuery.data?.dates?.length ? (
                <span className="text-xs text-muted-foreground max-w-[200px] truncate" title={snapshotDatesQuery.data.dates.join(', ')}>
                  Stored: {snapshotDatesQuery.data.dates.length} day(s)
                </span>
              ) : null}
            </div>
          )}

          {(suppliersQuery.isLoading ||
            (forecastMode === 'live' && forecastQuery.isLoading) ||
            loadingCompare) && (
            <span className="text-sm text-muted-foreground">Loading…</span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-xl p-5"
          >
            <p className="text-sm text-muted-foreground">Current exposure (live)</p>
            <p className="text-3xl font-bold text-risk-high mt-1">{selectedSupplier?.riskScore}%</p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card rounded-xl p-5"
          >
            <p className="text-sm text-muted-foreground">Criticality</p>
            <p className="text-3xl font-bold text-risk-low mt-1">{selectedSupplier?.criticality}</p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-card rounded-xl p-5"
          >
            {forecastMode === 'live' ? (
              <>
                <p className="text-sm text-muted-foreground">Forecast points</p>
                <p className="text-3xl font-bold text-primary mt-1">{forecastData.length}</p>
              </>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">MAE (completed days)</p>
                <p className="text-3xl font-bold text-primary mt-1">
                  {snapshotQuery.data?.mae != null ? snapshotQuery.data.mae.toFixed(2) : '—'}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {snapshotQuery.data?.completed_days ?? 0} / {snapshotQuery.data?.horizon_days ?? 14} days
                  {snapshotQuery.data?.generated_on_demand ? ' · computed on demand' : ''}
                </p>
              </>
            )}
          </motion.div>
        </div>

        <div className="grid grid-cols-1 gap-6">
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass-card rounded-xl p-5"
          >
            <h3 className="text-lg font-semibold text-foreground mb-4">
              {forecastMode === 'live' ? '14-Day Hybrid Forecast' : 'Snapshot vs actual (daily sum of risk_score)'}
            </h3>
            <div className="h-80">
              {forecastMode === 'live' ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={forecastData}>
                    <defs>
                      <linearGradient id="histGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(250, 60%, 60%)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="hsl(250, 60%, 60%)" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="newsGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(0, 84%, 60%)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="hsl(0, 84%, 60%)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 33%, 18%)" vertical={false} />
                    <XAxis
                      dataKey="ds"
                      stroke="hsl(215, 20%, 55%)"
                      tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 12 }}
                      tickFormatter={(value) => String(value).slice(5)}
                      tickLine={false}
                      axisLine={false}
                      dy={10}
                    />
                    <YAxis
                      stroke="hsl(215, 20%, 55%)"
                      tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 12 }}
                      domain={[0, 100]}
                      tickLine={false}
                      axisLine={false}
                      dx={-10}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'hsl(222, 47%, 10%)',
                        border: '1px solid hsl(217, 33%, 18%)',
                        borderRadius: '8px',
                        color: 'hsl(210, 40%, 98%)',
                      }}
                      itemStyle={{ color: 'hsl(210, 40%, 98%)' }}
                      labelStyle={{ color: 'hsl(215, 20%, 65%)', marginBottom: '8px' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="historical_contribution"
                      name="Historical trend"
                      stackId="1"
                      stroke="hsl(250, 60%, 60%)"
                      fill="url(#histGradient)"
                      strokeWidth={2}
                    />
                    <Area
                      type="monotone"
                      dataKey="news_contribution"
                      name="Predictive news"
                      stackId="1"
                      stroke="hsl(0, 84%, 60%)"
                      fill="url(#newsGradient)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={compareChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 33%, 18%)" vertical={false} />
                    <XAxis
                      dataKey="ds"
                      stroke="hsl(215, 20%, 55%)"
                      tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 12 }}
                      tickFormatter={(value) => String(value).slice(5)}
                      tickLine={false}
                      axisLine={false}
                      dy={10}
                    />
                    <YAxis
                      stroke="hsl(215, 20%, 55%)"
                      tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 12 }}
                      domain={[0, 'auto']}
                      tickLine={false}
                      axisLine={false}
                      dx={-10}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'hsl(222, 47%, 10%)',
                        border: '1px solid hsl(217, 33%, 18%)',
                        borderRadius: '8px',
                        color: 'hsl(210, 40%, 98%)',
                      }}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="lower"
                      name="Predicted lower"
                      stroke="hsl(250, 60%, 40%)"
                      strokeWidth={1}
                      strokeDasharray="4 4"
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="upper"
                      name="Predicted upper"
                      stroke="hsl(250, 60%, 40%)"
                      strokeWidth={1}
                      strokeDasharray="4 4"
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="predicted"
                      name="Predicted (XGBoost snapshot)"
                      stroke="hsl(250, 60%, 60%)"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="actual"
                      name="Realized Σ risk_score"
                      stroke="hsl(142, 70%, 45%)"
                      strokeWidth={2}
                      connectNulls
                      dot={{ r: 3 }}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              )}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
