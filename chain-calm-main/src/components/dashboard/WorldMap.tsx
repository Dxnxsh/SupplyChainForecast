import { useState } from 'react';
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
  useMapContext,
} from 'react-simple-maps';
import { useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { Supplier, RiskLevel, ColoredEdge } from '@/types/supplier';
import { cn } from '@/lib/utils';

const geoUrl = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

interface WorldMapProps {
  suppliers: Supplier[];
  onSupplierClick: (supplier: Supplier) => void;
  selectedSupplier?: Supplier | null;
  coloredEdges: ColoredEdge[];
  isFilterActive: boolean;
  searchQuery?: string;
}

const riskColors: Record<RiskLevel, string> = {
  low: 'hsl(152, 72%, 42%)',
  medium: 'hsl(32, 90%, 52%)',
  high: 'hsl(4, 82%, 58%)',
  critical: 'hsl(0, 78%, 40%)',
};

const ArcLine = ({
  from,
  to,
  riskLevel,
  isPulsing,
  isActive,
  isFilterActive,
  reduceMotion,
}: {
  from: [number, number];
  to: [number, number];
  riskLevel: RiskLevel;
  isPulsing: boolean;
  isActive: boolean;
  isFilterActive: boolean;
  reduceMotion: boolean;
}) => {
  const { projection } = useMapContext();

  const projectedFrom = projection(from);
  const projectedTo = projection(to);

  if (!projectedFrom || !projectedTo) return null;
  const [x1, y1] = projectedFrom;
  const [x2, y2] = projectedTo;

  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;

  const dist = Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
  const curveOffset = dist * 0.2;

  const cpX = midX;
  const cpY = midY - curveOffset;

  const opacity = isActive ? 1.0 : (isFilterActive ? 0.15 : 0.3);
  const strokeColor = isActive ? riskColors[riskLevel] : 'hsl(240, 5%, 28%)';

  const animation = reduceMotion
    ? 'none'
    : isActive && isPulsing
    ? 'flow 1s linear infinite, pulse-opacity 2s ease-in-out infinite'
    : 'flow 1s linear infinite';

  return (
    <path
      d={`M ${x1} ${y1} Q ${cpX} ${cpY} ${x2} ${y2}`}
      fill="none"
      stroke={strokeColor}
      strokeWidth={isActive ? 2 : 1.2}
      strokeLinecap="round"
      className="transition-opacity duration-500"
      style={{
        opacity,
        strokeDasharray: reduceMotion ? 'none' : '4, 4',
        animation,
        willChange: reduceMotion ? 'auto' : 'opacity',
      }}
    />
  );
};

export function WorldMap({
  suppliers,
  onSupplierClick,
  selectedSupplier,
  coloredEdges,
  isFilterActive,
  searchQuery
}: WorldMapProps) {
  const [tooltipContent, setTooltipContent] = useState<Supplier | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
  const [searchParams, setSearchParams] = useSearchParams();
  const shouldReduceMotion = useReducedMotion() ?? false;

  const handleMarkerHover = (supplier: Supplier, event: React.MouseEvent) => {
    setTooltipContent(supplier);
    setTooltipPosition({ x: event.clientX, y: event.clientY });
  };

  const handleSupplierClick = (supplier: Supplier) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set('s', supplier.id);
      return next;
    });
    onSupplierClick(supplier);
  };

  return (
    <div className="relative w-full h-full bg-card rounded-xl overflow-hidden select-none">
      <ComposableMap
        projection="geoMercator"
        projectionConfig={{
          scale: 140,
          center: [0, 30],
        }}
        className="w-full h-full"
      >
        <ZoomableGroup filterZoomEvent={() => false} onMoveEnd={undefined}>
          <Geographies geography={geoUrl}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill="hsl(240, 6%, 13%)"
                  stroke="hsl(240, 5%, 18%)"
                  strokeWidth={0.5}
                  style={{
                    default: { outline: 'none' },
                    hover: { fill: 'hsl(240, 6%, 17%)', outline: 'none' },
                    pressed: { outline: 'none' },
                  }}
                />
              ))
            }
          </Geographies>

          {/* Render Connections */}
          {coloredEdges.map((edge) => (
            <ArcLine
              key={`${edge.fromId}-${edge.toId}`}
              from={edge.from}
              to={edge.to}
              riskLevel={edge.sourceRiskLevel}
              isPulsing={edge.isPulsing}
              isActive={edge.isActive}
              isFilterActive={isFilterActive}
              reduceMotion={shouldReduceMotion}
            />
          ))}

          {suppliers.map((supplier) => {
            const isSearchMatch = searchQuery && supplier.name.toLowerCase().includes(searchQuery.toLowerCase());
            const isSelected = selectedSupplier?.id === supplier.id;

            return (
              <Marker
                key={supplier.id}
                coordinates={supplier.coordinates}
                onClick={() => handleSupplierClick(supplier)}
                onMouseEnter={(e) => handleMarkerHover(supplier, e as unknown as React.MouseEvent)}
                onMouseLeave={() => setTooltipContent(null)}
              >
                <motion.g
                  initial={shouldReduceMotion ? false : { scale: 0 }}
                  animate={{ scale: isSearchMatch ? 1.4 : 1 }}
                  transition={shouldReduceMotion ? {} : { type: 'spring', stiffness: 400, damping: 20 }}
                  style={{ cursor: 'pointer' }}
                >
                  <AnimatePresence>
                    {supplier.riskLevel === 'critical' && !shouldReduceMotion && (
                      <motion.circle
                        initial={{ r: 8, opacity: 0 }}
                        animate={{ r: 24, opacity: [0, 0.4, 0] }}
                        transition={{ duration: 3, repeat: Infinity, ease: "easeOut" }}
                        fill={riskColors.critical}
                        className="pointer-events-none"
                      />
                    )}
                  </AnimatePresence>
                  <circle
                    r={isSelected ? 14 : (isSearchMatch ? 12 : 8)}
                    fill={riskColors[supplier.riskLevel]}
                    fillOpacity={isSearchMatch ? 0.5 : 0.3}
                    tabIndex={0}
                    aria-label={`Supplier: ${supplier.name}, Risk: ${supplier.riskLevel}`}
                    className={cn(
                      "animate-pulse-glow focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
                      (isSearchMatch || isSelected) && "stroke-white stroke-2"
                    )}
                  />
                  <circle
                    r={isSelected ? 9 : (isSearchMatch ? 8 : 5)}
                    fill={riskColors[supplier.riskLevel]}
                    stroke="hsl(240, 7%, 8%)"
                    strokeWidth={isSearchMatch || isSelected ? 2 : 1}
                  />
                </motion.g>
              </Marker>
            );
          })}
        </ZoomableGroup>
      </ComposableMap>

      {/* Map Legend */}
      <div className="absolute bottom-4 left-4 glass-card rounded p-3 min-w-[140px]">
        <p className="text-xs font-mono text-muted-foreground mb-2 tracking-widest uppercase">Exposure</p>
        <div className="space-y-1.5">
          {[
            { level: 'low' as RiskLevel, label: 'Low', range: '0–8' },
            { level: 'medium' as RiskLevel, label: 'Medium', range: '9–18' },
            { level: 'high' as RiskLevel, label: 'High', range: '19–30' },
            { level: 'critical' as RiskLevel, label: 'Critical', range: '>30' },
          ].map(({ level, label, range }) => (
            <div key={level} className="flex items-center gap-2">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: riskColors[level] }}
              />
              <span className="text-xs font-mono text-foreground">{label}</span>
              <span className="text-xs font-mono text-muted-foreground ml-auto">{range}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Tooltip */}
      <AnimatePresence>
        {tooltipContent && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 10 }}
            className="fixed z-50 glass-card rounded-xl p-4 pointer-events-none shadow-2xl border-primary/20"
            style={{
              left: tooltipPosition.x + 15,
              top: tooltipPosition.y - 15,
            }}
          >
            <div className="flex items-start justify-between gap-4 mb-3">
              <div>
                <p className="font-bold text-foreground text-sm leading-tight">{tooltipContent.name}</p>
                <p className="text-xs font-mono text-muted-foreground mt-0.5">{tooltipContent.country}</p>
              </div>
              <div className="text-right">
                <p className="text-2xl font-bold font-mono text-foreground leading-none tabular-nums">{tooltipContent.riskScore}%</p>
                <p className="text-xs font-mono text-muted-foreground tracking-widest uppercase mt-0.5">EXPOSURE</p>
              </div>
            </div>

            <div className="flex items-center gap-2 mb-3">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: riskColors[tooltipContent.riskLevel] }}
              />
              <span className="text-xs font-mono font-medium uppercase tracking-wider" style={{ color: riskColors[tooltipContent.riskLevel] }}>
                {tooltipContent.riskLevel}
              </span>
            </div>

            {tooltipContent.products && tooltipContent.products.length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-border/40">
                <p className="text-xs font-mono text-muted-foreground tracking-widest uppercase">SUPPLIES</p>
                <div className="flex flex-wrap gap-1">
                  {tooltipContent.products.slice(0, 3).map(p => (
                    <span key={p} className="text-xs font-mono bg-secondary/60 text-foreground px-1.5 py-0.5 rounded border border-border/40">
                      {p}
                    </span>
                  ))}
                  {tooltipContent.products.length > 3 && (
                    <span className="text-xs font-mono text-muted-foreground">+{tooltipContent.products.length - 3}</span>
                  )}
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes flow {
          from { stroke-dashoffset: 16; }
          to { stroke-dashoffset: 0; }
        }
        @keyframes pulse-opacity {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
      `}} />
    </div>
  );
}
