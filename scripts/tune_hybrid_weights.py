import json
import statistics
from pathlib import Path
from datetime import datetime

import src.predictive_forecasting as pf
import src.forecast_validation as fv

profiles = {
    "baseline": {"high": 1.0, "medium": 0.7, "low": 0.4, "none": 0.0},
    "conservative": {"high": 0.85, "medium": 0.55, "low": 0.25, "none": 0.0},
    "balanced": {"high": 0.95, "medium": 0.65, "low": 0.35, "none": 0.0},
}
alphas = [0.5, 0.6, 0.7]

nodes = [
    "CATL_Ningde",
    "Port_of_Long_Beach",
    "TSMC_Hsinchu",
    "Foxconn_Zhengzhou",
    "Tesla_Berlin",
    "Albemarle_Chile",
]


def write_forecasts(events, alpha):
    out_dir = Path("data/forecasts")
    out_dir.mkdir(parents=True, exist_ok=True)
    all_out = {}

    for node in nodes:
        df = pf.create_hybrid_forecast(events, node, forecast_days=14, alpha=alpha)
        if df is None or df.empty:
            continue

        records = df.to_dict("records")
        for row in records:
            if isinstance(row["ds"], datetime):
                row["ds"] = row["ds"].date().isoformat()
            elif hasattr(row["ds"], "isoformat"):
                row["ds"] = row["ds"].isoformat()

        all_out[node] = records
        with open(out_dir / f"{node}_forecast.json", "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

    with open(out_dir / "all_forecasts.json", "w", encoding="utf-8") as f:
        json.dump(all_out, f, indent=2)


def main():
    events = pf.load_temporal_enriched_events()
    if not events:
        raise RuntimeError("No temporal enriched events found")

    base_weights = dict(pf.CONFIDENCE_WEIGHTS)
    results = []

    for profile_name, weights in profiles.items():
        pf.CONFIDENCE_WEIGHTS = dict(weights)

        for alpha in alphas:
            write_forecasts(events, alpha)
            report = fv.validate_forecasts(nodes=nodes, output_dir="data/validation")
            maes = [v["mae"] for v in report["nodes"].values() if isinstance(v, dict) and "mae" in v]
            avg_mae = statistics.mean(maes) if maes else float("inf")

            results.append(
                {
                    "profile": profile_name,
                    "alpha": alpha,
                    "weights": dict(weights),
                    "avg_mae": round(avg_mae, 3),
                    "node_mae": {k: v["mae"] for k, v in report["nodes"].items()},
                }
            )

    pf.CONFIDENCE_WEIGHTS = base_weights
    results.sort(key=lambda x: x["avg_mae"])
    best = results[0]

    Path("data/validation").mkdir(parents=True, exist_ok=True)
    with open("data/validation/tuning_results_latest.json", "w", encoding="utf-8") as f:
        json.dump({"results": results, "best": best}, f, indent=2)

    print("=== TUNING RESULTS (sorted by avg MAE) ===")
    for item in results:
        print(f"profile={item['profile']:<12} alpha={item['alpha']:.1f} avg_mae={item['avg_mae']:.3f}")

    print("\n=== BEST CONFIG ===")
    print(json.dumps(best, indent=2))

    # Materialize best config outputs
    pf.CONFIDENCE_WEIGHTS = dict(best["weights"])
    write_forecasts(events, best["alpha"])
    final_report = fv.validate_forecasts(nodes=nodes, output_dir="data/validation")

    print("\n=== FINAL REPORT (BEST CONFIG RE-RUN) ===")
    print(json.dumps(final_report["nodes"], indent=2))


if __name__ == "__main__":
    main()
