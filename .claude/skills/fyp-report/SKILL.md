---
name: fyp-report
description: Draft, revise, or recheck FYP thesis chapters (Chapter 3/4/5, abstract) for the SupplyChainForecast project. Use whenever the user mentions a chapter draft, .docx report file, abstract, or asks to "recheck" a thesis document. Encodes all house writing rules the user has established so they never need re-stating.
---

# FYP Report Writing — SupplyChainForecast

You are helping write a final-year-project thesis (CSP650 format) about the supply-chain
disruption early-warning system in this repo. These rules were established across many
sessions — apply ALL of them without being reminded.

## Output workflow

1. **Give revised text in chat by default.** Do NOT write into a .docx unless the user
   explicitly asks for a docx output. When they do, use the `anthropic-skills:docx` skill.
2. When asked to "recheck" a draft: read the whole document, check it against every rule
   below, and report violations with their section numbers. Do not edit unless asked.
3. When making requested edits, tell the user exactly where each change was made.

## House style rules (hard constraints)

- **Never use " — " (em dash)** anywhere in the document.
- **No cross-references** like "(section 4.2)" or "(see 3.1)" — write around them.
- **No file paths, directory names, or repo structure** in the text. The reader has no
  idea of the codebase layout. Real model/tool names (MiniLM, FinBERT, XGBoost, BERTopic,
  PostgreSQL) are fine and preferred over generic descriptions.
- **Heading numbering** must be full decimal style: "4.2.2.1 Encoder and Classifier
  Architecture". Never "1) Title" or bullet-style headings.
- **No empty heading gaps**: every heading must be followed by at least one paragraph of
  prose before the next (sub)heading appears.
- **No colon-introduced enumerations** in prose ("...described in turn below: X, Y, and Z").
  Write flowing sentences instead.
- **No explaining things in brackets/parentheses.** Work the explanation into the sentence.
- **Figure/table captions must be short** — one concise line, not a paragraph.
- Every figure and table must be mentioned in the surrounding body text.

## Content facts (do not contradict)

- **Exactly two data inputs**: (1) the historical news corpus bulk backfill — the
  HuggingFace `R3troR0b/news-dataset` plus a Webhose top-up — and (2) the live RSS feed
  ingested periodically. The labelled disruption-event subset is DERIVED from the corpus;
  never present it as a third dataset or third heading.
- **No mentions of legacy/v1 architecture.** Geocoding and alerts ARE implemented — write
  about them as existing features, matter-of-factly.
- **Chapter 3 = methodology** (process, methods, how they are used).
  **Chapter 4 = results** (presenting outcomes, metrics, discussion). Move content
  accordingly when the two overlap.
- Metrics presented must match the app's Accuracy page (sourced from
  `data/predictor_metrics.json`, `data/relevance_metrics_embeddings.json`). If class
  imbalance makes accuracy look poor, explain honestly with PR-AUC / calibration framing —
  never manipulate the test set.

## Test-case tables

Use columns: Test ID, Test Description, Preconditions, Actions, Expected Results,
Actual Result, Status.
