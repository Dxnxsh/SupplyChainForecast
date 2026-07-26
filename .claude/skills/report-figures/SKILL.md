---
name: report-figures
description: Generate thesis figures for the SupplyChainForecast report — confusion matrices, evaluation-metric tables, Mermaid flowcharts, draw.io ERDs, and app screenshots. Use when the user asks for a figure, diagram, flowchart, ERD, confusion matrix, or screenshots for the report.
---

# Report Figures — SupplyChainForecast

Conventions established across sessions for producing thesis figures. Apply them without
being reminded.

## Confusion matrix & evaluation metrics

- Confusion matrix: render as an **image via Python matplotlib** (seaborn heatmap style is
  fine), saved to a file the user can screenshot or insert.
- Evaluation metrics (Accuracy, Precision, Recall, F1): print as a **plain table in the
  terminal**, not an image.
- Numbers must come from the real tracked metrics (`data/predictor_metrics.json`,
  `data/relevance_metrics_embeddings.json`) or a real evaluation run — the figures must
  match what the app's Accuracy page shows.

## Mermaid flowcharts

- Always `flowchart TD` (vertical), never horizontal.
- Must include explicit Start and End terminator nodes: `A(["Start"])`.
- No numbered step labels; node text should be descriptive but compact (2 short lines max
  per node, `\n` for line breaks).
- Keep total length reasonable — collapse trivial sequential steps into one node rather
  than producing a very long chart.
- Deliver as a fenced ```mermaid code block in chat unless asked otherwise.

## draw.io ERDs

- Deliver as a complete .drawio XML file.
- Simple, conventional relations only: primary keys referenced directly as foreign keys.
  No exotic or indirect relationship modelling. Mark PK / FK / UK explicitly.

## App screenshots for figures

- Start the stack (API on :8000 via uvicorn, web via the `.claude/launch.json` dev server),
  open the page in the Browser pane, and capture with `computer {action: "screenshot"}`.
- One screenshot per page/section the text references. Confirm each figure is actually
  mentioned in the surrounding body text (per the fyp-report skill).

## Captions

Short, one line. Format: "Figure 4.3: Confusion matrix of the relevance classifier."
