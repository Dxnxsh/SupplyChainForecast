import { useState, useMemo } from 'react';
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
} from 'react-simple-maps';
import { motion, AnimatePresence } from 'framer-motion';
import { Supplier, RiskLevel } from '@/types/supplier';
import { cn } from '@/lib/utils';

const geoUrl = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

interface WorldMapProps {
  suppliers: Supplier[];
  onSupplierClick: (supplier: Supplier) => void;
  selectedSupplier?: Supplier | null;
}

const riskColors: Record<RiskLevel, string> = {
  low: 'hsl(142, 76%, 46%)',
  medium: 'hsl(45, 93%, 47%)',
  high: 'hsl(0, 84%, 60%)',
  critical: 'hsl(0, 84%, 45%)',
};

export function WorldMap({ suppliers, onSupplierClick, selectedSupplier }: WorldMapProps) {
  const [tooltipContent, setTooltipContent] = useState<Supplier | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });

  const handleMarkerHover = (supplier: Supplier, event: React.MouseEvent) => {
    setTooltipContent(supplier);
    setTooltipPosition({ x: event.clientX, y: event.clientY });
  };

  return (
    <div className="relative w-full h-full bg-card rounded-xl overflow-hidden">
      <ComposableMap
        projection="geoMercator"
        projectionConfig={{
          scale: 140,
          center: [0, 30],
        }}
        className="w-full h-full"
      >
        <ZoomableGroup>
          <Geographies geography={geoUrl}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill="hsl(217, 33%, 17%)"
                  stroke="hsl(217, 33%, 25%)"
                  strokeWidth={0.5}
                  style={{
                    default: { outline: 'none' },
                    hover: { fill: 'hsl(217, 33%, 22%)', outline: 'none' },
                    pressed: { outline: 'none' },
                  }}
                />
              ))
            }
          </Geographies>

          {suppliers.map((supplier) => (
            <Marker
              key={supplier.id}
              coordinates={supplier.coordinates}
              onClick={() => onSupplierClick(supplier)}
              onMouseEnter={(e) => handleMarkerHover(supplier, e as unknown as React.MouseEvent)}
              onMouseLeave={() => setTooltipContent(null)}
            >
              <motion.g
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: 'spring', stiffness: 400, damping: 20 }}
                style={{ cursor: 'pointer' }}
              >
                <circle
                  r={selectedSupplier?.id === supplier.id ? 12 : 8}
                  fill={riskColors[supplier.riskLevel]}
                  fillOpacity={0.3}
                  className="animate-pulse-glow"
                />
                <circle
                  r={selectedSupplier?.id === supplier.id ? 8 : 5}
                  fill={riskColors[supplier.riskLevel]}
                  stroke="hsl(0, 0%, 100%)"
                  strokeWidth={1.5}
                />
              </motion.g>
            </Marker>
          ))}
        </ZoomableGroup>
      </ComposableMap>

      {/* Map Legend */}
      <div className="absolute bottom-4 left-4 glass-card rounded-lg p-3">
        <p className="text-xs font-medium text-muted-foreground mb-2">Risk Level</p>
        <div className="space-y-1.5">
          {[
            { level: 'low' as RiskLevel, label: 'Low', range: '0–30' },
            { level: 'medium' as RiskLevel, label: 'Medium', range: '31–60' },
            { level: 'high' as RiskLevel, label: 'High', range: '61–80' },
            { level: 'critical' as RiskLevel, label: 'Critical', range: '>80' },
          ].map(({ level, label, range }) => (
            <div key={level} className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: riskColors[level] }}
              />
              <span className="text-xs text-foreground">{label}: {range}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Tooltip */}
      <AnimatePresence>
        {tooltipContent && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="fixed z-50 glass-card rounded-lg p-3 pointer-events-none"
            style={{
              left: tooltipPosition.x + 10,
              top: tooltipPosition.y - 10,
            }}
          >
            <p className="font-medium text-foreground">{tooltipContent.name}</p>
            <p className="text-sm text-muted-foreground">{tooltipContent.country}</p>
            <div className="flex items-center gap-2 mt-1">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: riskColors[tooltipContent.riskLevel] }}
              />
              <span className="text-xs text-muted-foreground capitalize">
                {tooltipContent.riskLevel} risk
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
