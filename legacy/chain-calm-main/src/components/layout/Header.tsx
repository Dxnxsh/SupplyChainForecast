import { useState, useEffect } from 'react';
import { Bell, Search, X } from 'lucide-react';
import { useSearchParams, useLocation, useNavigate } from 'react-router-dom';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from '@/lib/api';
import { AlertsHub } from '@/components/dashboard/AlertsHub';
import { mapDisruptionEvent } from '@/lib/dataMappers';
import { cn } from '@/lib/utils';

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [isAlertsOpen, setIsAlertsOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const query = searchParams.get('q') || '';

  const alertsQuery = useQuery({
    queryKey: ['events', 'forecasted', 'header'],
    queryFn: () => api.getForecastedEvents(200),
    refetchInterval: 60000,
  });

  const alerts = (alertsQuery.data ?? []).map(mapDisruptionEvent);
  const highRiskCount = alerts.filter(a => a.riskScore && a.riskScore > 60).length;

  const isSearchablePage = location.pathname === '/' || location.pathname === '/suppliers';

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    if (value) {
      setSearchParams(prev => { const p = new URLSearchParams(prev); p.set('q', value); return p; });
    } else {
      setSearchParams(prev => { const p = new URLSearchParams(prev); p.delete('q'); return p; });
    }
  };

  const handleSelectAlert = (alert: any) => {
    setIsAlertsOpen(false);
    if (alert.matchedNode) navigate(`/?s=${alert.matchedNode}`);
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setIsAlertsOpen(false); setSearchOpen(false); }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <header className="h-12 border-b border-border bg-card/60 backdrop-blur-sm flex items-center justify-between px-5 sticky top-0 z-[100] gap-4">
      {/* Page identity */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <h1 className="text-base font-bold tracking-tight text-foreground leading-none whitespace-nowrap">{title}</h1>
          {subtitle && (
            <span className="text-xs font-mono text-muted-foreground hidden md:block truncate">{subtitle}</span>
          )}
        </div>
      </div>

      {/* Right controls */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {/* Search */}
        <AnimatePresence initial={false}>
          {searchOpen && isSearchablePage ? (
            <motion.div
              key="search-open"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 220, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
              className="overflow-hidden"
            >
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <Input
                  autoFocus
                  placeholder="Search…"
                  className="h-7 pl-8 pr-8 text-xs bg-secondary/60 border-border font-sans"
                  value={query}
                  onChange={handleSearchChange}
                />
                {query && (
                  <button
                    onClick={() => { setSearchParams(prev => { const p = new URLSearchParams(prev); p.delete('q'); return p; }); }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {isSearchablePage && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setSearchOpen(v => !v)}
            aria-label="Toggle search"
          >
            <Search className="w-3.5 h-3.5" />
          </Button>
        )}

        {/* Alerts */}
        <div className="relative">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 relative"
            onClick={() => setIsAlertsOpen(!isAlertsOpen)}
            aria-label="Open alerts"
          >
            <Bell className={cn("w-3.5 h-3.5 transition-colors duration-150", highRiskCount > 0 && "text-risk-high")} />
            <AnimatePresence>
              {highRiskCount > 0 && (
                <motion.span
                  key="badge"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 25 }}
                  className="absolute -top-0.5 -right-0.5 h-4 w-4 flex items-center justify-center rounded-full bg-risk-high text-xs font-mono font-bold text-white pointer-events-none"
                >
                  {highRiskCount}
                </motion.span>
              )}
            </AnimatePresence>
          </Button>

          <AlertsHub
            isOpen={isAlertsOpen}
            onClose={() => setIsAlertsOpen(false)}
            alerts={alerts}
            onSelectAlert={handleSelectAlert}
          />
        </div>

        {/* System status */}
        <div className="flex items-center gap-1.5 pl-2 border-l border-border">
          <span
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              alertsQuery.isLoading ? "bg-muted-foreground animate-pulse"
              : alertsQuery.isError ? "bg-risk-high"
              : "bg-risk-low"
            )}
          />
          <span className="text-xs font-mono text-muted-foreground tracking-wider">
            {alertsQuery.isError ? "DEGRADED" : "LIVE"}
          </span>
        </div>
      </div>
    </header>
  );
}
