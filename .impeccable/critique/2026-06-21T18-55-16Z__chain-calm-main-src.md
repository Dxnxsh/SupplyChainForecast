---
target: chain-calm-main/src
total_score: 16
p0_count: 2
p1_count: 2
timestamp: 2026-06-21T18-55-16Z
slug: chain-calm-main-src
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | "System Ready" badge is hardcoded; no data freshness indicator; no skeleton loaders |
| 2 | Match System / Real World | 2 | "MAE", "XGBoost q75", "Forecasted Events" (misnomer) — unexplained jargon throughout |
| 3 | User Control and Freedom | 2 | Sidebar collapse not persisted; search disabled on 3/5 pages with no explanation |
| 4 | Consistency and Standards | 2 | "Score" column shows string label; risk badge rendered in some places, raw text in others |
| 5 | Error Prevention | 1 | "Filters" button has no onClick — dead affordance; snapshot date silently fails |
| 6 | Recognition Rather Than Recall | 2 | Map nodes show no names at rest; collapsed sidebar has no tooltips |
| 7 | Flexibility and Efficiency | 2 | No keyboard map navigation; no batch actions; rewind only on map page |
| 8 | Aesthetic and Minimalist Design | 1 | News cards show 4–6 equal-weight badges; hero-metric template on every data page |
| 9 | Error Recovery | 2 | Errors styled clearly but messages generic; no retry button; no recovery suggestion |
| 10 | Help and Documentation | 0 | No tooltips, no onboarding, no contextual help anywhere |
| **Total** | | **16/40** | **Poor** |

## Anti-Patterns Verdict

glass-card on every surface (P0); gradient-text utility not removed (detector confirmed); hero-metric stat cards (P0 aesthetic); staggered animations with no prefers-reduced-motion guard (P0 a11y); purple hsl(250, 60%, 60%) forecast line contradicts PRODUCT.md anti-references; uppercase tracked eyebrows in sidebar and header.

Detector: 6 findings — overused-font x2 (index.css), gradient-text x1 (index.css:102), design-system-color x3 (ResilienceHistoryPage.tsx lines 321, 325, 330). gradient-text confirmed real. hsl(250,60%,60%) purple is real. Lines 321 and 330 likely FPs.

## Priority Issues

P0: glass-card universal — replace with bg-card border border-border on all content surfaces; keep glass-card only on map overlay panel and modals.
P0: Staggered animation delay: index * 0.1 with 120 items (12s reveal) and no prefers-reduced-motion guard. Import useReducedMotion, cap stagger at min(index*0.05, 0.25) for first 6 items.
P1: SuppliersPage "Score" column displays riskLevel string ("high") not numeric riskScore. Sort key and cell value disagree.
P1: NewsEventsPage — 4–6 equal-weight metadata badges per card with no hierarchy. Risk% must be visually primary; Relevance/Severity/Model secondary (collapsible).
P2: Dead "Filters" button in SuppliersPage — no onClick handler.

## Persona Red Flags

Alex: disabled search on 3/5 pages; dead Filters button; no keyboard chart nav; Score/riskScore column mismatch.
Sam: no prefers-reduced-motion guard; date inputs have no label association; text-[10px] below 11px minimum; Progress bar has no accessible label.
Shift Analyst: ambient motion habituates attention system; no time-range filter on News; static System Ready badge; MAE given same prominence as exposure score.

## Minor Observations

Hardcoded "Across 8 countries" (6 nodes). Date formatter MM-DD ambiguous. Confidence interval as dashed lines not filled area. Two different purples. matched_node JSONB array vs string equality lookup. No collapsed sidebar tooltips.

## Questions to Consider

1. Does the world map anchor orientation or just look authoritative?
2. What does an analyst do when the forecast says risk peaks Thursday? Is there an action path?
3. Is 120 events a feed or a triage queue?
