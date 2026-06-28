import argparse
import html
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn


VALID_LABELS = ["LOW", "MEDIUM", "HIGH"]


def create_app(csv_path: Path):
    app = FastAPI(title="Manual Labeling UI")

    def load_df():
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")
        df = pd.read_csv(csv_path)
        required_cols = {"id", "headline", "text", "manual_label", "notes"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        df["manual_label"] = df["manual_label"].fillna("").astype(str).str.upper()
        df["notes"] = df["notes"].fillna("").astype(str)
        return df

    def save_df(df: pd.DataFrame):
        df.to_csv(csv_path, index=False)

    @app.get("/", response_class=HTMLResponse)
    def root():
        return RedirectResponse(url="/label")

    @app.get("/label", response_class=HTMLResponse)
    def get_label(index: int = 0):
        try:
            df = load_df()
        except Exception as e:
            return HTMLResponse(f"<h2>Error loading CSV</h2><pre>{html.escape(str(e))}</pre>", status_code=500)

        total = len(df)
        if total == 0:
            return HTMLResponse("<h2>No rows in CSV.</h2>", status_code=200)

        index = max(0, min(index, total - 1))
        row = df.iloc[index]
        done = int(df["manual_label"].isin(VALID_LABELS).sum())
        progress = (done / total) * 100

        headline = html.escape(str(row.get("headline", "")))
        text = html.escape(str(row.get("text", "")))
        current_label = str(row.get("manual_label", "")).upper()
        notes = html.escape(str(row.get("notes", "")))
        row_id = int(row.get("id", index + 1))
        article_url = html.escape(str(row.get("article_url", "")))

        options_html = ""
        for label in VALID_LABELS:
            checked = "checked" if current_label == label else ""
            options_html += f"""
                <label style='margin-right: 18px;'>
                    <input type='radio' name='manual_label' value='{label}' {checked}> {label}
                </label>
            """

        prev_index = max(0, index - 1)
        next_index = min(total - 1, index + 1)
        unlabelled = df[~df["manual_label"].isin(VALID_LABELS)]
        next_unlabelled_index = int(unlabelled.index[0]) if not unlabelled.empty else index

        page = f"""
        <html>
        <head>
          <title>Manual Labeling UI</title>
          <style>
            body {{ font-family: Arial, sans-serif; max-width: 950px; margin: 24px auto; line-height: 1.45; }}
            .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-top: 14px; }}
            .meta {{ color: #444; }}
            .text-box {{ white-space: pre-wrap; background: #fafafa; border: 1px solid #eee; padding: 12px; border-radius: 6px; max-height: 320px; overflow-y: auto; }}
            .btn {{ padding: 8px 12px; border-radius: 6px; border: 1px solid #bbb; background: #fff; cursor: pointer; text-decoration: none; color: #000; }}
            .btn-primary {{ background: #0b5fff; color: white; border-color: #0b5fff; }}
            textarea {{ width: 100%; min-height: 80px; }}
            .progress-bg {{ background: #eee; border-radius: 999px; height: 12px; }}
            .progress-fill {{ background: #19a34a; height: 12px; border-radius: 999px; width: {progress:.2f}%; }}
          </style>
        </head>
        <body>
          <h2>Manual Severity Labeling</h2>
          <div class='meta'>File: <code>{html.escape(str(csv_path))}</code></div>
          <div class='meta'>Row {index + 1} / {total} &nbsp;|&nbsp; Labeled: {done}/{total} ({progress:.1f}%)</div>
          <div class='progress-bg'><div class='progress-fill'></div></div>

          <div style='margin-top: 12px;'>
            <a class='btn' href='/label?index={prev_index}'>Previous</a>
            <a class='btn' href='/label?index={next_index}'>Next</a>
            <a class='btn' href='/label?index={next_unlabelled_index}'>Go To Next Unlabeled</a>
          </div>

          <div class='card'>
            <div><strong>ID:</strong> {row_id}</div>
            <div><strong>URL:</strong> <a href='{article_url}' target='_blank'>{article_url}</a></div>
            <div style='margin-top:8px;'><strong>Headline:</strong> {headline}</div>
            <div style='margin-top:10px;'><strong>Text:</strong></div>
            <div class='text-box'>{text}</div>
          </div>

          <form method='post' action='/label'>
            <input type='hidden' name='index' value='{index}' />
            <div class='card'>
              <div><strong>Manual Label:</strong></div>
              <div style='margin-top:8px;'>{options_html}</div>
              <div style='margin-top:12px;'><strong>Notes (optional):</strong></div>
              <textarea name='notes'>{notes}</textarea>
              <div style='margin-top: 12px;'>
                <button class='btn btn-primary' type='submit'>Save</button>
              </div>
            </div>
          </form>
        </body>
        </html>
        """
        return HTMLResponse(page)

    @app.post("/label")
    def save_label(
        index: int = Form(...),
        manual_label: str = Form(""),
        notes: str = Form(""),
    ):
        label = manual_label.strip().upper()
        if label and label not in VALID_LABELS:
            raise HTTPException(status_code=400, detail=f"Invalid label: {label}")

        df = load_df()
        if index < 0 or index >= len(df):
            raise HTTPException(status_code=400, detail="Index out of range")

        df.at[index, "manual_label"] = label
        df.at[index, "notes"] = notes.strip()
        save_df(df)

        next_index = min(len(df) - 1, index + 1)
        return RedirectResponse(url=f"/label?index={next_index}", status_code=303)

    @app.get("/stats", response_class=HTMLResponse)
    def stats():
        df = load_df()
        total = len(df)
        counts = df["manual_label"].value_counts(dropna=False).to_dict()
        rows = "".join(
            f"<tr><td>{html.escape(str(k) or '(blank)')}</td><td>{v}</td></tr>"
            for k, v in counts.items()
        )
        return HTMLResponse(
            f"""
            <h2>Label Stats</h2>
            <p>Total rows: {total}</p>
            <table border='1' cellpadding='6' cellspacing='0'>
              <tr><th>Label</th><th>Count</th></tr>
              {rows}
            </table>
            <p><a href='/label'>Back to labeling</a></p>
            """
        )

    return app


def main():
    parser = argparse.ArgumentParser(description="Run local web UI for manual labeling.")
    parser.add_argument("--csv", default="model_training/eval_set.csv", help="Path to eval CSV")
    parser.add_argument("--host", default="127.0.0.1", help="Host")
    parser.add_argument("--port", type=int, default=8765, help="Port")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    app = create_app(csv_path)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
