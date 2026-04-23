import { useState } from 'react';
import { motion } from 'framer-motion';
import { Globe, Building2, AlertTriangle, Shield, Filter } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
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

export default function WorldMapDashboard() {
  const [selectedSupplier, setSelectedSupplier] = useState<Supplier | null>(null);
  const [filterCountry, setFilterCountry] = useState<string>('all');

  const suppliersQuery = useQuery({
    queryKey: ['suppliers'],
    queryFn: api.getSuppliers,
  });

  const summaryQuery = useQuery({
    queryKey: ['summary'],
    queryFn: api.getSummary,
  });

  const forecastedEventsQuery = useQuery({
    queryKey: ['events', 'forecasted', 200],
    queryFn: () => api.getForecastedEvents(200),
  });

  const supplierEventsQuery = useQuery({
    queryKey: ['events', selectedSupplier?.id],
    queryFn: () => api.getEventsByNode(selectedSupplier!.id, 20),
    enabled: Boolean(selectedSupplier?.id),
  });

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);

  const filteredSuppliers =
    filterCountry === 'all'
      ? suppliers
      : suppliers.filter((s) => s.country === filterCountry);

  const countries = [...new Set(suppliers.map((s) => s.country))].sort();

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
        subtitle="Global supply chain monitoring"
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
          <div className="flex items-center gap-4 mb-4">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">Filter by country:</span>
            </div>
            <Select value={filterCountry} onValueChange={setFilterCountry}>
              <SelectTrigger className="w-48 bg-secondary/50">
                <SelectValue placeholder="Country" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Countries</SelectItem>
                {countries.map((country) => (
                  <SelectItem key={country} value={country}>
                    {country}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm">
              Clear Filters
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
              onSupplierClick={setSelectedSupplier}
              selectedSupplier={selectedSupplier}
            />
          </motion.div>
        </div>

        {/* Supplier Detail Panel */}
        <SupplierDetailPanel
          supplier={selectedSupplier}
          events={supplierDisruptions}
          isLoading={supplierEventsQuery.isLoading}
          onClose={() => setSelectedSupplier(null)}
        />
      </div>
    </div>
  );
}
