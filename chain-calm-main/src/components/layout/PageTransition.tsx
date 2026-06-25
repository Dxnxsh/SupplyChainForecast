import { motion, useReducedMotion } from 'framer-motion';

const EASE_OUT_QUART: [number, number, number, number] = [0.25, 1, 0.5, 1];

interface PageTransitionProps {
  children: React.ReactNode;
}

export function PageTransition({ children }: PageTransitionProps) {
  const shouldReduceMotion = useReducedMotion();
  return (
    <motion.div
      className="flex-1 h-screen overflow-hidden"
      initial={{ opacity: shouldReduceMotion ? 1 : 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: shouldReduceMotion ? 1 : 0 }}
      transition={{ duration: 0.15, ease: EASE_OUT_QUART }}
    >
      {children}
    </motion.div>
  );
}
