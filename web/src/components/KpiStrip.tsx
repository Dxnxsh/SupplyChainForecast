import { Link } from "react-router-dom";
import type { CSSProperties } from "react";
import type { Snapshot } from "../lib/types";

function Tile({ label, value, tone, to }: { label: string; value: string; tone?: string; to?: string }) {
  const sizing: CSSProperties = { flex: "1 1 108px", minWidth: 108 };
  const body = (
    <div className="panel" style={{ padding: "8px 12px", height: "100%", borderColor: tone ? `var(--${tone})` : undefined, background: tone ? `var(--${tone}-bg)` : undefined }}>
      <div className="label" style={{ fontSize: 10 }}>{label}</div>
      <div className="display" style={{ fontSize: 22, color: tone ? `var(--${tone})` : undefined }}>{value}</div>
    </div>
  );
  return to
    ? <Link to={to} style={{ color: "inherit", ...sizing }}>{body}</Link>
    : <div style={sizing}>{body}</div>;
}

export default function KpiStrip({ snap }: { snap: Snapshot }) {
  const onsetRecall = (snap.metrics?.predictor as any)?.onset_value_add?.predictor_recall;
  const catches = onsetRecall != null ? `~${Math.round(onsetRecall * 10)}/10` : "—";
  return (
    <div style={{ display: "flex", gap: 10, overflowX: "auto" }}>
      <Tile label="articles" value={snap.summary.total_articles.toLocaleString()} />
      <Tile label="clean events" value={String(snap.summary.clean_events)} />
      <Tile label="event-days" value={String(snap.summary.event_days)} />
      <Tile label="catches new events" value={catches} tone="accent" to="/accuracy" />
      <Tile label="watch" value={String(snap.summary.watch)} tone="watch" />
      <Tile label="active" value={String(snap.summary.active)} tone="alert" />
    </div>
  );
}
