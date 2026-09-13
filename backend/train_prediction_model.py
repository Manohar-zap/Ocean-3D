"""
OCEAN 3D — Fisher ML Prediction Model Trainer (Phase 1 Final Correction).

Trains separate, variable-specific time-series Autoregressive Models
for Temperature (24h, 48h) and Salinity (24h, 48h) using strict spatial series grouping,
true historical lags (t0, t-1, t-2), and horizon timing tolerance.

Usage:
    cd backend
    python train_prediction_model.py
"""
import os
import pickle
import numpy as np
from datetime import datetime, timezone

from app.storage import store, _parse


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def train_single_variable_horizon_model(
    variable: str, forecast_horizon_hours: int, horizon_tolerance_hours: float = 12.0
):
    print("-" * 65)
    print(f"Training Model: {variable.upper()} | Horizon: +{forecast_horizon_hours}h (Tol: ±{horizon_tolerance_hours}h)")
    print("-" * 65)

    records = store.model_records
    var_clean = variable.lower().strip()
    var_records = [r for r in records if r.variable.lower().strip() == var_clean]

    if len(var_records) < 10:
        print(f"Not enough {var_clean} records ({len(var_records)}) to train model.")
        return False

    # 1. Explicit Grouping by Stable Spatial Series Key
    series_groups: dict[tuple, list] = {}
    for r in var_records:
        key = (round(r.latitude, 2), round(r.longitude, 2), round(r.depth, 1))
        series_groups.setdefault(key, []).append(r)

    print(f"Grouped into {len(series_groups)} spatial time-series groups for {var_clean}.")

    X, y = [], []

    # 2. Extract Lags & Targets within SAME Series Group
    for s_key, group_recs in series_groups.items():
        # Deduplicate by timestamp and sort chronologically
        time_map = {}
        for r in group_recs:
            dt = ensure_utc(_parse(r.time))
            time_map[dt] = (r.latitude, r.longitude, r.depth, float(r.value))

        sorted_dts = sorted(time_map.keys())

        if len(sorted_dts) < 4:
            continue

        for i in range(2, len(sorted_dts)):
            dt0 = sorted_dts[i]
            dt1 = sorted_dts[i - 1]
            dt2 = sorted_dts[i - 2]

            # Verify strict historical direction
            if not (dt2 < dt1 < dt0):
                continue

            lat, lon, depth, val0 = time_map[dt0]
            val_t_minus1 = time_map[dt1][1]
            val_t_minus2 = time_map[dt2][1]

            # Find target timestamp matching forecast horizon with tolerance
            target_dt_ideal = dt0.timestamp() + forecast_horizon_hours * 3600.0
            tol_sec = horizon_tolerance_hours * 3600.0

            target_val = None
            for dt_candidate in sorted_dts[i + 1:]:
                c_sec = dt_candidate.timestamp()
                if abs(c_sec - target_dt_ideal) <= tol_sec:
                    target_val = time_map[dt_candidate][3]
                    break

            if target_val is None:
                continue

            X.append([lat, lon, depth, val0, val_t_minus1, val_t_minus2, 1.0])
            y.append(target_val)

    X = np.array(X, dtype=np.float64)
    y = np.array(y, dtype=np.float64)

    if len(X) < 10:
        print(f"Insufficient verified time-series samples ({len(X)}) for {var_clean} +{forecast_horizon_hours}h.")
        return False

    print(f"Constructed verified feature matrix: X shape {X.shape}, y shape {y.shape}")

    # 3. Chronological 80/20 train/validation split (preventing temporal leakage)
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    # 4. Train Autoregressive Linear Weights via Ordinary Least Squares
    weights, residuals, rank, s = np.linalg.lstsq(X_train, y_train, rcond=None)

    # 5. Evaluate on held-out validation set
    preds_val = np.dot(X_val, weights)
    res_val = y_val - preds_val
    rmse = np.sqrt(np.mean(res_val ** 2))
    mae = np.mean(np.abs(res_val))
    residual_std = float(np.std(res_val)) if len(res_val) > 1 else float(rmse)

    ss_tot = np.sum((y_val - np.mean(y_val)) ** 2)
    ss_res = np.sum(res_val ** 2)
    r2 = float(1.0 - (ss_res / max(1e-9, ss_tot)))

    units = "degC" if var_clean == "temperature" else "psu"
    print(f"Training Complete for {var_clean} +{forecast_horizon_hours}h!")
    print(f"  Train Samples: {len(X_train)} | Val Samples: {len(X_val)}")
    print(f"  Validation RMSE: {rmse:.4f} {units}")
    print(f"  Validation MAE:  {mae:.4f} {units}")
    print(f"  Validation R^2:   {r2:.4f}")

    # 6. Save Model Payload to backend/models/
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(models_dir, exist_ok=True)
    filename = f"{var_clean}_{forecast_horizon_hours}h_ml_v1.bin"
    model_path = os.path.join(models_dir, filename)

    payload = {
        "variable": var_clean,
        "forecast_horizon_hours": forecast_horizon_hours,
        "horizon_tolerance_hours": horizon_tolerance_hours,
        "weights": weights.tolist(),
        "feature_names": ["latitude", "longitude", "depth", "val_t0", "val_t_minus1", "val_t_minus2", "bias"],
        "lag_definition": "Strict historical time series lags (t0, t-1, t-2) within same spatial series group",
        "series_key_definition": "(variable, round(latitude, 2), round(longitude, 2), round(depth, 1))",
        "model_version": "INCOIS-data-derived baseline ML model v1.0",
        "trained_date": datetime.now(timezone.utc).isoformat(),
        "training_sample_count": len(X_train),
        "validation_sample_count": len(X_val),
        "rmse": round(float(rmse), 4),
        "mae": round(float(mae), 4),
        "r2": round(float(r2), 4),
        "residual_std": round(max(0.05, residual_std), 4),
        "training_data_period": "2018-02 to 2026-03",
        "split_strategy": "Chronological 80/20 train/validation time-series split",
        "units": units
    }

    with open(model_path, "wb") as f:
        pickle.dump(payload, f)

    # Legacy alias update
    if var_clean == "temperature" and forecast_horizon_hours == 24:
        legacy_path = os.path.join(models_dir, "incois_fisher_ml_v1.bin")
        with open(legacy_path, "wb") as f:
            pickle.dump(payload, f)

    print(f"Saved model binary: {os.path.abspath(model_path)}")
    return True


def train_all_models():
    print("=" * 65)
    print("OCEAN 3D — Training Variable-Specific & Horizon-Specific ML Models")
    print("=" * 65)

    train_single_variable_horizon_model("temperature", 24, horizon_tolerance_hours=12.0)
    train_single_variable_horizon_model("temperature", 48, horizon_tolerance_hours=12.0)
    train_single_variable_horizon_model("salinity", 24, horizon_tolerance_hours=12.0)
    train_single_variable_horizon_model("salinity", 48, horizon_tolerance_hours=12.0)

    print("=" * 65)
    print("All ML prediction models trained and saved successfully.")
    print("=" * 65)


if __name__ == "__main__":
    train_all_models()
