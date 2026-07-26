interface TrendPoint {
  date: string;
  p: number;
}

function linePoints(data: TrendPoint[], width: number, height: number, pad: number): string {
  const max = Math.max(0.3, ...data.map((d) => d.p));
  return data
    .map((d, i) => {
      const x = pad + (i / (data.length - 1)) * (width - pad * 2);
      const y = height - pad - (d.p / max) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function Sparkline({ data, width = 84, height = 26, color }: {
  data: TrendPoint[]; width?: number; height?: number; color?: string;
}) {
  if (data.length < 2) return null;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block", flexShrink: 0 }}>
      <polyline
        points={linePoints(data, width, height, 2)}
        fill="none"
        stroke={color ?? "currentColor"}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function TrendChart({ data, color, width = 260, height = 64 }: {
  data: TrendPoint[]; color?: string; width?: number; height?: number;
}) {
  if (data.length < 2) return null;
  const pad = 4;
  return (
    <div>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }}>
        <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="var(--border)" strokeWidth={1} />
        <polyline
          points={linePoints(data, width, height, pad)}
          fill="none"
          stroke={color ?? "var(--accent)"}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)", marginTop: 2 }}>
        <span>{data[0].date}</span>
        <span>{data[data.length - 1].date}</span>
      </div>
    </div>
  );
}
