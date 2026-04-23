import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
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

const navItems = [
  { title: 'World Map', path: '/', icon: Globe },
  { title: 'Suppliers', path: '/suppliers', icon: Building2 },
  { title: 'Forecast', path: '/forecast', icon: LineChart },
  { title: 'News & Events', path: '/news', icon: Newspaper },
  { title: 'Administration', path: '/admin', icon: Settings },
];

export function AppSidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const alertsQuery = useQuery({
    queryKey: ['events', 'forecasted', 'sidebar'],
    queryFn: () => api.getForecastedEvents(100),
  });
  const alertCount = alertsQuery.data?.length ?? 0;

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 72 : 240 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="h-screen bg-sidebar border-r border-sidebar-border flex flex-col"
    >
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-sidebar-border">
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0">
            <Shield className="w-5 h-5 text-primary-foreground" />
          </div>
          {!collapsed && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="font-semibold text-foreground whitespace-nowrap"
            >
              SCRMS
            </motion.span>
          )}
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-md hover:bg-sidebar-accent text-muted-foreground hover:text-foreground transition-colors"
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <ChevronLeft className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          const Icon = item.icon;

          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-foreground'
              )}
            >
              <Icon className="w-5 h-5 flex-shrink-0" />
              {!collapsed && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-sm font-medium whitespace-nowrap"
                >
                  {item.title}
                </motion.span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Status Indicator */}
      <div className="p-3 border-t border-sidebar-border">
        <div
          className={cn(
            'flex items-center gap-3 px-3 py-2.5 rounded-lg bg-sidebar-accent',
            collapsed && 'justify-center'
          )}
        >
          <div className="relative flex-shrink-0">
            <AlertTriangle className="w-5 h-5 text-risk-medium" />
            <span className="absolute -top-1 -right-1 w-2 h-2 bg-risk-medium rounded-full animate-pulse-glow" />
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <p className="text-xs font-medium text-foreground">{alertCount} Active Alerts</p>
              <p className="text-xs text-muted-foreground">Monitoring</p>
            </div>
          )}
        </div>
      </div>
    </motion.aside>
  );
}
