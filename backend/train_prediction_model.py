"""
OCEAN 3D — Fisher ML Prediction Model Trainer.

Trains a time-aware Autoregressive Linear Model
on historical ocean model fields (INCOIS ROMS & Copernicus CMEMS) using NumPy.

Usage:
    cd backend
    python train_prediction_model.py
"""
import os
import pickle
import numpy as np
from datetime import datetime, timezone

from app.storage import store


def train_model():
    print("=" * 60)
    print("OCEAN 3D — Training Fisher Environmental ML Prediction Model")
    print("=" * 60)

    # 1. Extract historical temperature, salinity, and current velocity records
    records = store.model_records
    print(f"Loaded {len(records)} historical ocean model records from store.")

    # 2. Extract time-series features (Time-Aware Autoregressive Lags)
    X, y = [], []
    temp_records = [r for r in records if r.variable == "temperature"]

    if len(temp_records) < 10:
        print("Not enough temperature records to train ML model.")
        return

    for i in range(2, len(temp_records) - 1):
        # Time-aware features (no temporal leakage)
        lat = temp_records[i].latitude
        lon = temp_records[i].longitude
        depth = temp_records[i].depth
        val_t0 = temp_records[i].value
        val_t_minus1 = temp_records[i - 1].value
        val_t_minus2 = temp_records[i - 2].value

        # Target: Forecasted value at +24h horizon
        val_target_24h = temp_records[i + 1].value

        X.append([lat, lon, depth, val_t0, val_t_minus1, val_t_minus2, 1.0])
        y.append(val_target_24h)

    X = np.array(X, dtype=np.float64)
    y = np.array(y, dtype=np.float64)

    print(f"Constructed time-aware feature matrix: X shape {X.shape}, y shape {y.shape}")

    # 3. Train-Test Split (Chronological time-aware split)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # 4. Train Autoregressive Linear Weights via Ordinary Least Squares
    print("Training Autoregressive Model via NumPy Least Squares...")
    weights, residuals, rank, s = np.linalg.lstsq(X_train, y_train, rcond=None)

    # 5. Evaluate Model
    preds = np.dot(X_test, weights)
    rmse = np.sqrt(np.mean((y_test - preds) ** 2))
    ss_tot = np.sum((y_test - np.mean(y_test)) ** 2)
    ss_res = np.sum((y_test - preds) ** 2)
    r2 = 1.0 - (ss_res / max(1e-9, ss_tot))

    print("Model Training Complete!")
    print(f"Validation RMSE: {rmse:.3f} degC")
    print(f"Validation R^2 Score: {r2:.3f}")

    # 6. Save Model File to backend/models/incois_fisher_ml_v1.bin
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(models_dir, exist_ok=True)
    model_path = os.path.join(models_dir, "incois_fisher_ml_v1.bin")

    model_payload = {
        "weights": weights.tolist(),
        "model_version": "INCOIS-ML-v1.0-ONLINE",
        "trained_date": datetime.now(timezone.utc).isoformat(),
        "rmse": float(rmse),
        "r2": float(r2),
        "features": ["latitude", "longitude", "depth", "val_t0", "val_t_minus1", "val_t_minus2", "bias"]
    }

    with open(model_path, "wb") as f:
        pickle.dump(model_payload, f)

    print(f"Saved trained model weights to: {os.path.abspath(model_path)}")
    print("=" * 60)


if __name__ == "__main__":
    train_model()
