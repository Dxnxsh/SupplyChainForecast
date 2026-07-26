---
name: viva-prep
description: Explain the SupplyChainForecast system in plain language for presentations, viva/examiner Q&A, or the user's own understanding. Use when the user asks "what does X do", "explain the pipeline", "what do I say if someone asks...", asks for a presentation script, or requests an examiner/user-perspective review.
---

# Viva Prep — SupplyChainForecast

The user is a final-year student who must present and defend this project. Answers here
are for a human explaining the system out loud — not for a code reviewer.

## Ground rules

- **Ground every claim in the actual code/config** (CLAUDE.md architecture section,
  `scripts/`, `src/`) — never describe an idealized version of the pipeline.
- **Plain language, real names.** Explain so someone with no ML/CS background follows,
  but keep the real component names (MiniLM, FinBERT, XGBoost, isotonic calibration,
  BERTopic). Define each term in one clause the first time it appears.
- Correct the user's misconceptions directly (e.g. BERTopic is offline-only validation,
  not in the live pipeline; the predictor uses 16 rolling-window features, not raw text).

## The canonical one-breath pipeline summary

RSS news articles come in every 30 minutes → FinBERT scores each article's sentiment →
a MiniLM-based classifier keeps only articles genuinely about supply-chain disruption →
each kept article is routed to one of 5 monitored sectors → per sector, 16 rolling-window
features (article counts, sentiment trends, burst signals) feed an XGBoost model that
outputs a calibrated probability of disruption in the next 1–3 days → the dashboard shows
that as calm / watch / active, with a date wheel to rewind history.

## Common questions to be ready for

- **Purpose / who is it for**: procurement and logistics planners at small/mid firms who
  can't afford commercial risk platforms; gives a free early-warning signal from public
  news so they can act (reroute, pre-order, hedge) days before disruption is official.
- **What is AUC**: probability the model ranks a random disrupted day above a random calm
  day; 0.5 = coin flip, 1.0 = perfect.
- **Why accuracy looks modest**: heavy class imbalance (disruptions are rare), so
  accuracy is the wrong headline metric — point to PR-AUC, recall at the alert threshold,
  and calibration instead. Never suggest inflating metrics.
- **What's unique**: end-to-end LLM-free live pipeline (cheap, reproducible), calibrated
  probabilities rather than raw scores, full date-rewind so every past prediction is
  auditable against what actually happened.

## Deliverables this skill covers

- Per-page presentation scripts (Map, Sectors, Products, Feed, Accuracy): short intro +
  what to point at + one sentence on how the data got there.
- Examiner-mode and end-user-mode critiques when asked "review as examiner/user" — honest,
  structured, with concrete improvement suggestions.
