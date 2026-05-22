import { useState } from 'react';
import { Bell, Search, User } from 'lucide-react';
import { useSearchParams, useLocation, useNavigate } from 'react-router-dom';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { AlertsHub } from '@/components/dashboard/AlertsHub';
import { mapDisruptionEvent } from '@/lib/dataMappers';
import { cn } from '@/lib/utils';
import { useEffect } from 'react';

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [isAlertsOpen, setIsAlertsOpen] = useState(false);
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
      setSearchParams(prev => {
        const newParams = new URLSearchParams(prev);
        newParams.set('q', value);
        return newParams;
      });
    } else {
      setSearchParams(prev => {
        const newParams = new URLSearchParams(prev);
        newParams.delete('q');
        return newParams;
      });
    }
  };

  const handleSelectAlert = (alert: any) => {
    setIsAlertsOpen(false);
    if (alert.matchedNode) {
      navigate(`/?s=${alert.matchedNode}`);
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsAlertsOpen(false);
      if (e.key === '/' && !isSearchablePage) {
        e.preventDefault();
        const searchInput = document.querySelector('input[type="text"]') as HTMLInputElement;
        if (searchInput) searchInput.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isSearchablePage]);

  return (
    <header className="h-16 border-b border-border bg-card/50 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-[100]">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">{title}</h1>
        {subtitle && (
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={isSearchablePage ? "Search suppliers, events..." : "Search available on Map & Suppliers"}
            className="w-64 pl-9 bg-secondary/50 border-border"
            value={isSearchablePage ? query : ''}
            onChange={handleSearchChange}
            disabled={!isSearchablePage}
          />
        </div>

        <div className="relative">
          <Button 
            variant="ghost" 
            size="icon" 
            className="relative"
            onClick={() => setIsAlertsOpen(!isAlertsOpen)}
          >
            <Bell className={cn("w-5 h-5", highRiskCount > 0 && "text-destructive")} />
            {highRiskCount > 0 && (
              <Badge className="absolute -top-1 -right-1 h-5 w-5 p-0 flex items-center justify-center bg-destructive text-xs">
                {highRiskCount}
              </Badge>
            )}
          </Button>

          <AlertsHub 
            isOpen={isAlertsOpen} 
            onClose={() => setIsAlertsOpen(false)} 
            alerts={alerts}
            onSelectAlert={handleSelectAlert}
          />
        </div>

        <div className="flex items-center gap-3 px-3 py-1.5 rounded-full bg-secondary/30 border border-border/50 shadow-sm">
          <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">System Ready</span>
        </div>
      </div>
    </header>
  );
}
