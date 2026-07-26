// Rule-based (no LLM) composition of "what this can mean for you" text. Unlike a fixed
// per-(sector, status) string, this reads the sector's *actual* current signals each time —
// the top model drivers, the trend direction, and the most recent headline — so the sentence
// changes as reality changes, with no manual re-writing. Only two things are hand-written and
// genuinely sector-invariant: what kind of impact this sector's disruptions typically cause,
// and what category of action is worth checking — everything describing "what's happening
// right now" is pulled live from the snapshot.
import type { Sector } from "./types";

const IMPACT: Record<string, string> = {
  shipping_chokepoints: "shipments via key shipping lanes",
  semiconductor_electronics: "component allocation or pricing for chips and electronics",
  european_auto: "European auto production and parts supply",
  critical_materials: "pricing or availability of lithium, rare earths, and battery materials",
  us_logistics: "US port, trucking, or freight capacity",
};

// Mirrors src/geocoding.py's CHOKEPOINTS keys, so a named lane only shows up here when it's
// actually in this sector's current headlines — not a fixed example list that goes stale the
// moment the real disruption moves to a different chokepoint.
const CHOKEPOINTS: [string, string[]][] = [
  ["Strait of Hormuz", ["strait of hormuz", "hormuz"]],
  ["Bab-el-Mandeb", ["bab-el-mandeb", "bab el mandeb"]],
  ["Suez Canal", ["suez canal", "suez"]],
  ["Red Sea", ["red sea"]],
  ["Strait of Malacca", ["strait of malacca", "malacca"]],
  ["Panama Canal", ["panama canal", "panama"]],
  ["Strait of Gibraltar", ["strait of gibraltar", "gibraltar"]],
  ["English Channel", ["english channel"]],
  ["Taiwan Strait", ["taiwan strait"]],
];

function detectChokepoints(texts: string[]): string[] {
  const lower = texts.join(" | ").toLowerCase();
  return CHOKEPOINTS.filter(([, aliases]) => aliases.some((a) => lower.includes(a)))
    .map(([canonical]) => canonical);
}

function impactFor(s: Sector): string | undefined {
  const base = IMPACT[s.key];
  if (!base || s.key !== "shipping_chokepoints") return base;
  const named = detectChokepoints(s.headlines.map((h) => h.title));
  return named.length > 0 ? `shipments via ${joinNatural(named)}` : base;
}

const ACTION: Record<string, string> = {
  shipping_chokepoints: "confirming carrier ETAs and reviewing safety stock for affected lanes",
  semiconductor_electronics: "confirming allocation with suppliers and reviewing buffer stock for critical parts",
  european_auto: "checking supplier status and reviewing contingency sourcing for EU-manufactured parts",
  critical_materials: "reviewing inventory buffers and alternate sourcing for materials-dependent products",
  us_logistics: "confirming delivery windows and reviewing contingency carriers",
};

function cap1(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function joinNatural(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

// Compares the last 3 days' smoothed P against the 5 days before that, in the sector's own
// 30-day trend series — a real (if simple) read of "is this getting worse or better."
function trendPhrase(trend: Sector["trend"]): string | null {
  if (!trend || trend.length < 8) return null;
  const recent = trend.slice(-3).reduce((sum, t) => sum + t.p, 0) / 3;
  const prior = trend.slice(-8, -3).reduce((sum, t) => sum + t.p, 0) / 5;
  const delta = recent - prior;
  if (delta > 0.05) return "risk has been climbing over the past week";
  if (delta < -0.05) return "risk has eased somewhat over the past week";
  return null;
}

export function guidanceFor(s: Sector): string | null {
  if (s.status !== "watch" && s.status !== "active") return null;
  const impact = impactFor(s);
  const action = ACTION[s.key];
  if (!impact || !action) return null;

  const signals = [...s.drivers.slice(0, 2)];
  const trend = trendPhrase(s.trend);
  if (trend) signals.push(trend);

  let situation = signals.length > 0
    ? cap1(joinNatural(signals))
    : `Signals here have crossed the "${s.status}" threshold`;

  const headline = s.headlines[0];
  if (headline) situation += ` (most recently: "${headline.title}")`;

  const stakes = s.status === "active"
    ? `${cap1(impact)} may be affected in the next few days.`
    : `Worth watching in case this starts affecting ${impact}.`;

  return `${situation}. ${stakes} Consider ${action}.`;
}
