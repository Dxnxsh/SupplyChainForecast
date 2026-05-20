# XGBoost Risk Forecasting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Facebook Prophet with a recursive XGBoost model to improve forecast reliability and resolve data sparsity issues.

**Architecture:** Recursive Autoregressive (AR) model using `XGBRegressor`. Features include historical risk lags, rolling averages, and event density.

**Tech Stack:** Python, XGBoost, Pandas, SQLAlchemy, FastAPI.

---

### Task 1: Training Pipeline and Feature Engineering

**Files:**
- Create: `scripts/train_forecast_model.py`
- Test: `scratch/test_training_data.py`

- [ ] **Step 1: Write data extraction and feature engineering script**
Create `scripts/train_forecast_model.py` with logic to:
1. Query `events` table for daily `SUM(risk_score)` and `COUNT(*)` per node.
2. Generate lag features (`risk_t-1` to `risk_t-7`).
3. Generate rolling averages (7d, 14d).
4. Train an `XGBRegressor`.
5. Save to `models/forecast_xgboost.json`.

```python
import pandas as pd
import xgboost as xgb
from sqlalchemy import text
import json
import os

def create_features(df):
    df = df.sort_values(['node_name', 'ds'])
    # Lags
    for i in range(1, 8):
        df[f'risk_lag_{i}'] = df.groupby('node_name')['y'].shift(i)
    # Rolling averages
    df['rolling_avg_7'] = df.groupby('node_name')['y'].transform(lambda x: x.rolling(7).mean())
    df['rolling_avg_14'] = df.groupby('node_name')['y'].transform(lambda x: x.rolling(14).mean())
    # Event density
    df['event_count_7'] = df.groupby('node_name')['event_count'].transform(lambda x: x.rolling(7).sum())
    return df.dropna()

# ... Training logic ...
```

- [ ] **Step 2: Run training and verify model file**
Run: `venv311/bin/python scripts/train_forecast_model.py`
Expected: `models/forecast_xgboost.json` is created and contains the model.

- [ ] **Step 3: Commit**
```bash
git add scripts/train_forecast_model.py
git commit -m "feat: add xgboost forecast training pipeline"
```

---

### Task 2: API Integration (Recursive Lag Model)

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Implement XGBoost prediction logic in `get_risk_forecast`**
Modify `src/main.py` to:
1. Load `XGBRegressor` from `models/forecast_xgboost.json`.
2. Fetch the window of data up to `as_of`.
3. Implement a loop that predicts `t+1`, adds it to features, and predicts `t+2`.

```python
@app.get("/suppliers/{node_name}/forecast")
def get_risk_forecast(node_name: str, as_of: Optional[date] = Depends(_parse_as_of_optional), db: Session = Depends(get_db)):
    # 1. Load model
    model = xgb.XGBRegressor()
    model.load_model("models/forecast_xgboost.json")
    
    # 2. Get history (last 14 days before as_of)
    # ...
    
    # 3. Recursive prediction
    forecast = []
    current_features = get_initial_features(history)
    for i in range(14):
        pred = model.predict(current_features)[0]
        forecast.append({"ds": as_of + timedelta(days=i+1), "yhat": pred})
        current_features = update_features(current_features, pred)
        
    return forecast
```

- [ ] **Step 2: Verify API endpoint with curl**
Run: `curl "http://localhost:8000/suppliers/TSMC_Hsinchu/forecast?as_of=2024-05-15"`
Expected: Valid JSON list of 14 points.

- [ ] **Step 3: Commit**
```bash
git add src/main.py
git commit -m "feat: switch risk forecast to xgboost recursive model"
```

---

### Task 3: Final Verification and Cleanup

**Files:**
- Create: `scratch/verify_forecast_consistency.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify rewind consistency**
Create a script that compares a forecast generated today for "yesterday" vs the actual prediction stored in history.

- [ ] **Step 2: Update documentation**
Update `CLAUDE.md` to mention the new forecast training requirement.

- [ ] **Step 3: Commit**
```bash
git add CLAUDE.md scratch/verify_forecast_consistency.py
git commit -m "docs: update forecast documentation and verification scripts"
```
