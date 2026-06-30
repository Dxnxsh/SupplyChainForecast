import { useMemo } from "react";
import { useSnapshot } from "../lib/useSnapshot";
import { useDate } from "../lib/DateContext";
import type { Status } from "../lib/types";

interface ProductDef {
  id: string;
  name: string;
  subtitle: string;
  icon: string;
  weights: Record<string, number>;
}

const PRODUCTS: ProductDef[] = [
  {
    id: "iphone",
    name: "iPhone",
    subtitle: "Assembled in Asia · components from 43+ countries",
    icon: "ti-device-mobile",
    weights: {
      semiconductor_electronics: 0.50,
      shipping_chokepoints:      0.20,
      critical_materials:        0.15,
      us_logistics:              0.10,
      european_auto:             0.05,
    },
  },
  {
    id: "airpods",
    name: "AirPods",
    subtitle: "H-series chip · rare-earth magnets · lithium battery",
    icon: "ti-headphones",
    weights: {
      semiconductor_electronics: 0.45,
      shipping_chokepoints:      0.25,
      critical_materials:        0.20,
      us_logistics:              0.10,
      european_auto:             0.00,
    },
  },
  {
    id: "ev",
    name: "Electric Vehicle",
    subtitle: "Li-ion pack · power electronics · EU manufacturing",
    icon: "ti-car",
    weights: {
      critical_materials:        0.40,
      european_auto:             0.30,
      semiconductor_electronics: 0.15,
      shipping_chokepoints:      0.10,
      us_logistics:              0.05,
    },
  },
  {
    id: "laptop",
    name: "Laptop",
    subtitle: "CPU / GPU / RAM / SSD · assembled in Taiwan & China",
    icon: "ti-device-laptop",
    weights: {
      semiconductor_electronics: 0.50,
      shipping_chokepoints:      0.20,
      critical_materials:        0.15,
      us_logistics:              0.10,
      european_auto:             0.05,
    },
  },
];

const SECTOR_SHORT: Record<string, string> = {
  shipping_chokepoints:     "Shipping",
  semiconductor_electronics:"Chips",
  european_auto:            "EU auto",
  critical_materials:       "Materials",
  us_logistics:             "US freight",
};

function exposureStatus(p: number): Status {
  if (p >= 0.30) return "active";
  if (p >= 0.15) return "watch";
  return "calm";
}

function exposureLabel(p: number): string {
  if (p >= 0.30) return "elevated";
  if (p >= 0.15) return "moderate";
  return "low";
}

function toneVar(st: Status) {
  return `var(--${st === "active" ? "alert" : st})`;
}

function topDriver(weights: Record<string, number>, pMap: Record<string, number>): string {
  let best = "";
  let bestScore = -1;
  for (const [k, w] of Object.entries(weights)) {
    const score = w * (pMap[k] ?? 0);
    if (score > bestScore) { bestScore = score; best = k; }
  }
  const p = pMap[best] ?? 0;
  const sectorName = SECTOR_SHORT[best] ?? best;
  if (p >= 0.30) return `Primary pressure from ${sectorName} — risk is elevated.`;
  if (p >= 0.15) return `Watch ${sectorName} — early signals, not yet critical.`;
  return `${sectorName} is the largest component by weight; currently stable.`;
}

interface SectorRow {
  key: string;
  weight: number;
  p: number;
  status: Status;
}

export default function Products() {
  const { asOf } = useDate();
  const { data, error, loading } = useSnapshot(asOf);

  const pMap = useMemo(() => {
    if (!data) return {} as Record<string, number>;
    return Object.fromEntries(data.sectors.map((s) => [s.key, s.p]));
  }, [data]);

  const statusMap = useMemo(() => {
    if (!data) return {} as Record<string, Status>;
    return Object.fromEntries(data.sectors.map((s) => [s.key, s.status]));
  }, [data]);

  if (loading) return <div className="label" style={{ padding: 24 }}>loading products…</div>;
  if (error || !data)
    return (
      <div className="panel" style={{ padding: 16, borderColor: "var(--alert)" }}>
        <div className="label" style={{ color: "var(--alert)" }}>snapshot unavailable — run scripts.build_ui_snapshot</div>
      </div>
    );

  return (
    <div className="grid" style={{ gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 8 }}>
        <div>
          <h1 className="display" style={{ margin: 0, fontSize: 24, letterSpacing: "0.03em" }}>Product supply chain</h1>
          <div style={{ color: "var(--muted)", fontSize: 14 }}>Sector forecasts composed into approximate bill-of-materials exposure per product</div>
        </div>
        <div className="panel" style={{ padding: "6px 12px", fontSize: 11, color: "var(--muted)", maxWidth: 340 }}>
          <i className="ti ti-info-circle" aria-hidden="true" /> These are <strong>compositions</strong> of the five sector forecasts using estimated BOM weights. Treat as directional, not precise.
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 12 }}>
        {PRODUCTS.map((prod) => {
          const rows: SectorRow[] = Object.entries(prod.weights)
            .filter(([, w]) => w > 0)
            .map(([key, weight]) => ({
              key,
              weight,
              p: pMap[key] ?? 0,
              status: statusMap[key] ?? "calm",
            }))
            .sort((a, b) => b.weight * b.p - a.weight * a.p);

          const exposure = rows.reduce((acc, r) => acc + r.weight * r.p, 0);
          const st = exposureStatus(exposure);
          const driver = topDriver(prod.weights, pMap);

          return (
            <div key={prod.id} className="panel" style={{ overflow: "hidden" }}>
              <div className="panel-head">
                <span className={`led ${st}`} />
                <i className={`ti ${prod.icon}`} aria-hidden="true" />
                <span style={{ flex: 1, fontSize: 13, color: "var(--ink)", letterSpacing: "0.04em" }}>{prod.name}</span>
                <span
                  className="pill"
                  style={{
                    borderColor: toneVar(st),
                    color: toneVar(st),
                    background: `var(--${st === "active" ? "alert" : st}-bg)`,
                  }}
                >
                  {exposureLabel(exposure)}
                </span>
              </div>

              <div style={{ padding: "10px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
                <div className="label" style={{ fontSize: 10 }}>{prod.subtitle}</div>

                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                    <span>Aggregate exposure</span>
                    <span className="display" style={{ fontSize: 13, color: toneVar(st) }}>{Math.round(exposure * 100)}%</span>
                  </div>
                  <div className="bar">
                    <span
                      style={{
                        display: "block",
                        height: "100%",
                        width: `${Math.round(Math.min(exposure, 1) * 100)}%`,
                        background: toneVar(st),
                        borderRadius: 3,
                      }}
                    />
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {rows.map((r) => (
                    <div key={r.key} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                      <span className={`led ${r.status}`} style={{ flexShrink: 0 }} />
                      <span style={{ flex: 1, color: "var(--ink)" }}>{SECTOR_SHORT[r.key]}</span>
                      <span style={{ color: "var(--muted)", fontSize: 11 }}>{Math.round(r.weight * 100)}% of BOM</span>
                      <span style={{ width: 80 }}>
                        <div className="bar" style={{ height: 4 }}>
                          <span
                            style={{
                              display: "block",
                              height: "100%",
                              width: `${Math.round(r.p * 100)}%`,
                              background: toneVar(r.status),
                              borderRadius: 2,
                            }}
                          />
                        </div>
                      </span>
                      <span style={{ fontSize: 11, color: toneVar(r.status), width: 30, textAlign: "right" }}>{Math.round(r.p * 100)}%</span>
                    </div>
                  ))}
                </div>

                <div style={{ background: "var(--panel-2)", borderRadius: 6, padding: "7px 10px", fontSize: 12, color: "var(--muted)" }}>
                  {driver}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="panel" style={{ padding: "10px 14px", fontSize: 12, color: "var(--muted)" }}>
        <strong style={{ color: "var(--ink)" }}>How this works:</strong> Each sector has a disruption probability score from the predictor model (walk-forward AUC 0.733). Product exposure is the weighted average of those scores using approximate bill-of-materials proportions. A score above 30% is flagged elevated; 15–30% is watch. BOM weights are estimates — actual exposure depends on each manufacturer's sourcing.
      </div>
    </div>
  );
}
