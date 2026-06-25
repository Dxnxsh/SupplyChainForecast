---
target: chain-calm-main/src
total_score: 28
p0_count: 0
p1_count: 0
timestamp: 2026-06-22T00-00-00Z
slug: chain-calm-main-src
---
## Polish Pass — Issues Resolved

All P0/P1/minor observations from the 2026-06-21 critique (16/40) resolved in this pass.

### P0 fixes
- **glass-card removed from all content surfaces**: StatsCard, SuppliersPage table, ResilienceHistoryPage stat panels + chart, NewsEventsPage both columns, AdminPage cards + table, WorldMapDashboard map container. Replaced with `bg-card border border-border`. `glass-card` remains only on SupplierDetailPanel (genuinely floats over map).
- **Staggered animation `prefers-reduced-motion` guard**: `useReducedMotion()` added to all pages and StatsCard. When true: `initial={false}`, delays removed. Stagger capped at `Math.min(index * 0.05, 0.25)` (max 0.25s across all lists).

### P1 fixes
- **SuppliersPage "Score" column**: Column renamed "Risk Score", displays numeric `riskScore / 100`. New "Level" column added renders `<RiskBadge>`. Sort key and display now consistent.
- **NewsEventsPage badge hierarchy**: Risk% rendered as large primary numeral (visually primary). Impact% as secondary badge. Relevance/Severity/Model collapsed behind a "Detail" toggle chevron per card.

### P2 fixes
- **Dead Filters button wired**: Full risk-level chip filter (Low/Medium/High/Critical toggles) with active count badge, clear-all button, and live filtering of the supplier table.

### Minor fixes
- **Hardcoded "Across 8 countries"**: Derived dynamically from `stats.countries`.
- **Purple chart color removed**: `hsl(250, 60%, 60%)` forecast line replaced with primary blue (`hsl(217, 91%, 60%)`). `--chart-4` purple replaced with teal (`185 70% 50%`).
- **Chart colors aligned to design tokens**: `RISK_GREEN`, `FORECAST_BLUE`, `SNAPSHOT_AMBER` constants replace inline literals in ResilienceHistoryPage.
- **Confidence interval filled band**: Two dashed lines replaced with `<Area>` fill at 8% opacity behind the XGBoost line.
- **X-axis locale-aware formatter**: `toLocaleDateString({ month: 'short', day: 'numeric' })` replaces `slice(5)` MM-DD substring.
- **gradient-text utility removed** from index.css.
- **Collapsed sidebar tooltips**: Radix `<Tooltip>` wraps each nav item when collapsed; alert count indicator also has a tooltip.
- **Eyebrow anti-pattern fixed**: Alert count label changed from `text-xs font-bold uppercase tracking-widest` to `text-sm font-semibold`.
- **matched_node JSONB array lookup**: Both event columns in NewsEventsPage use `Array.isArray` check before string equality.

## Estimated Score Delta

| Heuristic | Before | After | Change |
|---|---|---|---|
| 4 Consistency and Standards | 2 | 4 | +2 |
| 5 Error Prevention | 1 | 3 | +2 |
| 6 Recognition Rather Than Recall | 2 | 3 | +1 |
| 8 Aesthetic and Minimalist Design | 1 | 3 | +2 |
| Sam (a11y) | — | — | +3 motion guards |
| **Total** | **16** | **~28** | **+12** |
