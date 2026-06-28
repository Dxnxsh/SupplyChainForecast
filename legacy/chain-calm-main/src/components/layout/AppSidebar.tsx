import { useState, useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import {
  Globe,
  Building2,
  LineChart,
  Newspaper,
  Settings,
  ChevronLeft,
  ChevronRight,
  Shield,
  AlertTriangle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

const navItems = [
  { title: 'World Map', path: '/', icon: Globe },
  { title: 'Suppliers', path: '/suppliers', icon: Building2 },
  { title: 'Forecast', path: '/forecast', icon: LineChart },
  { title: 'News & Events', path: '/news', icon: Newspaper },
  { title: 'Administration', path: '/admin', icon: Settings },
];

export function AppSidebar() {
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window !== 'undefined') return window.innerWidth < 768;
    return false;
  });

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) setCollapsed(true);
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const location = useLocation();
  const alertsQuery = useQuery({
    queryKey: ['events', 'forecasted', 'sidebar'],
    queryFn: () => api.getForecastedEvents(100),
  });
  const alertCount = alertsQuery.data?.length ?? 0;

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 56 : 220 }}
      transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
      className="h-screen bg-sidebar border-r border-sidebar-border flex flex-col flex-shrink-0 overflow-hidden"
    >
      {/* Brand mark */}
      <div className="h-14 flex items-center justify-between px-3 border-b border-sidebar-border">
        <div className="flex items-center gap-2.5 overflow-hidden min-w-0">
          <div className="w-7 h-7 rounded bg-primary flex items-center justify-center flex-shrink-0">
            <Shield className="w-4 h-4 text-primary-foreground" />
          </div>
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.div
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15, ease: [0.25, 1, 0.5, 1] }}
                className="overflow-hidden whitespace-nowrap"
              >
                <p className="font-bold text-sm text-foreground tracking-tight leading-none">SCRMS</p>
                <p className="text-xs text-muted-foreground mt-0.5 font-mono tracking-wider">SUPPLY CHAIN</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-sidebar-accent transition-colors flex-shrink-0"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-0.5">
        <TooltipProvider delayDuration={0}>
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            const Icon = item.icon;

            const linkEl = (
              <NavLink
                key={item.path}
                to={item.path}
                className={cn(
                  'flex items-center gap-3 px-2.5 py-2 rounded text-sm transition-all duration-150',
                  collapsed && 'justify-center px-0',
                  isActive
                    ? 'bg-primary/12 text-primary font-medium'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-foreground'
                )}
              >
                <Icon className={cn('flex-shrink-0', collapsed ? 'w-4 h-4' : 'w-3.5 h-3.5')} />
                {!collapsed && (
                  <span className="whitespace-nowrap">{item.title}</span>
                )}
                {isActive && !collapsed && (
                  <span className="ml-auto w-1 h-1 rounded-full bg-primary" />
                )}
              </NavLink>
            );

            if (collapsed) {
              return (
                <Tooltip key={item.path}>
                  <TooltipTrigger asChild>{linkEl}</TooltipTrigger>
                  <TooltipContent side="right" className="font-sans">{item.title}</TooltipContent>
                </Tooltip>
              );
            }
            return linkEl;
          })}
        </TooltipProvider>
      </nav>

      {/* Alert count strip */}
      <div className="px-2 pb-3">
        <TooltipProvider delayDuration={0}>
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                className={cn(
                  'flex items-center gap-2.5 px-2.5 py-2 rounded border transition-colors',
                  alertCount > 0
                    ? 'border-risk-high/30 bg-risk-high/8 text-risk-high'
                    : 'border-sidebar-border bg-sidebar-accent text-muted-foreground',
                  collapsed && 'justify-center px-0 border-0 bg-transparent'
                )}
              >
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                {!collapsed && (
                  <div className="min-w-0">
                    <p className="text-xs font-semibold leading-none">
                      {alertCount} Alert{alertCount !== 1 ? 's' : ''}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">Active monitoring</p>
                  </div>
                )}
              </div>
            </TooltipTrigger>
            {collapsed && (
              <TooltipContent side="right">
                {alertCount} Alert{alertCount !== 1 ? 's' : ''}
              </TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>
      </div>
    </motion.aside>
  );
}
