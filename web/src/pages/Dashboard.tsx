import { Link } from "react-router-dom";
import { useSnapshot } from "../lib/useSnapshot";
import { useDate } from "../lib/DateContext";
import KpiStrip from "../components/KpiStrip";
import SectorCard from "../components/SectorCard";
import EmergingRisks from "../components/EmergingRisks";
import StatusLegend from "../components/StatusLegend";
import { DashboardSkeleton } from "../components/Skeleton";

export default function Dashboard() {
  const { asOf } = useDate();
  const { data, error, loading } = useSnapshot(asOf);

  if (loading) return <DashboardSkeleton />;
  if (error || !data)
    return (
      <div className="panel" style={{ padding: 16, borderColor: "var(--alert)" }}>
        <div className="label" style={{ color: "var(--alert)" }}>snapshot unavailable</div>
        <div style={{ fontSize: 13, marginTop: 6 }}>
          {error}. Run <code>venv311/bin/python -m scripts.build_ui_snapshot</code>.
        </div>
      </div>
    );

  const { active, watch } = data.summary;
  const headline =
    active > 0
      ? `${active} active disruption${active > 1 ? "s" : ""} right now${watch ? `, ${watch} to watch` : ""}`
      : watch > 0
      ? `${watch} area${watch > 1 ? "s" : ""} to watch, no active disruptions`
      : "All sectors calm";

  return (
    <div className="grid" style={{ gap: 12 }}>
      <div>
        <h1 className="display" style={{ margin: 0, fontSize: 24, letterSpacing: "0.03em" }}>
          Supply chain disruption watch
        </h1>
        <div style={{ color: "var(--muted)", fontSize: 14 }}>
          Plain-language status and 3-day outlook for five global sectors
        </div>
      </div>

      <div className="panel" style={{ display: "flex", alignItems: "center", gap: 14, padding: 14 }}>
        <span className={`led ${active ? "active" : watch ? "watch" : "calm"}`} />
        <div className="display" style={{ fontSize: 30, color: `var(--${active ? "alert" : watch ? "watch" : "calm"})` }}>
          {active || watch || 0}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15 }}>{headline}</div>
          <div style={{ fontSize: 12, color: "var(--muted)" }}>{data.data_note}</div>
        </div>
      </div>

      <StatusLegend />

      <KpiStrip snap={data} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))", gap: 12 }}>
        {data.sectors.map((s) => (
          <SectorCard key={s.key} s={s} />
        ))}
      </div>

      <EmergingRisks />

      <div className="panel" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", gap: 10, flexWrap: "wrap" }}>
        <div style={{ fontSize: 13, color: "var(--muted)" }}>
          <i className="ti ti-info-circle" aria-hidden="true" /> Predictions come from a model trained on past disruptions. It catches about 7 in 10 new disruptions.
        </div>
        <Link to="/accuracy" style={{ fontSize: 13 }}>
          See how accurate it is <i className="ti ti-arrow-right" aria-hidden="true" />
        </Link>
      </div>
    </div>
  );
}
