import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { AlertTriangle, Calendar, ExternalLink, Shield, X } from 'lucide-react';
import { createPortal } from 'react-dom';
import { DisruptionEvent } from '@/types/supplier';
import { RiskBadge } from './RiskBadge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';

interface AlertsHubProps {
  isOpen: boolean;
  onClose: () => void;
  alerts: DisruptionEvent[];
  onSelectAlert: (alert: DisruptionEvent) => void;
}

export function AlertsHub({ isOpen, onClose, alerts, onSelectAlert }: AlertsHubProps) {
  const shouldReduceMotion = useReducedMotion();
  const highRiskAlerts = alerts.filter(a => a.riskScore && a.riskScore > 60);

  const panelVariants = {
    hidden: shouldReduceMotion ? { opacity: 0 } : { opacity: 0, y: -6, scale: 0.98 },
    show: { opacity: 1, y: 0, scale: 1 },
    exit: shouldReduceMotion ? { opacity: 0 } : { opacity: 0, y: -6, scale: 0.98 },
  };

  const listVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: shouldReduceMotion ? {} : { staggerChildren: 0.04, delayChildren: 0.04 },
    },
  };

  const itemVariants = {
    hidden: shouldReduceMotion ? { opacity: 0 } : { opacity: 0, x: 8 },
    show: { opacity: 1, x: 0 },
  };

  const content = (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
            onClick={onClose}
            className="fixed inset-0 z-[9998] cursor-default"
          />

          <motion.div
            variants={panelVariants}
            initial="hidden"
            animate="show"
            exit="exit"
            transition={{ duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
            className="fixed top-14 right-3 w-88 max-w-[calc(100vw-1.5rem)] h-[calc(100vh-80px)] max-h-[560px] bg-card border border-border rounded z-[9999] overflow-hidden flex flex-col"
            style={{ width: '352px' }}
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-border flex items-center justify-between bg-secondary/20">
              <div className="flex items-center gap-2.5">
                <Shield className="w-3.5 h-3.5 text-primary" />
                <span className="text-xs font-semibold text-foreground">Active Alerts</span>
                {highRiskAlerts.length > 0 && (
                  <span className="text-xs font-mono font-bold bg-risk-high/15 text-risk-high border border-risk-high/30 px-1.5 py-0.5 rounded">
                    {highRiskAlerts.length} HIGH
                  </span>
                )}
              </div>
              <button
                onClick={onClose}
                className="text-muted-foreground hover:text-foreground transition-colors"
                aria-label="Close alerts"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <ScrollArea className="flex-1">
              <motion.div
                variants={listVariants}
                initial="hidden"
                animate="show"
                className="p-2 space-y-1.5"
              >
                {alerts.length === 0 ? (
                  <div className="py-10 text-center space-y-2">
                    <AlertTriangle className="w-6 h-6 text-muted-foreground/30 mx-auto" />
                    <p className="text-xs font-mono text-muted-foreground">NO ACTIVE ALERTS</p>
                  </div>
                ) : highRiskAlerts.length > 0 ? (
                  highRiskAlerts.map(alert => (
                    <motion.div
                      key={alert.id}
                      variants={itemVariants}
                      className="p-3 rounded border border-risk-high/20 bg-risk-high/5 hover:bg-risk-high/10 transition-colors cursor-pointer group"
                      onClick={() => onSelectAlert(alert)}
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <h4 className="text-xs font-medium text-foreground group-hover:text-primary transition-colors line-clamp-2 leading-snug">
                          {alert.title}
                        </h4>
                        <RiskBadge level={alert.severity} size="sm" showLabel={false} />
                      </div>

                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground">
                          <span className="text-primary/80">{alert.matchedNode?.replace(/_/g, ' ')}</span>
                          {(alert.predictedDate || alert.date) && (
                            <>
                              <span className="opacity-30">·</span>
                              <Calendar className="w-2.5 h-2.5" />
                              <span>{alert.predictedDate || alert.date}</span>
                            </>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {alert.riskScore && (
                            <span className="text-xs font-mono font-bold text-risk-high">
                              {Math.round(alert.riskScore)}%
                            </span>
                          )}
                          <ExternalLink className="w-3 h-3 text-muted-foreground group-hover:text-primary transition-colors" />
                        </div>
                      </div>
                    </motion.div>
                  ))
                ) : (
                  <div className="py-10 text-center space-y-2">
                    <Shield className="w-6 h-6 text-muted-foreground/30 mx-auto" />
                    <p className="text-xs font-mono text-muted-foreground">SYSTEM STABLE</p>
                  </div>
                )}
              </motion.div>
            </ScrollArea>

            <div className="px-3 py-2 border-t border-border">
              <Button variant="ghost" size="sm" onClick={onClose} className="w-full text-xs h-7 font-mono text-muted-foreground">
                DISMISS
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );

  return createPortal(content, document.body);
}
