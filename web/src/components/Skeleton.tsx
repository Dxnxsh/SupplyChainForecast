export function SkeletonBlock({ height, width }: { height: number; width?: number | string }) {
  return <div className="skeleton" style={{ height, width: width ?? "100%" }} />;
}

export function DashboardSkeleton() {
  return (
    <div className="grid" style={{ gap: 12 }}>
      <SkeletonBlock height={44} width={320} />
      <SkeletonBlock height={64} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 10 }}>
        {Array.from({ length: 6 }).map((_, i) => <SkeletonBlock key={i} height={56} />)}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))", gap: 12 }}>
        {Array.from({ length: 5 }).map((_, i) => <SkeletonBlock key={i} height={220} />)}
      </div>
    </div>
  );
}

export function MapSkeleton() {
  return (
    <div className="grid" style={{ gap: 12 }}>
      <SkeletonBlock height={44} width={320} />
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 300px", gap: 12 }}>
        <SkeletonBlock height={480} />
        <div style={{ display: "grid", gap: 12 }}>
          <SkeletonBlock height={220} />
          <SkeletonBlock height={240} />
        </div>
      </div>
    </div>
  );
}

export function TableSkeleton() {
  return (
    <div className="grid" style={{ gap: 12 }}>
      <SkeletonBlock height={44} width={320} />
      <SkeletonBlock height={40} />
      {Array.from({ length: 8 }).map((_, i) => <SkeletonBlock key={i} height={28} />)}
    </div>
  );
}
