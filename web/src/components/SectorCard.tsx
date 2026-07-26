import { Sparkline } from "./Sparkline";
import HoverDetails from "./HoverDetails";
import { guidanceFor } from "../lib/actionGuidance";
import type { Sector } from "../lib/types";

const STATUS_LABEL: Record<string, string> = {
  calm: "calm",
  watch: "watch",
  active: "active disruption",
};

export default function SectorCard({ s }: { s: Sector }) {
  const lowData = s.data_confidence === "limited";
  const guidance = guidanceFor(s);
  const hasDetails = Boolean(guidance) || s.headlines.length > 0 || s.drivers.length > 0;
  return (
    <div className="panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, flexWrap: "wrap" }}>
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
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {lowData && (
            <span
              className="pill"
              title={`Only ${s.train_pos ?? "few"} confirmed disruption days in training history — predictions here are less reliable.`}
              style={{ borderColor: "var(--border-strong)", color: "var(--muted)" }}
            >
              <i className="ti ti-alert-triangle" aria-hidden="true" /> limited history
            </span>
          )}
          <span className={`pill ${s.status}`}>{STATUS_LABEL[s.status]}</span>
        </div>
      </div>

      <div style={{ fontSize: 14, lineHeight: 1.6 }}>{s.summary}</div>

      <div style={{ background: "var(--panel-2)", borderRadius: 8, padding: "10px 12px", opacity: lowData ? 0.7 : 1 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="label" style={{ fontSize: 10 }}>next 3 days{lowData ? " · low confidence" : ""}</div>
          {s.trend.length > 1 && (
            <span title="30-day trend" style={{ color: lowData ? "var(--muted)" : `var(--${s.status === "active" ? "alert" : s.status})` }}>
              <Sparkline data={s.trend} />
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
          <span style={{ fontSize: 14, textTransform: "capitalize" }}>disruption {s.outlook}</span>
          <span className="bar" style={{ flex: 1, background: "var(--panel)" }}>
            <span className={lowData ? "" : `fill-${s.status}`} style={{ width: `${Math.round(s.p * 100)}%`, background: lowData ? "var(--muted)" : undefined }} />
          </span>
          <span style={{ fontSize: 12, color: lowData ? "var(--muted)" : `var(--${s.status === "active" ? "alert" : s.status})` }}>{s.likelihood}</span>
        </div>
      </div>

      {hasDetails && (
        <HoverDetails>
          {guidance && (
            <div style={{ display: "flex", gap: 8, fontSize: 12, lineHeight: 1.5, color: "var(--muted)" }}>
              <i className="ti ti-bulb" aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
              <div><strong style={{ color: "var(--ink)" }}>What this can mean for you: </strong>{guidance}</div>
            </div>
          )}

          {(s.headlines.length > 0 || s.drivers.length > 0) && (
            <div>
              <div className="label" style={{ fontSize: 10, marginBottom: 4 }}>
                <i className="ti ti-news" aria-hidden="true" /> why now
              </div>
              {s.drivers.length > 0 && (
                <ul style={{ margin: "0 0 6px", paddingLeft: 16, fontSize: 12, lineHeight: 1.6, color: "var(--muted)" }}>
                  {s.drivers.map((d, i) => <li key={i}>{d}</li>)}
                </ul>
              )}
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 13, lineHeight: 1.6 }}>
                {s.headlines.map((h, i) => (
                  <li key={i}>
                    {h.url ? (
                      <a href={h.url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit" }}>
                        {h.title}
                      </a>
                    ) : h.title}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </HoverDetails>
      )}
    </div>
  );
}
