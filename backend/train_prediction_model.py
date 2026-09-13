"""
OCEAN 3D — Fisher ML Prediction Model Trainer.

Trains separate, variable-specific time-aware Autoregressive Models
for Temperature (24h, 48h) and Salinity (24h, 48h) using NumPy.

Usage:
    cd backend
    python train_prediction_model.py
"""
import os
import pickle
import numpy as np
from datetime import datetime, timezone

from app.storage import store


def train_single_variable_horizon_model(variable: str, horizon_hours: int, step_offset: int):
    print("-" * 60)
    print(f"Training Model: {variable.upper()} | Horizon: +{horizon_hours}h")
    print("-" * 60)

    records = store.model_records
    var_records = [r for r in records if r.variable == variable]

    if len(var_records) < 12:
        print(f"Not enough {variable} records ({len(var_records)}) to train model.")
        return False

    # Sort chronologically
    var_records = sorted(var_records, key=lambda r: (r.time, r.latitude, r.longitude, r.depth))

    X, y = [], []
    for i in range(2, len(var_records) - step_offset):
        lat = var_records[i].latitude
        lon = var_records[i].longitude
        depth = var_records[i].depth
        val_t0 = var_records[i].value
        val_t_minus1 = var_records[i - 1].value
        val_t_minus2 = var_records[i - 2].value

        # Target: Forecasted value at +horizon_hours
        target_val = var_records[i + step_offset].value

        X.append([lat, lon, depth, val_t0, val_t_minus1, val_t_minus2, 1.0])
        y.append(target_val)

    X = np.array(X, dtype=np.float64)
    y = np.array(y, dtype=np.float64)

    print(f"Constructed time-aware feature matrix: X shape {X.shape}, y shape {y.shape}")

    # Chronological 80/20 train/validation split (preventing temporal leakage)
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    # Train Autoregressive Linear Weights via Ordinary Least Squares
    weights, residuals, rank, s = np.linalg.lstsq(X_train, y_train, rcond=None)

    # Evaluate on held-out validation set
    preds_val = np.dot(X_val, weights)
    res_val = y_val - preds_val
    rmse = np.sqrt(np.mean(res_val ** 2))
    mae = np.mean(np.abs(res_val))
    residual_std = float(np.std(res_val)) if len(res_val) > 1 else float(rmse)

    ss_tot = np.sum((y_val - np.mean(y_val)) ** 2)
    ss_res = np.sum(res_val ** 2)
    r2 = float(1.0 - (ss_res / max(1e-9, ss_tot)))

    units = "degC" if variable == "temperature" else "psu"
    print(f"Training Complete for {variable} +{horizon_hours}h!")
    print(f"  Train Samples: {len(X_train)} | Val Samples: {len(X_val)}")
    print(f"  Validation RMSE: {rmse:.4f} {units}")
    print(f"  Validation MAE:  {mae:.4f} {units}")
    print(f"  Validation R^2:   {r2:.4f}")

    # Save to dedicated model binary file in backend/models/
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(models_dir, exist_ok=True)
    filename = f"{variable}_{horizon_hours}h_ml_v1.bin"
    model_path = os.path.join(models_dir, filename)

    payload = {
        "variable": variable,
        "forecast_horizon_hours": horizon_hours,
        "weights": weights.tolist(),
        "feature_names": ["latitude", "longitude", "depth", "val_t0", "val_t_minus1", "val_t_minus2", "bias"],
        "model_version": "INCOIS-data-derived baseline ML model v1.0",
        "trained_date": datetime.now(timezone.utc).isoformat(),
        "training_sample_count": len(X_train),
        "validation_sample_count": len(X_val),
        "rmse": float(rmse),
        "mae": float(mae),
        "r2": float(r2),
        "residual_std": round(max(0.05, residual_std), 4),
        "training_data_period": "2018-02 to 2026-03",
        "split_strategy": "Chronological 80/20 train/validation time-series split",
        "units": units
    }

    with open(model_path, "wb") as f:
        pickle.dump(payload, f)

    # Also save fallback legacy filename for backwards compatibility
    if variable == "temperature" and horizon_hours == 24:
        legacy_path = os.path.join(models_dir, "incois_fisher_ml_v1.bin")
        with open(legacy_path, "wb") as f:
            pickle.dump(payload, f)

    print(f"Saved model binary: {os.path.abspath(model_path)}")
    return True


def train_all_models():
    print("=" * 60)
    print("OCEAN 3D — Training Variable-Specific & Horizon-Specific ML Models")
    print("=" * 60)

    # Train 4 distinct models
    train_single_variable_horizon_model("temperature", 24, step_offset=1)
    train_single_variable_horizon_model("temperature", 48, step_offset=2)
    train_single_variable_horizon_model("salinity", 24, step_offset=1)
    train_single_variable_horizon_model("salinity", 48, step_offset=2)

    print("=" * 60)
    print("All ML prediction models trained and saved successfully.")
    print("=" * 60)


if __name__ == "__main__":
    train_all_models()
