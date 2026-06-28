import type { Sector } from "../lib/types";

const STATUS_LABEL: Record<string, string> = {
  calm: "calm",
  watch: "watch",
  active: "active disruption",
};

export default function SectorCard({ s }: { s: Sector }) {
  return (
    <div className="panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <span
            className={`led ${s.status}`}
            style={{ width: 38, height: 38, borderRadius: 10, boxShadow: "none", background: `var(--${s.status === "active" ? "alert" : s.status}-bg)`, color: `var(--${s.status === "active" ? "alert" : s.status})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}
          >
            <i className={`ti ti-${s.icon}`} aria-hidden="true" />
          </span>
          <div>
            <div style={{ fontSize: 16 }}>{s.name}</div>
            <div className="label" style={{ fontSize: 11 }}>{s.subtitle}</div>
          </div>
        </div>
        <span className={`pill ${s.status}`}>{STATUS_LABEL[s.status]}</span>
      </div>

      <div style={{ fontSize: 14, lineHeight: 1.6 }}>{s.summary}</div>

      <div style={{ background: "var(--panel-2)", borderRadius: 8, padding: "10px 12px" }}>
        <div className="label" style={{ fontSize: 10 }}>next 3 days</div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
          <span style={{ fontSize: 14, textTransform: "capitalize" }}>disruption {s.outlook}</span>
          <span className="bar" style={{ flex: 1, background: "var(--panel)" }}>
            <span className={`fill-${s.status}`} style={{ width: `${Math.round(s.p * 100)}%` }} />
          </span>
          <span style={{ fontSize: 12, color: `var(--${s.status === "active" ? "alert" : s.status})` }}>{s.likelihood}</span>
        </div>
      </div>

      {s.headlines.length > 0 && (
        <div>
          <div className="label" style={{ fontSize: 10, marginBottom: 4 }}>
            <i className="ti ti-news" aria-hidden="true" /> why now
          </div>
          <ul style={{ margin: 0, paddingLeft: 16, fontSize: 13, lineHeight: 1.6 }}>
            {s.headlines.map((h, i) => (
              <li key={i}>{h.title}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
