import { useState } from "react";
import { useSnapshot } from "../lib/useSnapshot";
import { useDate } from "../lib/DateContext";
import { TableSkeleton } from "../components/Skeleton";
import type { FeedEntry } from "../lib/types";

const SECTOR_SHORT: Record<string, string> = {
  shipping_chokepoints:     "Shipping",
  semiconductor_electronics: "Chips",
  european_auto:            "EU auto",
  critical_materials:       "Materials",
  us_logistics:             "US freight",
};

function sentimentTone(score: number): string {
  if (score <= -0.3) return "alert";
  if (score >= 0.3) return "calm";
  return "muted";
}

function relBar(p: number, relevant: boolean) {
  const tone = relevant ? "calm" : "muted";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div className="bar" style={{ width: 60, flexShrink: 0 }}>
        <span style={{
          display: "block", height: "100%",
          width: `${Math.round(p * 100)}%`,
          background: `var(--${tone})`,
          borderRadius: 3,
        }} />
      </div>
      <span style={{
        fontSize: 11,
        color: relevant ? `var(--${tone})` : "var(--muted)",
        fontVariantNumeric: "tabular-nums",
      }}>
        {(p * 100).toFixed(0)}%
      </span>
      {relevant && <span style={{ fontSize: 10, color: "var(--calm)" }}>✓</span>}
    </div>
  );
}

function EntryRow({ entry, expanded, onToggle }: {
  entry: FeedEntry;
  expanded: boolean;
  onToggle: () => void;
}) {
  const ts = new Date(entry.ts);
  const timeStr = isNaN(ts.getTime()) ? entry.ts.slice(0, 16) : ts.toLocaleDateString("en-GB", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const sentTone = sentimentTone(entry.sentiment_score);

  return (
    <>
      <tr
        onClick={onToggle}
        style={{
          cursor: "pointer",
          background: expanded ? "var(--panel-2)" : "transparent",
          opacity: entry.relevant ? 1 : 0.6,
          borderBottom: "1px solid var(--border)",
        }}
      >
        <td style={{ padding: "9px 12px", fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>{timeStr}</td>
        <td style={{ padding: "9px 6px", fontSize: 11, color: "var(--muted)" }}>{entry.source}</td>
        <td style={{ padding: "9px 8px", fontSize: 12, lineHeight: 1.4 }}>
          {entry.title}
        </td>
        <td style={{ padding: "9px 8px" }}>
          {relBar(entry.relevance_p, entry.relevant)}
        </td>
        <td style={{ padding: "9px 8px", fontSize: 11 }}>
          {entry.theme
            ? <span style={{ color: "var(--ink)" }}>{entry.theme}</span>
            : <span style={{ color: "var(--muted)" }}>—</span>
          }
        </td>
        <td style={{ padding: "9px 8px", fontSize: 11 }}>
          <span style={{ color: `var(--${sentTone})` }}>
            {entry.sentiment_score > 0 ? "+" : ""}{entry.sentiment_score.toFixed(2)}
          </span>
        </td>
        <td style={{ padding: "9px 12px", fontSize: 11, color: "var(--muted)" }}>
          {entry.sector_key ? SECTOR_SHORT[entry.sector_key] ?? entry.sector_key : "—"}
        </td>
      </tr>
      {expanded && (
        <tr style={{ background: "var(--panel-2)", borderBottom: "1px solid var(--border)" }}>
          <td colSpan={7} style={{ padding: "10px 16px" }}>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 12 }}>
              <div>
                <div className="label" style={{ fontSize: 10, marginBottom: 4 }}>relevance score</div>
                <div>
                  <strong style={{ color: entry.relevant ? "var(--calm)" : "var(--muted)" }}>
                    {(entry.relevance_p * 100).toFixed(1)}%
                  </strong>
                  {" "}vs threshold 59%
                  {" "}→ {entry.relevant ? <span style={{ color: "var(--calm)" }}>relevant ✓</span> : <span style={{ color: "var(--muted)" }}>filtered out</span>}
                </div>
              </div>
              {entry.relevant && entry.theme && (
                <div>
                  <div className="label" style={{ fontSize: 10, marginBottom: 4 }}>routed theme</div>
                  <div>{entry.theme}</div>
                </div>
              )}
              {entry.relevant && entry.sector_key && (
                <div>
                  <div className="label" style={{ fontSize: 10, marginBottom: 4 }}>sector it feeds</div>
                  <div>{SECTOR_SHORT[entry.sector_key] ?? entry.sector_key}</div>
                  <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 2 }}>
                    → raises this sector's news-volume and keyword signals for the next few days
                  </div>
                </div>
              )}
              <div>
                <div className="label" style={{ fontSize: 10, marginBottom: 4 }}>sentiment</div>
                <div style={{ color: `var(--${sentTone})` }}>
                  {entry.sentiment_score > 0 ? "positive" : entry.sentiment_score < 0 ? "negative" : "neutral"}{" "}
                  ({entry.sentiment_score > 0 ? "+" : ""}{entry.sentiment_score.toFixed(3)})
                </div>
                <div style={{ color: "var(--muted)", fontSize: 11, marginTop: 2 }}>factors into the sector's rolling mood signal</div>
              </div>
              <div>
                <a href={entry.url} target="_blank" rel="noopener noreferrer"
                  style={{ color: "var(--accent)", fontSize: 11 }}
                  onClick={(e) => e.stopPropagation()}>
                  open article ↗
                </a>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function Feed() {
  const { asOf } = useDate();
  const { data, error, loading } = useSnapshot(asOf);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "relevant" | "filtered">("all");
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState<string>("all");

  if (loading) return <TableSkeleton />;
  if (error || !data)
    return (
      <div className="panel" style={{ padding: 16, borderColor: "var(--alert)" }}>
        <div className="label" style={{ color: "var(--alert)" }}>snapshot unavailable — run scripts.build_ui_snapshot</div>
      </div>
    );

  const feed = data.feed ?? [];
  const q = search.trim().toLowerCase();
  const filtered = feed.filter((e) => {
    if (filter === "relevant" && !e.relevant) return false;
    if (filter === "filtered" && e.relevant) return false;
    if (sector !== "all" && e.sector_key !== sector) return false;
    if (q && !e.title.toLowerCase().includes(q) && !e.source.toLowerCase().includes(q)) return false;
    return true;
  });

  const nRelevant = feed.filter((e) => e.relevant).length;
  const nFiltered = feed.length - nRelevant;
  const sectorsPresent = Array.from(new Set(feed.map((e) => e.sector_key).filter((k): k is string => !!k)));

  return (
    <div className="grid" style={{ gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 8 }}>
        <div>
          <h1 className="display" style={{ margin: 0, fontSize: 24, letterSpacing: "0.03em" }}>Live feed</h1>
          <div style={{ color: "var(--muted)", fontSize: 14 }}>
            Recent articles. How each one scored, what it was routed to, and which sector it influences
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {(["all", "relevant", "filtered"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: "4px 12px", fontSize: 11, letterSpacing: "0.08em",
                textTransform: "uppercase", borderRadius: 6,
                border: "1px solid",
                borderColor: filter === f ? "var(--border-strong)" : "var(--border)",
                background: filter === f ? "var(--panel-2)" : "transparent",
                color: filter === f ? "var(--ink)" : "var(--muted)",
                cursor: "pointer",
              }}
            >
              {f === "all" ? `all (${feed.length})` : f === "relevant" ? `relevant (${nRelevant})` : `filtered (${nFiltered})`}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="search headline or source (e.g. Hormuz)"
          style={{
            flex: "1 1 240px", padding: "6px 10px", fontSize: 12,
            fontFamily: "IBM Plex Mono, monospace",
            border: "1px solid var(--border)", borderRadius: 6,
            background: "var(--panel)", color: "var(--ink)",
          }}
        />
        <select
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          style={{
            padding: "6px 10px", fontSize: 12, fontFamily: "IBM Plex Mono, monospace",
            border: "1px solid var(--border)", borderRadius: 6,
            background: "var(--panel)", color: "var(--ink)",
          }}
        >
          <option value="all">all sectors</option>
          {sectorsPresent.map((k) => (
            <option key={k} value={k}>{SECTOR_SHORT[k] ?? k}</option>
          ))}
        </select>
      </div>

      {feed.length === 0 ? (
        <div className="panel" style={{ padding: 24, textAlign: "center" }}>
          <div className="label">no articles yet — run ingest_live to populate</div>
          <div style={{ marginTop: 8, fontFamily: "IBM Plex Mono, monospace", fontSize: 12, color: "var(--muted)" }}>
            venv311/bin/python -m scripts.ingest_live --no-geocode
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="panel" style={{ padding: 24, textAlign: "center" }}>
          <div className="label">no articles match this search/filter</div>
        </div>
      ) : (
        <div className="panel" style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["time", "source", "headline", "relevance P", "routed theme", "sentiment", "sector"].map((h) => (
                  <th key={h} style={{
                    padding: "7px 8px", textAlign: "left", fontSize: 10,
                    letterSpacing: "0.12em", textTransform: "uppercase",
                    color: "var(--muted)", fontWeight: 500, whiteSpace: "nowrap",
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((entry, i) => (
                <EntryRow
                  key={`${entry.url}-${i}`}
                  entry={entry}
                  expanded={expanded === i}
                  onToggle={() => setExpanded(expanded === i ? null : i)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
