import { useMemo, useState } from "react";
import { ComposableMap, Geographies, Geography, Marker, Line, ZoomableGroup } from "react-simple-maps";
import { useSnapshot } from "../lib/useSnapshot";
import type { Sector, Status } from "../lib/types";

const GEO_URL = `${import.meta.env.BASE_URL}data/world-110m.json`;

const SHORT: Record<string, string> = {
  shipping_chokepoints: "Shipping",
  semiconductor_electronics: "Chips",
  european_auto: "EU auto",
  critical_materials: "Materials",
  us_logistics: "US freight",
};

const SEV: Record<Status, number> = { active: 0, watch: 1, calm: 2 };
const toneVar = (st: Status) => `var(--${st === "active" ? "alert" : st})`;

// shipping lane waypoints: Hormuz -> Bab-el-Mandeb -> Suez (lon, lat)
const LANE: [number, number][] = [
  [56.5, 26.6],
  [43.3, 12.6],
  [32.5, 30.0],
];

export default function MapView() {
  const { data, error, loading } = useSnapshot();
  const [sel, setSel] = useState<string | null>(null);

  const ordered = useMemo(
    () =>
      data ? [...data.sectors].sort((a, b) => SEV[a.status] - SEV[b.status] || b.p - a.p) : [],
    [data]
  );
  const selected: Sector | undefined =
    ordered.find((s) => s.key === sel) ?? ordered[0];
  const shippingActive = data?.sectors.find((s) => s.key === "shipping_chokepoints")?.status === "active";

  if (loading) return <div className="label" style={{ padding: 24 }}>loading map…</div>;
  if (error || !data)
    return (
      <div className="panel" style={{ padding: 16, borderColor: "var(--alert)" }}>
        <div className="label" style={{ color: "var(--alert)" }}>snapshot unavailable — run scripts.build_ui_snapshot</div>
      </div>
    );

  return (
    <div className="grid" style={{ gap: 12 }}>
      <div>
        <h1 className="display" style={{ margin: 0, fontSize: 24, letterSpacing: "0.03em" }}>Global situation map</h1>
        <div style={{ color: "var(--muted)", fontSize: 14 }}>Where disruptions are happening now — sectors and live events</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 300px", gap: 12, alignItems: "start" }}>
        <div className="panel" style={{ padding: 8, position: "relative" }}>
          <div style={{ position: "absolute", top: 14, left: 14, zIndex: 2, display: "flex", gap: 12, fontSize: 11 }}>
            <span><span className="led calm" style={{ display: "inline-block", verticalAlign: "middle" }} /> calm</span>
            <span><span className="led watch" style={{ display: "inline-block", verticalAlign: "middle" }} /> watch</span>
            <span><span className="led active" style={{ display: "inline-block", verticalAlign: "middle" }} /> disruption</span>
          </div>
          <ComposableMap projection="geoEqualEarth" projectionConfig={{ scale: 165 }} style={{ width: "100%", height: "auto" }}>
            <ZoomableGroup center={[20, 25]} zoom={1} minZoom={1} maxZoom={6}>
              <Geographies geography={GEO_URL}>
                {({ geographies }) =>
                  geographies.map((geo) => (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      style={{
                        default: { fill: "var(--panel-2)", stroke: "var(--border)", strokeWidth: 0.5, outline: "none" },
                        hover: { fill: "var(--panel-2)", stroke: "var(--border-strong)", strokeWidth: 0.5, outline: "none" },
                        pressed: { fill: "var(--panel-2)", outline: "none" },
                      }}
                    />
                  ))
                }
              </Geographies>

              {shippingActive &&
                LANE.slice(0, -1).map((from, i) => (
                  <Line key={i} from={from} to={LANE[i + 1]} stroke="var(--alert)" strokeWidth={1.5} strokeLinecap="round" strokeDasharray="4 4" />
                ))}

              {data.map_points.map((pt, i) => (
                <Marker key={`pt-${i}`} coordinates={[pt.lon, pt.lat]}>
                  <circle r={2.4} fill="var(--alert)" opacity={0.45} />
                </Marker>
              ))}

              {data.sectors.map((s) => {
                const active = selected?.key === s.key;
                return (
                  <Marker key={s.key} coordinates={[s.lon, s.lat]} onClick={() => setSel(s.key)} style={{ default: { cursor: "pointer" } }}>
                    <circle r={active ? 13 : 9} fill="none" stroke={toneVar(s.status)} strokeWidth={1.5} opacity={0.35} />
                    <circle r={active ? 7 : 5.5} fill={toneVar(s.status)} stroke="var(--panel)" strokeWidth={1.2} />
                    <text textAnchor="middle" y={-15} style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 10, fill: "var(--ink)", paintOrder: "stroke", stroke: "var(--panel)", strokeWidth: 3 }}>
                      {SHORT[s.key]}
                    </text>
                  </Marker>
                );
              })}
            </ZoomableGroup>
          </ComposableMap>
          <div style={{ fontSize: 11, color: "var(--muted)", padding: "2px 6px 4px" }}>
            <i className="ti ti-click" aria-hidden="true" /> markers = sectors (click to inspect) · dots = recent geocoded events · scroll to zoom
          </div>
        </div>

        <div className="grid" style={{ gap: 12 }}>
          <div className="panel">
            <div className="panel-head"><span className="tick" /> active hotspots <span className="leader" /></div>
            <div>
              {ordered.map((s) => (
                <button
                  key={s.key}
                  onClick={() => setSel(s.key)}
                  style={{ width: "100%", textAlign: "left", background: selected?.key === s.key ? "var(--panel-2)" : "transparent", border: "none", borderBottom: "1px solid var(--border)", padding: "10px 12px", cursor: "pointer", display: "flex", alignItems: "center", gap: 10, color: "var(--ink)", font: "inherit" }}
                >
                  <span className={`led ${s.status}`} />
                  <span style={{ flex: 1, fontSize: 13 }}>{SHORT[s.key]}</span>
                  <span className="display" style={{ fontSize: 14 }}>{s.p.toFixed(2)}</span>
                </button>
              ))}
            </div>
          </div>

          {selected && (
            <div className="panel" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <div style={{ fontSize: 15 }}>{selected.name}</div>
                <span className={`pill ${selected.status}`}>{selected.status === "active" ? "active" : selected.status}</span>
              </div>
              <div className="label" style={{ fontSize: 11 }}>{selected.subtitle}</div>
              <div style={{ fontSize: 13, lineHeight: 1.6 }}>{selected.summary}</div>
              <div style={{ background: "var(--panel-2)", borderRadius: 8, padding: "8px 10px" }}>
                <div className="label" style={{ fontSize: 10 }}>next 3 days</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 3 }}>
                  <span style={{ fontSize: 13, textTransform: "capitalize" }}>{selected.outlook}</span>
                  <span className="bar" style={{ flex: 1, background: "var(--panel)" }}>
                    <span className={`fill-${selected.status}`} style={{ width: `${Math.round(selected.p * 100)}%` }} />
                  </span>
                  <span style={{ fontSize: 12, color: toneVar(selected.status) }}>{selected.likelihood}</span>
                </div>
              </div>
              {selected.headlines.length > 0 && (
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, lineHeight: 1.6 }}>
                  {selected.headlines.map((h, i) => <li key={i}>{h.title}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
