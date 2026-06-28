export default function Placeholder({ title, blurb }: { title: string; blurb: string }) {
  return (
    <div className="grid" style={{ gap: 12 }}>
      <h1 className="display" style={{ margin: 0, fontSize: 24, letterSpacing: "0.03em" }}>{title}</h1>
      <div className="panel" style={{ padding: 24 }}>
        <div className="label">on the build list</div>
        <div style={{ fontSize: 14, marginTop: 8, lineHeight: 1.6, maxWidth: 640 }}>{blurb}</div>
      </div>
    </div>
  );
}
