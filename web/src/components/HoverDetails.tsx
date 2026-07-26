import { useEffect, useRef, useState } from "react";
import { useIsMobile } from "../lib/useIsMobile";

const CLOSE_DELAY_MS = 150;

export default function HoverDetails({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobile();

  const cancelClose = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };
  const scheduleClose = () => {
    cancelClose();
    closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  };

  useEffect(() => {
    if (!isMobile || !open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [isMobile, open]);

  useEffect(() => () => cancelClose(), []);

  const hoverProps = isMobile
    ? {}
    : {
        onMouseEnter: cancelClose,
        onMouseLeave: scheduleClose,
        onFocus: cancelClose,
        onBlur: scheduleClose,
      };

  return (
    <div ref={wrapRef} style={{ position: "relative" }} {...hoverProps}>
      <button
        className="ghost"
        onClick={() => isMobile && setOpen((v) => !v)}
        onMouseEnter={() => !isMobile && setOpen(true)}
        onFocus={() => !isMobile && setOpen(true)}
        style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11 }}
      >
        <span style={{ textDecoration: "underline", textDecorationStyle: "dotted", textUnderlineOffset: 3 }}>
          why now &amp; what this means
        </span>
        <i className={`ti ti-${isMobile ? (open ? "chevron-up" : "chevron-down") : "info-circle"}`} aria-hidden="true" />
      </button>

      {open && (
        <div
          className="panel"
          style={{
            position: "absolute",
            bottom: "calc(100% + 6px)",
            left: 0,
            right: 0,
            zIndex: 20,
            padding: 14,
            maxHeight: 320,
            overflowY: "auto",
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.18)",
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
