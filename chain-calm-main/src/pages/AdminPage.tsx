import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  Database,
  Users,
  Activity,
  CheckCircle,
  AlertCircle,
  Rss,
} from 'lucide-react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';

export default function AdminPage() {
  const [isUpdating, setIsUpdating] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const queryClient = useQueryClient();

  const suppliersQuery = useQuery({
    queryKey: ['suppliers'],
    queryFn: api.getSuppliers,
  });

  const summaryQuery = useQuery({
    queryKey: ['summary'],
    queryFn: api.getSummary,
  });

  const statusQuery = useQuery({
    queryKey: ['rssStatus'],
    queryFn: api.getRssIngestStatus,
    refetchInterval: 1000,
  });

  const isCurrentlyIngesting = isIngesting || (statusQuery.data?.is_running ?? false);

  const [prevRunning, setPrevRunning] = useState(false);
  useEffect(() => {
    const isRunning = statusQuery.data?.is_running ?? false;
    if (prevRunning && !isRunning) {
      // Ingestion just finished
      setIsIngesting(false);
      handleTriggerUpdate();
    }
    setPrevRunning(isRunning);
  }, [statusQuery.data?.is_running, prevRunning]);

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);

  const handleTriggerIngest = async () => {
    setIsIngesting(true);
    try {
      await api.triggerRssIngest();
      // Polling will handle UI state updates
    } catch (e) {
      console.error(e);
      setIsIngesting(false);
    }
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
      <Header
        title="Administration"
        subtitle="System control and management"
      />

      <div className="flex-1 p-6 overflow-auto">
        {(suppliersQuery.isError || summaryQuery.isError) && (
          <div className="mb-4 rounded-lg border border-risk-high/40 bg-risk-high/10 px-4 py-3 text-sm text-risk-high">
            Could not load admin data from the backend API.
          </div>
        )}

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Card className="glass-card border-border hover:border-primary/30 transition-colors cursor-pointer">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Rss className={`w-4 h-4 ${isCurrentlyIngesting ? 'animate-pulse text-primary' : ''}`} />
                  Fetch Live News
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Button
                  size="sm"
                  onClick={handleTriggerIngest}
                  disabled={isCurrentlyIngesting}
                  className="w-full"
                  variant="default"
                >
                  {isCurrentlyIngesting ? 'Ingesting...' : 'Trigger RSS'}
                </Button>
                {isCurrentlyIngesting && (
                  <div className="mt-3 space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span className="truncate mr-2">{statusQuery.data?.current_step || 'Starting...'}</span>
                      <span>{statusQuery.data?.progress_percent || 0}%</span>
                    </div>
                    <Progress value={statusQuery.data?.progress_percent || 0} className="h-1.5" />
                    {(statusQuery.data?.total_items ?? 0) > 0 && (
                      <div className="text-[10px] text-muted-foreground text-right mt-1">
                        {statusQuery.data?.items_processed} / {statusQuery.data?.total_items} processed
                      </div>
                    )}
                  </div>
                )}
                {!isCurrentlyIngesting && statusQuery.data?.error && (
                  <div className="mt-3 text-xs text-risk-high bg-risk-high/10 p-2 rounded">
                    Error: {statusQuery.data.error}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Card className="glass-card border-border hover:border-primary/30 transition-colors cursor-pointer">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <RefreshCw className={`w-4 h-4 ${isUpdating ? 'animate-spin' : ''}`} />
                  Refresh Data
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Button
                  size="sm"
                  onClick={handleTriggerUpdate}
                  disabled={isUpdating}
                  className="w-full"
                >
                  {isUpdating ? 'Refreshing...' : 'Refresh'}
                </Button>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <Card className="glass-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Database className="w-4 h-4" />
                  Database Status
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  {suppliersQuery.isError ? (
                    <>
                      <AlertCircle className="w-4 h-4 text-risk-high" />
                      <span className="text-sm text-muted-foreground">Disconnected</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle className="w-4 h-4 text-risk-low" />
                      <span className="text-sm text-muted-foreground">Connected</span>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Card className="glass-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Users className="w-4 h-4" />
                  Total Suppliers
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{suppliers.length}</p>
              </CardContent>
            </Card>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <Card className="glass-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <Activity className="w-4 h-4" />
                  System Health
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-full animate-pulse ${
                      summaryQuery.isError ? 'bg-risk-high' : 'bg-risk-low'
                    }`}
                  />
                  <span className="text-sm text-muted-foreground">
                    {summaryQuery.isError ? 'Degraded' : 'Operational'}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  {summaryQuery.data?.total_events ?? 0} total events indexed
                </p>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card rounded-xl overflow-hidden"
        >
          <div className="p-4 border-b border-border flex items-center justify-between">
            <h3 className="font-semibold">Supplier Management</h3>
            <Button size="sm" onClick={handleTriggerUpdate} disabled={isUpdating}>
              <RefreshCw className={`w-4 h-4 mr-2 ${isUpdating ? 'animate-spin' : ''}`} />
              {isUpdating ? 'Refreshing...' : 'Refresh Data'}
            </Button>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent border-border">
                <TableHead>Name</TableHead>
                <TableHead>Country</TableHead>
                <TableHead>Risk Score</TableHead>
                <TableHead>Criticality</TableHead>
                <TableHead>Coordinates</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppliers.map((supplier) => (
                <TableRow key={supplier.id} className="border-border">
                  <TableCell className="font-medium">{supplier.name}</TableCell>
                  <TableCell className="text-muted-foreground">{supplier.country}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <span className="text-sm">{supplier.riskScore}%</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm">{supplier.criticality}</span>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {supplier.coordinates[1].toFixed(2)}, {supplier.coordinates[0].toFixed(2)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {suppliersQuery.isLoading && <div className="p-4 text-sm text-muted-foreground">Loading suppliers...</div>}
        </motion.div>
      </div>
    </div>
  );
}
