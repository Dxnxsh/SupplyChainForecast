import { useState } from 'react';
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
import { XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';

export default function ResilienceHistoryPage() {
  const suppliersQuery = useQuery({
    queryKey: ['suppliers'],
    queryFn: api.getSuppliers,
  });

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);
  const [selectedSupplierId, setSelectedSupplierId] = useState<string>('');

  const effectiveSupplierId = selectedSupplierId || suppliers[0]?.id || '';

  const forecastQuery = useQuery({
    queryKey: ['forecast', effectiveSupplierId],
    queryFn: () => api.getSupplierForecast(effectiveSupplierId),
    enabled: Boolean(effectiveSupplierId),
  });

  const selectedSupplier = suppliers.find((s) => s.id === effectiveSupplierId);
  const forecastData = forecastQuery.data ?? [];

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      <Header
        title="Forecast"
        subtitle="Backend-generated supplier risk forecast"
      />

      <div className="flex-1 p-6 overflow-auto">
        {(suppliersQuery.isError || forecastQuery.isError) && (
          <div className="mb-4 rounded-lg border border-risk-high/40 bg-risk-high/10 px-4 py-3 text-sm text-risk-high">
            Could not load supplier forecast from the backend.
          </div>
        )}

        {/* Supplier Selector */}
        <div className="flex items-center gap-4 mb-6">
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
          {(suppliersQuery.isLoading || forecastQuery.isLoading) && (
            <span className="text-sm text-muted-foreground">Loading data...</span>
          )}
        </div>

        {/* Current Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-card rounded-xl p-5"
          >
            <p className="text-sm text-muted-foreground">Current Risk Score</p>
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
            <p className="text-sm text-muted-foreground">Criticality</p>
            <p className="text-3xl font-bold text-risk-low mt-1">
              {selectedSupplier?.criticality}
            </p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="glass-card rounded-xl p-5"
          >
            <p className="text-sm text-muted-foreground">Forecast Points</p>
            <p className="text-3xl font-bold text-primary mt-1">{forecastData.length}</p>
          </motion.div>
        </div>

        {/* Forecast Chart */}
        <div className="grid grid-cols-1 gap-6">
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            className="glass-card rounded-xl p-5"
          >
            <h3 className="text-lg font-semibold text-foreground mb-4">14-Day Forecast</h3>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={forecastData}>
                  <defs>
                    <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(0, 84%, 60%)" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="hsl(0, 84%, 60%)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 33%, 18%)" />
                  <XAxis
                    dataKey="ds"
                    stroke="hsl(215, 20%, 55%)"
                    tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 12 }}
                    tickFormatter={(value) => value.slice(5)}
                  />
                  <YAxis
                    stroke="hsl(215, 20%, 55%)"
                    tick={{ fill: 'hsl(215, 20%, 55%)', fontSize: 12 }}
                    domain={[0, 100]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(222, 47%, 10%)',
                      border: '1px solid hsl(217, 33%, 18%)',
                      borderRadius: '8px',
                    }}
                    labelStyle={{ color: 'hsl(210, 40%, 98%)' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="yhat"
                    stroke="hsl(0, 84%, 60%)"
                    fill="url(#forecastGradient)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
