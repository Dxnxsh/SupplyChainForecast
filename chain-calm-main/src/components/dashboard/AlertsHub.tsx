import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, Calendar, ExternalLink, ShieldAlert, X } from 'lucide-react';
import { createPortal } from 'react-dom';
import { DisruptionEvent } from '@/types/supplier';
import { RiskBadge } from './RiskBadge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';

interface AlertsHubProps {
  isOpen: boolean;
  onClose: () => void;
  alerts: DisruptionEvent[];
  onSelectAlert: (alert: DisruptionEvent) => void;
}

export function AlertsHub({ isOpen, onClose, alerts, onSelectAlert }: AlertsHubProps) {
  const highRiskAlerts = alerts.filter(a => a.riskScore && a.riskScore > 60);

  const content = (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Global Backdrop Overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/5 backdrop-blur-[1px] z-[9998] cursor-default"
          />
          
          {/* Hub Panel */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ type: 'spring', damping: 20, stiffness: 300 }}
            className="fixed top-20 right-4 w-96 h-[calc(100vh-120px)] max-h-[600px] bg-card border border-border shadow-2xl rounded-xl z-[9999] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 border-b border-border flex items-center justify-between bg-secondary/20">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-primary" />
                <h3 className="font-semibold text-foreground">Active Risk Alerts</h3>
              </div>
              <RiskBadge level="high" size="sm" labelPrefix={`${highRiskAlerts.length}`} />
            </div>

            <ScrollArea className="flex-grow overflow-y-auto">
              <motion.div 
                initial="hidden"
                animate="show"
                variants={{
                  hidden: { opacity: 0 },
                  show: {
                    opacity: 1,
                    transition: { staggerChildren: 0.05 }
                  }
                }}
                className="p-2 space-y-2"
              >
                {alerts.length === 0 ? (
                  <div className="p-8 text-center space-y-2">
                    <AlertTriangle className="w-8 h-8 text-muted-foreground mx-auto opacity-20" />
                    <p className="text-sm text-muted-foreground">No critical alerts detected</p>
                  </div>
                ) : highRiskAlerts.length > 0 ? (
                  highRiskAlerts.map((alert) => (
                    <motion.div
                      key={alert.id}
                      variants={{
                        hidden: { opacity: 0, x: 20 },
                        show: { opacity: 1, x: 0 }
                      }}
                      whileHover={{ scale: 1.02, backgroundColor: 'rgba(var(--secondary), 0.4)' }}
                      className="p-3 rounded-lg border border-border bg-secondary/10 backdrop-blur-sm hover:bg-secondary/30 transition-all cursor-pointer group relative overflow-hidden"
                      onClick={() => onSelectAlert(alert)}
                    >
                      <div className="absolute left-0 top-0 bottom-0 w-1 bg-risk-high shadow-[0_0_8px_rgba(239,68,68,0.4)]" />
                      <div className="flex items-start justify-between gap-2 pl-2">
                        <div className="flex-1">
                          <h4 className="text-sm font-bold text-foreground group-hover:text-primary transition-colors line-clamp-2 leading-tight">
                            {alert.title}
                          </h4>
                          <div className="flex items-center gap-2 mt-1.5 text-[10px] text-muted-foreground">
                            <span className="font-bold text-primary tracking-wider uppercase">{alert.matchedNode?.replace(/_/g, ' ')}</span>
                            <span className="opacity-30">|</span>
                            <Calendar className="w-3 h-3" />
                            <span>{alert.predictedDate || alert.date}</span>
                          </div>
                        </div>
                        <RiskBadge level={alert.severity} size="sm" showLabel={false} />
                      </div>
                      
                      <div className="flex items-center justify-between mt-3 pl-2">
                        <div className="flex gap-2">
                          {alert.riskScore && (
                            <span className="text-[10px] bg-risk-high/20 text-risk-high px-2 py-0.5 rounded-full font-bold border border-risk-high/30">
                              RISK {Math.round(alert.riskScore)}%
                            </span>
                          )}
                        </div>
                        <Button variant="ghost" size="sm" className="h-7 px-2 text-[10px] gap-1 hover:bg-primary/10 hover:text-primary transition-colors font-bold uppercase tracking-tighter">
                          Engage Map
                          <ExternalLink className="w-3 h-3" />
                        </Button>
                      </div>
                    </motion.div>
                  ))
                ) : (
                  <div className="p-8 text-center space-y-2">
                    <ShieldAlert className="w-8 h-8 text-muted-foreground mx-auto opacity-20" />
                    <p className="text-sm text-muted-foreground">System stable. No new alerts.</p>
                  </div>
                )}
              </motion.div>
            </ScrollArea>

            <div className="p-3 border-t border-border bg-secondary/5 flex justify-center">
              <Button variant="ghost" size="sm" onClick={onClose} className="text-xs">
                Dismiss All
              </Button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );

  return createPortal(content, document.body);
}
