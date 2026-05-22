import { useState, useMemo, useEffect } from 'react';
import { motion } from 'framer-motion';
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
        title="World Map Dashboard"
        subtitle={
          rewindDate
            ? `Rewind: data as of ${rewindDate} (UTC calendar day)`
            : 'Global supply chain monitoring (live)'
        }
      />

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 flex flex-col p-6 overflow-auto">
          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <StatsCard
              title="Total Suppliers"
              value={stats.totalSuppliers}
              subtitle="Across 8 countries"
              icon={Building2}
            />
            <StatsCard
              title="High Risk"
              value={stats.highRisk}
              subtitle="Require attention"
              icon={AlertTriangle}
              variant="risk-high"
            />
            <StatsCard
              title="Avg. Risk"
              value={`${stats.avgRisk}%`}
              icon={Shield}
              subtitle={`${stats.countries} countries tracked`}
            />
            <StatsCard
              title="Active Alerts"
              value={stats.activeAlerts}
              subtitle="Forecasted disruptions"
              icon={Globe}
              variant="risk-medium"
            />
          </div>

          {hasError && (
            <div className="mb-4 rounded-lg border border-risk-high/40 bg-risk-high/10 px-4 py-3 text-sm text-risk-high">
              Could not load some dashboard data from the backend. Check that the API is running.
            </div>
          )}

          {/* Filter Bar */}
          <div className="flex flex-wrap items-center gap-4 mb-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground whitespace-nowrap">As of (UTC):</span>
              <input
                type="date"
                className="h-9 rounded-md border border-border bg-secondary/50 px-3 text-sm text-foreground"
                value={rewindDate}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setRewindDate(e.target.value)}
              />
              <Button
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => setRewindDate('')}
              >
                Live
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Filter by product:</span>
            </div>
            <Select value={filterProduct} onValueChange={setFilterProduct}>
              <SelectTrigger className="w-48 bg-secondary/50">
                <SelectValue placeholder="Product" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Products</SelectItem>
                {products.map((product) => (
                  <SelectItem key={product} value={product}>
                    {product}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" type="button" onClick={() => setFilterProduct('all')}>
              Clear product
            </Button>

            {suppliersQuery.isLoading && (
              <span className="text-sm text-muted-foreground">Loading suppliers...</span>
            )}
          </div>

          {/* World Map */}
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex-1 min-h-[500px] glass-card rounded-xl overflow-hidden"
          >
            <WorldMap
              suppliers={filteredSuppliers}
              onSupplierClick={(s) => {
                if (s) {
                  setSearchParams(prev => {
                    const next = new URLSearchParams(prev);
                    next.set('s', s.id);
                    return next;
                  });
                }
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
            setSearchParams(prev => {
              const next = new URLSearchParams(prev);
              next.delete('s');
              return next;
            });
          }}
        />
      </div>
    </div>
  );
}
