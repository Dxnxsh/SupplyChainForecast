const DEFS: { status: string; label: string; text: string }[] = [
  { status: "calm", label: "calm", text: "no meaningful risk signals" },
  { status: "watch", label: "watch", text: "early signals rising, worth monitoring" },
  { status: "active", label: "active", text: "model puts disruption odds at 1 in 4 or higher over the next 3 days" },
];

export default function StatusLegend() {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, fontSize: 12, color: "var(--muted)" }}>
      {DEFS.map((d) => (
        <span key={d.status} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className={`led ${d.status}`} />
          <strong style={{ color: "var(--ink)" }}>{d.label}</strong> — {d.text}
        </span>
      ))}
    </div>
  );
}
