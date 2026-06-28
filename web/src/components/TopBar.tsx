import { NavLink } from "react-router-dom";
import { useEffect, useState } from "react";

const NAV = [
  { to: "/", label: "Situation", end: true },
  { to: "/map", label: "Map" },
  { to: "/products", label: "Products" },
  { to: "/accuracy", label: "Accuracy" },
];

export default function TopBar({ asOf }: { asOf?: string }) {
  const [theme, setTheme] = useState<string>(
    () => localStorage.getItem("theme") || "light"
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <div
      className="panel"
      style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", flexWrap: "wrap", gap: 10 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span
          style={{ width: 26, height: 26, border: "1px solid var(--border-strong)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <i className="ti ti-radar-2" aria-hidden="true" />
        </span>
        <div>
          <div className="display" style={{ fontSize: 15, letterSpacing: "0.1em" }}>DISRUPTION MONITOR</div>
          <div className="label" style={{ fontSize: 10 }}>supply-chain early-warning · v2</div>
        </div>
      </div>

      <nav style={{ display: "flex", gap: 4 }}>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            style={({ isActive }) => ({
              fontSize: 12,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              padding: "5px 10px",
              borderRadius: 6,
              border: "1px solid",
              borderColor: isActive ? "var(--border-strong)" : "transparent",
              color: isActive ? "var(--ink)" : "var(--muted)",
            })}
          >
            {n.label}
          </NavLink>
        ))}
      </nav>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 11, color: "var(--alert)", letterSpacing: "0.1em" }}>● LIVE</span>
        {asOf && <span className="label" style={{ fontSize: 11 }}>as of {asOf}</span>}
        <button className="ghost" onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label="toggle theme">
          <i className={theme === "light" ? "ti ti-moon" : "ti ti-sun"} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
