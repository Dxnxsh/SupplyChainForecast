# Spec: XGBoost-based Risk Forecasting

## Goal
Replace the current Facebook Prophet time-series model with an XGBoost-based recursive lag model to improve forecast accuracy and resolve the "hit or miss" issues caused by data sparsity.

## Proposed Changes

### 1. Model Architecture
- **Type**: `XGBRegressor`
- **Approach**: Recursive Autoregressive (AR) model.
- **Horizon**: 14 days.
- **Input Features (Lags)**:
    - `risk_t`: Current day risk sum.
    - `risk_t_1` to `risk_t_7`: Risk sums for the previous 7 days.
    - `rolling_avg_7`: 7-day rolling average.
    - `rolling_avg_14`: 14-day rolling average.
    - `event_count_7`: Total number of events in the last 7 days.

### 2. Training Pipeline
- **New Script**: `scripts/train_forecast_model.py`
- **Logic**:
    - Queries the `events` table for all historical daily risk sums per node.
    - Generates the lag features for every available date.
    - Trains a global `XGBRegressor` on all node data (transfer learning across nodes).
    - Saves the model to `models/forecast_xgboost.json`.

### 3. API Integration
- **File**: `src/main.py`
- **Function**: `get_risk_forecast(node_name, as_of: Optional[date])`
- **New Logic**:
    1. Fetch the last 14 days of historical data for the node **up to the `as_of` date** (defaulting to today).
    2. Load the XGBoost model from `models/forecast_xgboost.json`.
    3. Perform recursive prediction:
        - Use the historical window leading up to `as_of` to predict `as_of + 1`.
        - Append predicted `as_of + 1` to the window and use it to predict `as_of + 2`.
        - Repeat until `as_of + 14`.
    4. Return the results in the existing `ForecastPoint` format.

### 4. Data Sparsity Handling
- The model will be trained to understand that `0` risk is the baseline.
- By using `rolling_avg` and `event_count` as features, the model can sustain a "High Risk" forecast even if a specific day has no new articles, as long as the recent window was active.

## Verification Plan

### Automated Tests
- `scripts/verify_forecast_model.py`: Load the model and run a mock prediction for a high-risk node and a low-risk node.
- Ensure the API returns a valid 14-day list.

### Manual Verification
- Compare the new XGBoost forecast curve against the old Prophet curve in the UI (if available).
- Check if nodes with only 1-2 days of data now return a forecast instead of a 404 error.
