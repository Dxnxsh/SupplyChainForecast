# Design Spec: Event-Driven Decomposed Signal Fusion (EDSF) Forecasting

**Date:** 2026-05-20  
**Author:** Antigravity AI  
**Topic:** Transitioning from Recursive Autoregressive XGBoost to Explainable Decomposed Signal Fusion for Supply Chain Risk Management (SCRM)  

---

## 1. Problem Statement & Critical Model Analysis

The legacy forecasting system utilized a **Recursive Autoregressive (AR) XGBoost Regressor**. While tree-boosting regressors excel at static tabular mapping, empirical testing revealed three fatal architectural flaws when applied to event-driven supply chain anomaly prediction:

1.  **Autoregressive Anomaly Smearing ("Ghost Spikes")**: Supply chain disruptions are sparse, point-in-time anomalies (e.g., a port shutdown). Because the model relies recursively on historical lag features (`risk_lag_1` to `risk_lag_7`), a single massive point-in-time spike (such as risk = 996.91 on May 5) is recursively fed back as yesterday's prediction. This creates a slow, artificial, and long-lasting exponential decay curve (false alarms) that smears risk forward over the entire 14-day horizon.
2.  **Scale Dominance & News Signal Washout**: During gradient boosting optimization, tree splits are made to minimize Mean Squared Error (MSE). Because historical lags are orders of magnitude larger (up to `996.0`) than the forward-looking news-extracted risk features (typically `15.0` to `50.0`), the tree-building splits focus exclusively on lag features. The model essentially learns to ignore the predictive news signals.
3.  **Extrapolation Limits of Decision Trees**: XGBoost cannot predict any value outside the range of its training targets. If a catastrophic future event is predicted by news with a risk score of `500.0`, but the training dataset capped at `200.0`, XGBoost will fail to extrapolate, capping the prediction.

---

## 2. Proposed Architecture: Decomposed Signal Fusion (EDSF)

To solve these limitations, we completely decouple the time-series forecasting problem into a stationary baseline (operational noise) and a forward-looking news signal. 

The forecast risk $\hat{y}_{N}(t)$ for a supplier node $N$ on future target date $t$ is formulated as:

$$\hat{y}_{N}(t) = \text{Baseline}_{N}(t) + \text{NewsSignal}_{N}(t)$$

### A. Systemic Operational Baseline ($\text{Baseline}_{N}(t)$)
The baseline represents the quiet-time operational noise of a node, including weekly and yearly seasonal patterns.
1.  **Outlier Filtering**: We filter out historical anomaly spikes (risk scores above the 90th percentile) from the training set, replacing them with the rolling historical median. This ensures the baseline is not skewed by historic extreme disruptions.
2.  **Prophet Modeling**: We fit a Facebook Prophet model on this filtered continuous series to capture clean weekly seasonality (e.g., lower risk on weekends).
3.  **Fallback**: If a node has highly sparse history (less than 2 events), the baseline falls back to a continuous historical 30-day trimmed rolling median.

### B. Event-Driven News Signal ($\text{NewsSignal}_{N}(t)$)
The news signal is computed purely from forward-looking temporal news extractions that explicitly predict a disruption on a future date. To account for lead-time and temporal uncertainty, we apply a **Gaussian Bell Curve (Temporal Dispersion)**:

$$\text{NewsSignal}_{N}(t) = \sum_{e \in E_{N}} \text{Risk}(e) \times e^{-\frac{(t - \text{Date}(e))^2}{2\sigma^2}}$$

*   $E_{N}$: Set of predictive future news events matching node $N$.
*   $\text{Risk}(e)$: Severity score of event $e$.
*   $\text{Date}(e)$: Predicted calendar date of event $e$.
*   $\sigma$ (Standard Deviation): Set to **1.0 day**. This distributes risk over a 5-day window centered on the event date (100% impact on the event day, ~60% on $\pm 1$ day, and ~13% on $\pm 2$ days).

---

## 3. Compounding News-Sensitive Bounds

To capture both the compounding uncertainty of the forecast horizon and the heightened volatility introduced by active news signals, we define a dynamic prediction margin:

$$\text{margin}(t) = 30.0 + 4.0 \times i + 0.5 \times \text{NewsSignal}(t)$$

$$\text{yhat\_lower}(t) = \max(0.0, \text{yhat}(t) - \text{margin}(t))$$
$$\text{yhat\_upper}(t) = \text{yhat}(t) + \text{margin}(t)$$

*where $i \in [1, 14]$ is the forecast step day.*

*   **Quiet days** ($yhat$ is low) allow the lower bound to touch `0.0`, perfectly covering periods of zero realized risk.
*   **Active event days** cause the bounds to balloon, ensuring the realized peak is completely contained within the shaded interval on the frontend chart.

---

## 4. API & Database Compatibility

To maintain 100% backward compatibility with the React frontend and prevent any disruption to the existing database schema:
*   The API will map:
    *   `yhat` = $\text{Baseline}(t) + \text{NewsSignal}(t)$
    *   `news_contribution` = $\text{NewsSignal}(t)$
    *   `historical_contribution` = $\text{Baseline}(t)$
    *   `method` = `"edsf"`
*   The legacy XGBoost model code will be kept fully intact in the codebase as a code-level reference/fallback, but the active routing in `src/main.py` and `src/forecast_snapshots.py` will point exclusively to the EDSF execution path.

---

## 5. Success Criteria & FYP Defense Strengths
*   **Explainable AI (XAI)**: High transparency. Operators can inspect the exact contribution of the historical baseline vs a specific news article.
*   **MAE Reduction**: Elimination of "ghost spikes" lowers the false-alarm rate, reducing overall MAE.
*   **Spike Anticipation**: The Gaussian bell curve provides clean, early warnings 1-2 days prior to the predicted event date.
