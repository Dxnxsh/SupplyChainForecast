import { cn } from '@/lib/utils';
import { RiskLevel } from '@/types/supplier';

interface RiskBadgeProps {
  level: RiskLevel;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
  labelPrefix?: string;
}

const riskConfig = {
  low: {
    label: 'LOW',
    bgClass: 'bg-risk-low/12',
    textClass: 'text-risk-low',
    borderClass: 'border-risk-low/30',
    dotClass: 'bg-risk-low',
  },
  medium: {
    label: 'MEDIUM',
    bgClass: 'bg-risk-medium/12',
    textClass: 'text-risk-medium',
    borderClass: 'border-risk-medium/30',
    dotClass: 'bg-risk-medium',
  },
  high: {
    label: 'HIGH',
    bgClass: 'bg-risk-high/12',
    textClass: 'text-risk-high',
    borderClass: 'border-risk-high/30',
    dotClass: 'bg-risk-high',
  },
  critical: {
    label: 'CRITICAL',
    bgClass: 'bg-risk-critical/12',
    textClass: 'text-risk-critical',
    borderClass: 'border-risk-critical/30',
    dotClass: 'bg-risk-critical',
  },
};

const sizeConfig = {
  sm: 'text-xs px-1.5 py-0.5 tracking-widest',
  md: 'text-xs px-2 py-0.5 tracking-widest',
  lg: 'text-xs px-2.5 py-1 tracking-wider',
};

export function RiskBadge({ level, showLabel = true, size = 'md', labelPrefix }: RiskBadgeProps) {
  const config = riskConfig[level];
  const label = labelPrefix ? `${labelPrefix}: ${config.label}` : config.label;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded border font-mono font-medium',
        config.bgClass,
        config.textClass,
        config.borderClass,
        sizeConfig[size]
      )}
      aria-label={!showLabel ? label : undefined}
      role={!showLabel ? 'img' : undefined}
    >
      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', config.dotClass)} aria-hidden="true" />
      {showLabel && <span>{label}</span>}
    </span>
  );
}
