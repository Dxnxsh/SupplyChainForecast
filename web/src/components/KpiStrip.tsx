import type { Snapshot } from "../lib/types";

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="panel" style={{ padding: "8px 12px", borderColor: tone ? `var(--${tone})` : undefined, background: tone ? `var(--${tone}-bg)` : undefined }}>
      <div className="label" style={{ fontSize: 10 }}>{label}</div>
      <div className="display" style={{ fontSize: 22, color: tone ? `var(--${tone})` : undefined }}>{value}</div>
    </div>
  );
}

export default function KpiStrip({ snap }: { snap: Snapshot }) {
  const auc = (snap.metrics?.predictor as any)?.predictor?.auc;
  const onset = (snap.metrics?.predictor_test as any)?.checks?.walk_forward?.mean_auc;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
      <Tile label="articles" value={snap.summary.total_articles.toLocaleString()} />
      <Tile label="clean events" value={String(snap.summary.clean_events)} />
      <Tile label="event-days" value={String(snap.summary.event_days)} />
      <Tile label="walk-fwd auc" value={onset ? onset.toFixed(2) : auc ? auc.toFixed(2) : "—"} tone="accent" />
      <Tile label="watch" value={String(snap.summary.watch)} tone="watch" />
      <Tile label="active" value={String(snap.summary.active)} tone="alert" />
    </div>
  );
}
