import { motion, useReducedMotion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StatsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: { value: number; isPositive: boolean };
  variant?: 'default' | 'risk-low' | 'risk-medium' | 'risk-high';
}

const variantStyles = {
  default: 'border-border',
  'risk-low': 'border-risk-low/25 risk-glow-low',
  'risk-medium': 'border-risk-medium/25 risk-glow-medium',
  'risk-high': 'border-risk-high/25 risk-glow-high',
};

const variantValueColor = {
  default: 'text-foreground',
  'risk-low': 'text-risk-low',
  'risk-medium': 'text-risk-medium',
  'risk-high': 'text-risk-high',
};

export function StatsCard({ title, value, subtitle, icon: Icon, trend, variant = 'default' }: StatsCardProps) {
  const shouldReduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={shouldReduceMotion ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
      className={cn(
        'bg-card border rounded p-4 flex flex-col gap-3',
        variantStyles[variant]
      )}
    >
      {/* Label row */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono text-muted-foreground tracking-widest uppercase">{title}</span>
        <Icon className="w-3.5 h-3.5 text-muted-foreground/60" />
      </div>

      {/* Value */}
      <div>
        <p className={cn(
          'text-4xl font-bold font-mono leading-none tabular-nums',
          variantValueColor[variant]
        )}>
          {value}
        </p>
        {subtitle && (
          <p className="text-xs text-muted-foreground mt-1.5">{subtitle}</p>
        )}
        {trend && (
          <p className={cn(
            'text-xs font-mono mt-1.5',
            trend.isPositive ? 'text-risk-low' : 'text-risk-high'
          )}>
            {trend.isPositive ? '+' : '−'}{Math.abs(trend.value)}%
          </p>
        )}
      </div>
    </motion.div>
  );
}
