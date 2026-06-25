import { useState, useMemo, useEffect } from 'react';
import { motion, useReducedMotion } from 'framer-motion';

import { Globe, Building2, AlertTriangle, Shield, Filter } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams, useLocation, useNavigate } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { StatsCard } from '@/components/dashboard/StatsCard';
import { WorldMap } from '@/components/dashboard/WorldMap';
import { SupplierDetailPanel } from '@/components/dashboard/SupplierDetailPanel';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Supplier } from '@/types/supplier';
import { api } from '@/lib/api';
import { mapDisruptionEvent, mapSupplier } from '@/lib/dataMappers';
import { PRODUCT_EDGES } from '@/lib/productEdges';

export default function WorldMapDashboard() {
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);
  const [filterProduct, setFilterProduct] = useState<string>('all');
  /** YYYY-MM-DD UTC calendar day, or '' for live data */
  const [rewindDate, setRewindDate] = useState<string>('');
  const shouldReduceMotion = useReducedMotion();

  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const searchQuery = searchParams.get('q') || '';
  const selectedId = searchParams.get('s');

  const asOf = rewindDate || undefined;

  const suppliersQuery = useQuery({
    queryKey: ['suppliers', rewindDate],
    queryFn: () => api.getSuppliers(asOf),
  });

  const summaryQuery = useQuery({
    queryKey: ['summary', rewindDate],
    queryFn: () => api.getSummary(asOf),
  });

  const forecastedEventsQuery = useQuery({
    queryKey: ['events', 'forecasted', 200, rewindDate],
    queryFn: () => api.getForecastedEvents(200, asOf),
  });

  const supplierEventsQuery = useQuery({
    queryKey: ['events', selectedSupplier?.id, rewindDate],
    queryFn: () => api.getEventsByNode(selectedSupplier!.id, 20, asOf),
    enabled: Boolean(selectedSupplier?.id),
  });

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);

  // Handle cross-page selection and URL sync
  useEffect(() => {
    if (suppliers.length > 0) {
      if (selectedId) {
        const supplier = suppliers.find(s => s.id === selectedId);
        if (supplier) setSelectedSupplier(supplier);
      } else if (location.state?.selectedSupplierId) {
        const supplier = suppliers.find(s => s.id === location.state.selectedSupplierId || s.name === location.state.selectedSupplierId);
        if (supplier) {
          setSelectedSupplier(supplier);
          setSearchParams(prev => {
            const next = new URLSearchParams(prev);
            next.set('s', supplier.id);
            return next;
          });
          navigate('.', { replace: true, state: {} });
        }
      } else {
        setSelectedSupplier(null);
      }
    }
  }, [selectedId, location.state, suppliers, navigate, setSearchParams]);

  // Compute ColoredEdges with risk coloring and deduplication
  const coloredEdges = useMemo(() => {
    const suppliersMap = new Map(suppliers.map(s => [s.id, s]));
    const allEdges: any[] = [];
    const activeEdgePairs = new Set<string>();

    if (filterProduct !== 'all' && PRODUCT_EDGES[filterProduct]) {
      PRODUCT_EDGES[filterProduct].forEach(([fromId, toId]) => {
        activeEdgePairs.add(`${fromId}-${toId}`);
      });
    }

    // Deduplicate union of all product edges
    const seenEdges = new Set<string>();
    Object.values(PRODUCT_EDGES).forEach(edges => {
      edges.forEach(([fromId, toId]) => {
        const edgeKey = `${fromId}-${toId}`;
        if (!seenEdges.has(edgeKey)) {
          seenEdges.add(edgeKey);
          const fromNode = suppliersMap.get(fromId);
          const toNode = suppliersMap.get(toId);
          if (fromNode && toNode) {
            allEdges.push({
              from: fromNode.coordinates,
              to: toNode.coordinates,
              fromId,
              toId,
              sourceRiskLevel: fromNode.riskLevel,
              isPulsing: fromNode.riskScore >= 69,
              isActive: activeEdgePairs.has(edgeKey) || filterProduct === 'all'
            });
          }
        }
      });
    });

    return allEdges;
  }, [suppliers, filterProduct]);

  const filteredSuppliers = suppliers.filter((s) => {
    const matchProduct = filterProduct === 'all' || (s.products && s.products.includes(filterProduct));
    return matchProduct;
  });

  const countries = [...new Set(suppliers.map((s) => s.country))].sort();
  
  // Extract unique products from all suppliers
  const products = [...new Set(suppliers.flatMap((s) => s.products || []))].sort();

  const summaryAvgRisk = Math.round(summaryQuery.data?.avg_risk_score ?? 0);
  const highRiskSuppliers = suppliers.filter(
    (s) => s.riskLevel === 'high' || s.riskLevel === 'critical'
  ).length;

  const stats = {
    totalSuppliers: suppliers.length,
    highRisk: highRiskSuppliers,
    countries: countries.length,
    activeAlerts: forecastedEventsQuery.data?.length ?? 0,
    avgRisk: summaryAvgRisk,
  };

  const supplierDisruptions = (supplierEventsQuery.data ?? []).map(mapDisruptionEvent);

  const hasError = suppliersQuery.isError || summaryQuery.isError || forecastedEventsQuery.isError;

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      <Header
        title="World Map"
        subtitle={rewindDate ? `AS-OF ${rewindDate}` : 'LIVE · Global monitoring'}
      />

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* Stats strip — horizontal, compact, above the map */}
          <div className="flex gap-px border-b border-border bg-border shrink-0">
            {[
              { label: 'SUPPLIERS', value: stats.totalSuppliers, variant: 'default' as const, icon: Building2 },
              { label: 'HIGH RISK', value: stats.highRisk, variant: 'risk-high' as const, icon: AlertTriangle },
              { label: 'AVG RISK', value: `${stats.avgRisk}%`, variant: 'default' as const, icon: Shield },
              { label: 'ALERTS', value: stats.activeAlerts, variant: 'risk-medium' as const, icon: Globe },
            ].map(({ label, value, variant, icon: Icon }) => (
              <div
                key={label}
                className={`flex-1 flex items-center justify-between px-4 py-2.5 bg-card ${
                  variant === 'risk-high' ? 'border-t-2 border-risk-high/60' :
                  variant === 'risk-medium' ? 'border-t-2 border-risk-medium/40' :
                  'border-t-2 border-transparent'
                }`}
              >
                <div>
                  <p className="text-xs font-mono text-muted-foreground tracking-widest">{label}</p>
                  <p className={`text-2xl font-bold font-mono tabular-nums leading-none mt-0.5 ${
                    variant === 'risk-high' ? 'text-risk-high' :
                    variant === 'risk-medium' ? 'text-risk-medium' :
                    'text-foreground'
                  }`}>{value}</p>
                </div>
                <Icon className="w-4 h-4 text-muted-foreground/40" />
              </div>
            ))}
          </div>

          {hasError && (
            <div className="mx-4 mt-3 rounded border border-risk-high/30 bg-risk-high/8 px-3 py-2 text-xs font-mono text-risk-high">
              BACKEND UNREACHABLE — check that the API server is running on port 8000
            </div>
          )}

          {/* Filter bar */}
          <div className="flex flex-wrap items-center gap-3 px-4 py-2.5 border-b border-border bg-card/40 shrink-0">
            <div className="flex items-center gap-2">
              <label className="text-xs font-mono text-muted-foreground tracking-widest uppercase whitespace-nowrap">
                As of
              </label>
              <input
                type="date"
                aria-label="As of date (UTC)"
                className="h-7 rounded border border-border bg-secondary/50 px-2 text-xs font-mono text-foreground"
                value={rewindDate}
                max={(() => {
                  const d = new Date();
                  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
                })()}
                onChange={e => setRewindDate(e.target.value)}
              />
              {rewindDate && (
                <button
                  onClick={() => setRewindDate('')}
                  className="text-xs font-mono text-primary hover:underline"
                >
                  LIVE
                </button>
              )}
            </div>

            <div className="w-px h-4 bg-border" />

            <div className="flex items-center gap-2">
              <Filter className="w-3 h-3 text-muted-foreground" />
              <Select value={filterProduct} onValueChange={setFilterProduct}>
                <SelectTrigger className="h-7 w-40 bg-secondary/50 text-xs font-mono border-border">
                  <SelectValue placeholder="All Products" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" className="text-xs font-mono">All Products</SelectItem>
                  {products.map(p => (
                    <SelectItem key={p} value={p} className="text-xs font-mono">{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {filterProduct !== 'all' && (
                <button
                  onClick={() => setFilterProduct('all')}
                  className="text-xs font-mono text-muted-foreground hover:text-foreground"
                >
                  CLEAR
                </button>
              )}
            </div>

            {suppliersQuery.isLoading && (
              <span className="text-xs font-mono text-muted-foreground ml-auto animate-pulse">LOADING…</span>
            )}
          </div>

          {/* Map — fills all remaining space */}
          <motion.div
            initial={shouldReduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3, ease: [0.25, 1, 0.5, 1] }}
            className="flex-1 bg-card overflow-hidden"
          >
            <WorldMap
              suppliers={filteredSuppliers}
              onSupplierClick={s => {
                if (s) setSearchParams(prev => { const n = new URLSearchParams(prev); n.set('s', s.id); return n; });
              }}
              selectedSupplier={selectedSupplier}
              coloredEdges={coloredEdges}
              isFilterActive={filterProduct !== 'all'}
              searchQuery={searchQuery}
            />
          </motion.div>
        </div>

        {/* Supplier Detail Panel */}
        <SupplierDetailPanel
          supplier={selectedSupplier}
          events={supplierDisruptions}
          isLoading={supplierEventsQuery.isLoading}
          onClose={() => {
            setSelectedSupplier(null);
            setSearchParams(prev => { const n = new URLSearchParams(prev); n.delete('s'); return n; });
          }}
        />
      </div>
    </div>
  );
}
