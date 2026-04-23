import { cn } from '@/lib/utils';
import { RiskLevel } from '@/types/supplier';

interface RiskBadgeProps {
  level: RiskLevel;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const riskConfig = {
  low: {
    label: 'Low Risk',
    bgClass: 'bg-risk-low/20',
    textClass: 'text-risk-low',
    dotClass: 'bg-risk-low',
  },
  medium: {
    label: 'Medium Risk',
    bgClass: 'bg-risk-medium/20',
    textClass: 'text-risk-medium',
    dotClass: 'bg-risk-medium',
  },
  high: {
    label: 'High Risk',
    bgClass: 'bg-risk-high/20',
    textClass: 'text-risk-high',
    dotClass: 'bg-risk-high',
  },
  critical: {
    label: 'Critical',
    bgClass: 'bg-risk-critical/20',
    textClass: 'text-risk-critical',
    dotClass: 'bg-risk-critical',
  },
};

const sizeConfig = {
  sm: 'text-xs px-2 py-0.5',
  md: 'text-sm px-2.5 py-1',
  lg: 'text-base px-3 py-1.5',
};

export function RiskBadge({ level, showLabel = true, size = 'md' }: RiskBadgeProps) {
  const config = riskConfig[level];

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        config.bgClass,
        config.textClass,
        sizeConfig[size]
      )}
    >
      <span className={cn('w-2 h-2 rounded-full', config.dotClass)} />
      {showLabel && config.label}
    </span>
  );
}
