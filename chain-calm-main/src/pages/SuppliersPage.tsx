import { useState, useMemo } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { Filter, ArrowUpDown, ArrowUp, ArrowDown, X } from 'lucide-react';
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
import { RiskBadge } from '@/components/dashboard/RiskBadge';
import { type RiskLevel } from '@/types/supplier';

const RISK_LEVELS: RiskLevel[] = ['low', 'medium', 'high', 'critical'];

type SortField = 'name' | 'riskScore' | 'criticality';

function SortIcon({ field, sortField, sortDirection }: {
  field: SortField;
  sortField: SortField;
  sortDirection: 'asc' | 'desc';
}) {
  if (field !== sortField) return <ArrowUpDown className="w-3.5 h-3.5 text-muted-foreground/40" />;
  return sortDirection === 'asc'
    ? <ArrowUp className="w-3.5 h-3.5 text-primary" />
    : <ArrowDown className="w-3.5 h-3.5 text-primary" />;
}

export default function SuppliersPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const searchQuery = searchParams.get('q') || '';
  const shouldReduceMotion = useReducedMotion();

  const [sortField, setSortField] = useState<SortField>('riskScore');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [activeFilters, setActiveFilters] = useState<Set<RiskLevel>>(new Set());
  const [showFilters, setShowFilters] = useState(false);

  const toggleFilter = (level: RiskLevel) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  };

  const suppliersQuery = useQuery({
    queryKey: ['suppliers'],
    queryFn: api.getSuppliers,
  });

  const suppliers = useMemo(
    () => (suppliersQuery.data ?? []).map(mapSupplier),
    [suppliersQuery.data]
  );

  const filteredAndSortedSuppliers = useMemo(() => {
    return suppliers
      .filter(
        (s) =>
          (s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          s.country.toLowerCase().includes(searchQuery.toLowerCase())) &&
          (activeFilters.size === 0 || activeFilters.has(s.riskLevel))
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
  }, [searchQuery, sortField, sortDirection, suppliers, activeFilters]);

  const handleSort = (field: SortField) => {
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

  const isFiltered = activeFilters.size > 0 || !!searchQuery;
  const resultSummary = suppliersQuery.isLoading
    ? 'Loading…'
    : isFiltered
    ? `${filteredAndSortedSuppliers.length} of ${suppliers.length} suppliers`
    : `${suppliers.length} suppliers`;

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden">
      <Header title="Suppliers" subtitle="Manage and monitor all suppliers" />

      <div className="flex-1 p-5 overflow-auto">
        {suppliersQuery.isError && (
          <div className="mb-4 rounded border border-risk-high/30 bg-risk-high/8 px-3 py-2 text-xs font-mono text-risk-high">
            BACKEND UNREACHABLE — could not load supplier data
          </div>
        )}

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center gap-2.5 mb-4">
          <button
            onClick={() => setShowFilters((v) => !v)}
            className={`h-7 px-3 rounded border text-xs font-mono tracking-wider uppercase transition-colors flex items-center gap-2 ${
              showFilters
                ? 'bg-secondary border-border text-foreground'
                : 'bg-transparent border-border text-muted-foreground hover:text-foreground'
            }`}
          >
            <Filter className="w-3 h-3" />
            Filter
            {activeFilters.size > 0 && (
              <span className="bg-primary text-primary-foreground text-xs font-bold w-4 h-4 rounded flex items-center justify-center">
                {activeFilters.size}
              </span>
            )}
          </button>

          <AnimatePresence initial={false}>
            {showFilters && (
              <motion.div
                key="filter-chips"
                initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, x: -8 }}
                transition={{ duration: 0.15, ease: [0.25, 1, 0.5, 1] }}
                className="flex items-center gap-1.5"
              >
                {RISK_LEVELS.map((level) => (
                  <button
                    key={level}
                    onClick={() => toggleFilter(level)}
                    aria-pressed={activeFilters.has(level)}
                    className={`h-7 px-2.5 rounded border text-xs font-mono tracking-widest uppercase transition-colors ${
                      activeFilters.has(level)
                        ? level === 'low'   ? 'bg-risk-low/15 border-risk-low/40 text-risk-low'
                        : level === 'medium' ? 'bg-risk-medium/15 border-risk-medium/40 text-risk-medium'
                        : level === 'high'  ? 'bg-risk-high/15 border-risk-high/40 text-risk-high'
                        : 'bg-risk-critical/15 border-risk-critical/40 text-risk-critical'
                        : 'bg-transparent border-border text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {level}
                  </button>
                ))}
                <AnimatePresence>
                  {activeFilters.size > 0 && (
                    <motion.button
                      key="clear"
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      transition={{ duration: 0.12 }}
                      onClick={() => setActiveFilters(new Set())}
                      aria-label="Clear all filters"
                      className="h-7 w-7 flex items-center justify-center rounded border border-border text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <X className="w-3 h-3" />
                    </motion.button>
                  )}
                </AnimatePresence>
              </motion.div>
            )}
          </AnimatePresence>

          <span className="text-xs font-mono text-muted-foreground ml-auto">{resultSummary}</span>
        </div>

        {/* Suppliers Table */}
        <motion.div
          initial={shouldReduceMotion ? false : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
          className="bg-card border border-border rounded overflow-hidden"
        >
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent border-border">
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort('name')}>
                  <div className="flex items-center gap-1.5 text-xs font-mono tracking-widest uppercase text-muted-foreground">
                    Supplier
                    <SortIcon field="name" sortField={sortField} sortDirection={sortDirection} />
                  </div>
                </TableHead>
                <TableHead>
                  <span className="text-xs font-mono tracking-widest uppercase text-muted-foreground">Location</span>
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort('riskScore')}>
                  <div className="flex items-center gap-1.5 text-xs font-mono tracking-widest uppercase text-muted-foreground">
                    Exposure
                    <SortIcon field="riskScore" sortField={sortField} sortDirection={sortDirection} />
                  </div>
                </TableHead>
                <TableHead>
                  <span className="text-xs font-mono tracking-widest uppercase text-muted-foreground">Level</span>
                </TableHead>
                <TableHead className="cursor-pointer select-none" onClick={() => handleSort('criticality')}>
                  <div className="flex items-center gap-1.5 text-xs font-mono tracking-widest uppercase text-muted-foreground">
                    Crit
                    <SortIcon field="criticality" sortField={sortField} sortDirection={sortDirection} />
                  </div>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppliersQuery.isLoading &&
                Array.from({ length: 4 }).map((_, i) => (
                  <TableRow key={`skel-${i}`} className="border-border">
                    {[65, 40, 80, 30, 20].map((w, j) => (
                      <TableCell key={j}>
                        <div className="h-3 bg-secondary/50 rounded animate-pulse" style={{ width: `${w}%` }} />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}

              {!suppliersQuery.isLoading && filteredAndSortedSuppliers.length === 0 && (
                <TableRow className="border-0">
                  <TableCell colSpan={5} className="h-32 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <Filter className="w-4 h-4 text-muted-foreground/30" />
                      <p className="text-xs font-mono text-muted-foreground">
                        {isFiltered ? 'NO MATCHES' : 'NO DATA'}
                      </p>
                      {activeFilters.size > 0 && (
                        <button onClick={() => setActiveFilters(new Set())}
                          className="text-xs font-mono text-primary hover:underline">
                          CLEAR FILTERS
                        </button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )}

              {filteredAndSortedSuppliers.map((supplier, index) => (
                <motion.tr
                  key={supplier.id}
                  initial={shouldReduceMotion ? false : { opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={shouldReduceMotion ? {} : { delay: Math.min(index * 0.04, 0.2), ease: [0.25, 1, 0.5, 1], duration: 0.18 }}
                  className="border-border hover:bg-secondary/25 cursor-pointer transition-colors"
                  onClick={() => handleRowClick(supplier.id)}
                >
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
                </motion.tr>
              ))}
            </TableBody>
          </Table>
        </motion.div>
      </div>
    </div>
  );
}
