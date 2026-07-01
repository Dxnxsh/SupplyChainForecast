import { useDate } from "../lib/DateContext";
import { clustersAsOf, useEmergingTimeline, type EmergingCluster, type EmergingStatus } from "../lib/emergingTimeline";

const STATUS_LABEL: Record<EmergingStatus, string> = {
  nascent: "watching",
  bursting: "bursting",
  candidate: "candidate sector",
};

function StatusPill({ status }: { status: EmergingStatus }) {
  if (status === "candidate") return <span className="pill active" style={{ fontSize: 10 }}>{STATUS_LABEL[status]}</span>;
  if (status === "bursting") return <span className="pill watch" style={{ fontSize: 10 }}>{STATUS_LABEL[status]}</span>;
  return (
    <span className="pill" style={{ fontSize: 10, color: "var(--muted)", borderColor: "var(--border-strong)" }}>
      {STATUS_LABEL[status]}
    </span>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(1, ...values);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 20, flexShrink: 0 }} title="recent weekly article count">
      {values.map((v, i) => (
        <span
          key={i}
          style={{
            width: 4,
            height: Math.max(2, Math.round((v / max) * 20)),
            background: "var(--accent)",
            opacity: 0.35 + 0.65 * (i / Math.max(1, values.length - 1)),
            borderRadius: 1,
          }}
        />
      ))}
    </div>
  );
}

function ClusterRow({ c }: { c: EmergingCluster }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", borderTop: "1px solid var(--border)" }}>
      <StatusPill status={c.status} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, textTransform: "capitalize", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {c.label}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)" }}>
          {c.n_total} article{c.n_total === 1 ? "" : "s"} since {c.first_seen}
        </div>
      </div>
      <Sparkline values={c.velocity} />
    </div>
  );
}

export default function EmergingRisks() {
  const { asOf } = useDate();
  const { timeline, loaded } = useEmergingTimeline();

  if (!loaded) return null;
  const clusters = clustersAsOf(timeline, asOf);
  if (clusters.length === 0) return null;

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="tick" />
        emerging risks
        <span className="leader" />
      </div>
      <div style={{ padding: "8px 14px 4px", fontSize: 11, color: "var(--muted)" }}>
        <i className="ti ti-info-circle" aria-hidden="true" /> Emerging signal — not yet forecast. Topics discovered
        directly from live news, outside the five monitored sectors.
      </div>
      <div>
        {clusters.map((c) => (
          <ClusterRow key={c.cluster_id} c={c} />
        ))}
      </div>
    </div>
  );
}
