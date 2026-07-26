import { useRef, useEffect, useCallback, useState, useMemo } from "react";
import { useDate } from "../lib/DateContext";

const DAY_MS = 86400000;
const START = new Date("2025-06-01").getTime();
const TICK_W = 6;

function fmt(ts: number): string {
  return new Date(ts).toISOString().slice(0, 10);
}

function fmtLabel(ts: number): string {
  const d = new Date(ts);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

function fmtMonth(ts: number): string {
  const d = new Date(ts);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[d.getMonth()]} '${String(d.getFullYear()).slice(2)}`;
}

export default function DateWheel() {
  const { asOf, setAsOf, maxDate } = useDate();
  const trackRef = useRef<HTMLDivElement>(null);
  const ready = useRef(false);
  const programmatic = useRef(false);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragStartX = useRef(0);
  const dragStartScroll = useRef(0);
  const [halfW, setHalfW] = useState(0);

  // Falls back to today until the live max date resolves, then self-corrects.
  const END = useMemo(() => (maxDate ? new Date(maxDate).getTime() : Date.now()), [maxDate]);
  const TOTAL_DAYS = Math.round((END - START) / DAY_MS);
  const CONTENT_W = (TOTAL_DAYS + 1) * TICK_W;

  const heights = useMemo(() => {
    const h: number[] = [];
    for (let i = 0; i <= TOTAL_DAYS; i++) {
      const ts = START + i * DAY_MS;
      h.push(new Date(ts).getDate() === 1 ? 1.0 : 0.4);
    }
    return h;
  }, [TOTAL_DAYS]);

  const currentIdx = asOf
    ? Math.round((new Date(asOf).getTime() - START) / DAY_MS)
    : TOTAL_DAYS;

  // Tracks the in-flight target index so rapid clicks accumulate instead of
  // each reading the same stale render-time currentIdx.
  const pendingIdx = useRef(currentIdx);
  useEffect(() => { pendingIdx.current = currentIdx; }, [currentIdx]);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const measure = () => setHalfW(Math.floor(el.clientWidth / 2));
    measure();
    const obs = new ResizeObserver(measure);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const scrollToIdx = useCallback((idx: number, instant = false) => {
    const el = trackRef.current;
    if (!el || !halfW) return;
    const target = idx * TICK_W + TICK_W / 2;
    programmatic.current = true;
    if (instant) {
      el.scrollLeft = target;
      setTimeout(() => { programmatic.current = false; }, 50);
    } else {
      el.scrollTo({ left: target, behavior: "smooth" });
      setTimeout(() => { programmatic.current = false; }, 500);
    }
  }, [halfW]);

  useEffect(() => {
    // Wait for the real end-of-range before the first scroll commit — scrolling to
    // a provisional "today" fallback and then jumping once maxDate resolves would
    // fire a spurious native scroll event that knocks the wheel off "live".
    if (!halfW || !maxDate) return;
    scrollToIdx(currentIdx, true);
    const t = setTimeout(() => { ready.current = true; }, 200);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [halfW, maxDate]);

  useEffect(() => {
    if (ready.current && halfW) scrollToIdx(currentIdx);
  }, [currentIdx, scrollToIdx, halfW]);

  const idxFromScroll = useCallback((): number => {
    const el = trackRef.current;
    if (!el) return TOTAL_DAYS;
    const centerScroll = el.scrollLeft + el.clientWidth / 2;
    const idx = Math.round((centerScroll - halfW - TICK_W / 2) / TICK_W);
    return Math.max(0, Math.min(TOTAL_DAYS, idx));
  }, [halfW]);

  const commitScroll = useCallback(() => {
    const idx = idxFromScroll();
    if (idx === TOTAL_DAYS) setAsOf(null);
    else setAsOf(fmt(START + idx * DAY_MS));
  }, [idxFromScroll, setAsOf]);

  const onScroll = useCallback(() => {
    if (!ready.current || programmatic.current) return;
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(commitScroll, 150);
  }, [commitScroll]);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
    dragStartX.current = e.clientX;
    dragStartScroll.current = trackRef.current?.scrollLeft ?? 0;
  };

  useEffect(() => {
    if (!dragging) return;
    const handleMove = (e: MouseEvent) => {
      const el = trackRef.current;
      if (!el) return;
      programmatic.current = true;
      el.scrollLeft = dragStartScroll.current + (dragStartX.current - e.clientX);
    };
    const handleUp = () => {
      setDragging(false);
      programmatic.current = false;
      commitScroll();
    };
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [dragging, commitScroll]);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const handle = (e: WheelEvent) => {
      e.preventDefault();
      programmatic.current = false;
      el.scrollLeft += e.deltaY || e.deltaX;
      onScroll();
    };
    el.addEventListener("wheel", handle, { passive: false });
    return () => el.removeEventListener("wheel", handle);
  }, [onScroll]);

  const step = (dir: -1 | 1) => {
    const next = Math.max(0, Math.min(TOTAL_DAYS, pendingIdx.current + dir));
    pendingIdx.current = next;
    if (next === TOTAL_DAYS) setAsOf(null);
    else setAsOf(fmt(START + next * DAY_MS));
  };

  return (
    <div className="panel" style={{ padding: "4px 0", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <button
          onClick={() => step(-1)}
          style={{
            border: "none", background: "transparent", cursor: "pointer",
            padding: "4px 10px", fontSize: 15, color: "var(--muted)", flexShrink: 0,
          }}
          aria-label="Previous day"
        >‹</button>

        <div style={{ flex: 1, position: "relative", overflow: "hidden" }}>
          {/* Center indicator */}
          <div style={{
            position: "absolute", left: "50%", top: 0, bottom: 0,
            width: 2, marginLeft: -1,
            background: "var(--alert)", opacity: 0.8,
            zIndex: 2, pointerEvents: "none",
          }} />

          <div
            ref={trackRef}
            onMouseDown={handleMouseDown}
            onScroll={onScroll}
            style={{
              overflowX: "scroll",
              overflowY: "hidden",
              cursor: dragging ? "grabbing" : "grab",
              userSelect: "none",
              scrollbarWidth: "none",
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-end", height: 20 }}>
              <div style={{ width: halfW, flexShrink: 0 }} />
              {heights.map((h, i) => {
                const ts = START + i * DAY_MS;
                const d = new Date(ts);
                const isFirst = d.getDate() === 1;
                const isSelected = i === currentIdx;
                return (
                  <div
                    key={i}
                    onClick={() => {
                      if (i === TOTAL_DAYS) setAsOf(null);
                      else setAsOf(fmt(ts));
                    }}
                    style={{
                      width: TICK_W, flexShrink: 0,
                      display: "flex", justifyContent: "center", alignItems: "flex-end",
                      height: "100%", cursor: "pointer",
                    }}
                  >
                    <div style={{
                      width: 0,
                      height: `${Math.round(h * 100)}%`,
                      borderLeft: `${isFirst ? 2.5 : 1.5}px dotted ${isSelected ? "var(--alert)" : isFirst ? "var(--ink)" : "var(--muted)"}`,
                      opacity: isSelected ? 1 : isFirst ? 0.9 : 0.45,
                    }} />
                  </div>
                );
              })}
              <div style={{ width: halfW, flexShrink: 0 }} />
            </div>

            <div style={{ display: "flex", height: 11, position: "relative" }}>
              <div style={{ width: halfW, flexShrink: 0 }} />
              <div style={{ width: CONTENT_W, flexShrink: 0, position: "relative" }}>
                {heights.map((_, i) => {
                  const ts = START + i * DAY_MS;
                  const d = new Date(ts);
                  if (d.getDate() !== 1) return null;
                  return (
                    <span
                      key={i}
                      style={{
                        position: "absolute",
                        left: i * TICK_W,
                        transform: "translateX(-50%)",
                        fontSize: 8, color: "var(--muted)",
                        whiteSpace: "nowrap", letterSpacing: "0.05em",
                      }}
                    >
                      {fmtMonth(ts)}
                    </span>
                  );
                })}
              </div>
              <div style={{ width: halfW, flexShrink: 0 }} />
            </div>
          </div>
        </div>

        <button
          onClick={() => step(1)}
          style={{
            border: "none", background: "transparent", cursor: "pointer",
            padding: "4px 10px", fontSize: 15, color: "var(--muted)", flexShrink: 0,
          }}
          aria-label="Next day"
        >›</button>
      </div>

      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 10, marginTop: 1 }}>
        <span style={{
          fontFamily: "IBM Plex Mono, monospace", fontSize: 10,
          color: asOf ? "var(--ink)" : "var(--alert)", letterSpacing: "0.08em",
        }}>
          {asOf ? fmtLabel(new Date(asOf).getTime()) : "● LIVE"}
        </span>
        {asOf && (
          <button
            onClick={() => setAsOf(null)}
            style={{
              border: "1px solid var(--border)", background: "transparent",
              borderRadius: 4, padding: "1px 7px", fontSize: 9,
              color: "var(--alert)", cursor: "pointer",
              letterSpacing: "0.08em", textTransform: "uppercase",
            }}
          >● live</button>
        )}
        <span style={{ fontSize: 9, color: "var(--muted)" }}>
          · drag or scroll to rewind · dots are month starts
        </span>
      </div>
    </div>
  );
}
