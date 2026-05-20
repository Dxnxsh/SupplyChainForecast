import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Filter, ArrowUpDown } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import { api } from '@/lib/api';
import { mapSupplier } from '@/lib/dataMappers';

export default function SuppliersPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const searchQuery = searchParams.get('q') || '';
  
  const [sortField, setSortField] = useState<'name' | 'riskScore' | 'criticality'>('riskScore');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');

  const suppliersQuery = useQuery({
    queryKey: ['suppliers'],
    queryFn: api.getSuppliers,
  });

  const suppliers = (suppliersQuery.data ?? []).map(mapSupplier);

  const filteredAndSortedSuppliers = useMemo(() => {
    return suppliers
      .filter(
        (s) =>
          s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          s.country.toLowerCase().includes(searchQuery.toLowerCase())
      )
      .sort((a, b) => {
        const aVal = a[sortField];
        const bVal = b[sortField];
        if (typeof aVal === 'string' && typeof bVal === 'string') {
          return sortDirection === 'asc'
            ? aVal.localeCompare(bVal)
            : bVal.localeCompare(aVal);
        }
        return sortDirection === 'asc'
          ? (aVal as number) - (bVal as number)
          : (bVal as number) - (aVal as number);
      });
  }, [searchQuery, sortField, sortDirection, suppliers]);

  const handleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const handleRowClick = (supplierId: string) => {
    navigate('/', { state: { selectedSupplierId: supplierId } });
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      <Header title="Suppliers" subtitle="Manage and monitor all suppliers" />

      <div className="flex-1 p-6 overflow-auto">
        {suppliersQuery.isError && (
          <div className="mb-4 rounded-lg border border-risk-high/40 bg-risk-high/10 px-4 py-3 text-sm text-risk-high">
            Could not load suppliers from the backend API.
          </div>
        )}

        {/* Filter Bar */}
        <div className="flex items-center gap-4 mb-6">
          <Button variant="outline" size="sm">
            <Filter className="w-4 h-4 mr-2" />
            Filters
          </Button>
          {suppliersQuery.isLoading && (
            <span className="text-sm text-muted-foreground">Loading suppliers...</span>
          )}
          {searchQuery && (
            <span className="text-sm text-muted-foreground italic">
              Filtering by: "{searchQuery}"
            </span>
          )}
        </div>

        {/* Suppliers Table */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card rounded-xl overflow-hidden"
        >
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent border-border">
                <TableHead
                  className="cursor-pointer"
                  onClick={() => handleSort('name')}
                >
                  <div className="flex items-center gap-2">
                    Supplier
                    <ArrowUpDown className="w-4 h-4" />
                  </div>
                </TableHead>
                <TableHead>Location</TableHead>
                <TableHead>Exposure</TableHead>
                <TableHead
                  className="cursor-pointer"
                  onClick={() => handleSort('riskScore')}
                >
                  <div className="flex items-center gap-2">
                    Score
                    <ArrowUpDown className="w-4 h-4" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer"
                  onClick={() => handleSort('criticality')}
                >
                  <div className="flex items-center gap-2">
                    Criticality
                    <ArrowUpDown className="w-4 h-4" />
                  </div>
                </TableHead>
                <TableHead>Coordinates</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredAndSortedSuppliers.map((supplier, index) => (
                <motion.tr
                  key={supplier.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className="border-border hover:bg-secondary/30 cursor-pointer transition-colors"
                  onClick={() => handleRowClick(supplier.id)}
                >
                  <TableCell className="font-medium">{supplier.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {supplier.country}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Progress value={supplier.riskScore} className="w-16 h-1.5" />
                      <span className="text-sm">{supplier.riskScore}%</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm font-medium">{supplier.riskLevel}</span>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm font-medium">{supplier.criticality}</span>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-muted-foreground">
                      {supplier.coordinates[1].toFixed(2)}, {supplier.coordinates[0].toFixed(2)}
                    </span>
                  </TableCell>
                </motion.tr>
              ))}
            </TableBody>
          </Table>
        </motion.div>
      </div>
    </div>
  );
}
