# Product

## Register

product

## Users

Supply chain operations analysts and risk managers. They are working a shift or responding to an emerging situation — elevated attention, fast pattern-scanning, ready to act. The context is a workstation or large monitor, ambient light variable (office to NOC). Primary task on any screen: assess whether something requires action right now, and what that action is.

## Product Purpose

Chain Calm is a real-time supply chain disruption intelligence platform. It ingests live news (RSS) and batch article data, runs a multi-stage ML pipeline (NLP classification, NER, geocoding, FinBERT sentiment, XGBoost risk scoring), and produces a 14-day daily risk forecast per supplier node. The operator dashboard surfaces these signals — world map with pulsing risk nodes, supplier exposure table, forecast timelines, and live news feed — so risk managers can detect disruptions early and monitor critical suppliers (TSMC, Foxconn, Port of Long Beach, CATL, Albemarle, Tesla Berlin).

Success: an analyst can sit down, see current risk state globally in under five seconds, drill into any supplier, understand the forecast trajectory, and read the supporting news — without configuring anything.

## Brand Personality

Precise · Vigilant · Restrained

The tool is confident and measured. It doesn't shout; it focuses attention. Urgency is expressed through data hierarchy, not animation or decoration.

## Anti-references

- **Typical SaaS analytics** (Stripe/Mixpanel): Purple-on-light gradients, hero metric cards, dashboard-as-marketing. Chain Calm is an operator tool, not a marketing surface.
- **Generic BI tools** (Power BI/Tableau): Flat gray sidebars, default blue bars, corporate blandness. The data has real operational stakes; the interface should reflect that.
- **Military/cyber ops theater**: Neon-green-on-black HUD aesthetics, radar sweep animations, techno-dystopian atmosphere. Vigilance, not theater.

## Design Principles

1. **Signal before noise.** Risk levels must be instantly scannable without reading labels. Secondary data requires deliberate intent to surface. Hierarchy is earned by operational importance, not visual weight.
2. **Control room discipline.** Every element must justify its presence. Decoration is noise in a high-stakes context. Motion conveys state change only.
3. **The map is the anchor.** Spatial context is the primary mental model; supplier geography comes first, then drill-down. Navigation should always let operators re-orient to the global view.
4. **Trust through precision.** Numbers must mean something. Approximate metrics, rounded ranges, and decorative stats erode the confidence operators need to act.
5. **Steady when the data isn't.** The interface stays calm when risk is elevated. Color and layout do not shift with data state; only semantic risk indicators (colors, counts, severity labels) change.

## Accessibility & Inclusion

- WCAG AA minimum. Risk severity indicators must never rely on color alone — pair with label, icon, or pattern.
- Reduced motion support required (operators may use this on long shifts; persistent animation is fatiguing).
- Body text contrast ≥ 4.5:1 against background. Muted label text ≥ 3:1 for large/secondary use; verify — the current muted-foreground (`215 20% 55%` on `222 47% 6%`) is borderline.
- Dense data tables must remain readable without requiring zoom.
