import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const LAST_SEEN_KEY = "alerts_last_seen";
const POLL_MS = 60000;

interface Alert {
  id: string;
  ts: string;
  sector_key: string;
  sector_name: string;
  from_status: string;
  to_status: string;
  p: number;
  headline: { title: string; url: string } | null;
}

const toneVar = (st: string) => `var(--${st === "active" ? "alert" : st})`;

function timeAgo(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function AlertsBell() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [open, setOpen] = useState(false);
  const [lastSeen, setLastSeen] = useState<string>(() => localStorage.getItem(LAST_SEEN_KEY) ?? "");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      fetch(`${API_BASE}/api/alerts?limit=30`)
        .then((r) => (r.ok ? r.json() : []))
        .then((data: Alert[]) => { if (alive) setAlerts(data); })
        .catch(() => {});
    };
    load();
    const t = setInterval(load, POLL_MS);
    return () => { alive = false; clearInterval(t); };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const unreadCount = alerts.filter((a) => a.ts > lastSeen).length;

  const toggle = () => {
    setOpen((wasOpen) => {
      const next = !wasOpen;
      if (next && alerts.length > 0) {
        // Alerts from the same ingest cycle aren't guaranteed to be in strict
        // timestamp order (loop insertion order vs. wall-clock ts can differ by
        // microseconds), so take the true max rather than assuming alerts[0].
        const newest = alerts.reduce((max, a) => (a.ts > max ? a.ts : max), alerts[0].ts);
        localStorage.setItem(LAST_SEEN_KEY, newest);
        setLastSeen(newest);
      }
      return next;
    });
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="ghost" onClick={toggle} aria-label="alerts" style={{ position: "relative" }}>
        <i className="ti ti-bell" aria-hidden="true" />
        {unreadCount > 0 && (
          <span style={{
            position: "absolute", top: -2, right: -2, background: "var(--alert)", color: "#fff",
            borderRadius: "50%", fontSize: 9, minWidth: 14, height: 14, display: "flex",
            alignItems: "center", justifyContent: "center", padding: "0 3px", lineHeight: 1,
          }}>{unreadCount > 9 ? "9+" : unreadCount}</span>
        )}
      </button>
      {open && (
        <div className="panel" style={{
          position: "absolute", right: 0, top: "calc(100% + 6px)", width: 320, maxHeight: 400,
          overflowY: "auto", zIndex: 20, padding: 4,
        }}>
          <div className="label" style={{ fontSize: 10, padding: "6px 8px" }}>recent status changes</div>
          {alerts.length === 0 ? (
            <div style={{ padding: "12px 8px", fontSize: 12, color: "var(--muted)" }}>No status changes yet.</div>
          ) : (
            alerts.map((a) => (
              <div key={a.id} style={{ padding: 8, borderTop: "1px solid var(--border)", fontSize: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 500 }}>{a.sector_name}</span>
                  <span style={{ fontSize: 10, color: "var(--muted)" }}>{timeAgo(a.ts)}</span>
                </div>
                <div style={{ color: "var(--muted)", marginTop: 2 }}>
                  <span style={{ textTransform: "capitalize" }}>{a.from_status}</span>
                  {" → "}
                  <span style={{ color: toneVar(a.to_status), textTransform: "capitalize", fontWeight: 500 }}>{a.to_status}</span>
                </div>
                {a.headline && (
                  <a href={a.headline.url} target="_blank" rel="noopener noreferrer"
                    style={{ display: "block", marginTop: 4, color: "inherit", fontSize: 11 }}>
                    {a.headline.title}
                  </a>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
