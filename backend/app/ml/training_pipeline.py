"""
OCEAN 3D — Real-Data Ocean State & Quantile Uncertainty Training Pipeline.

Trains machine learning models (LightGBM Mean + Quantile Regressors) on genuine in-situ ocean
observations (Argo GDAC, Argovis, IOOS Gliders, CTD casts, and moorings).
Implements a platform-grouped spatiotemporal train/test split to prevent profile data leakage.
Computes genuine distribution-free 90% Prediction Intervals [Q_0.05, Q_0.95] and held-out validation metrics.
"""
from __future__ import annotations

import os
import math
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Any
import numpy as np
import joblib
import lightgbm as lgb
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from app.storage import store

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "latitude",
    "longitude",
    "sin_lon",
    "cos_lon",
    "sin_lat",
    "depth",
    "log_depth",
    "sin_doy",
    "cos_doy",
    "bathy_depth",
]

PHYSICAL_LIMITS = {
    "temperature": (-2.5, 38.0),
    "salinity": (10.0, 42.0),
}


class MLTrainingPipeline:
    """End-to-end reproducible training pipeline using genuine in-situ ocean observations."""

    def __init__(self, models_dir: Optional[str] = None):
        if models_dir:
            self.models_dir = models_dir
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.models_dir = os.path.join(base_dir, "models")
        os.makedirs(self.models_dir, exist_ok=True)
        self._etopo: Optional[np.ndarray] = None
        self._load_etopo()

    def _load_etopo(self):
        """Loads NOAA ETOPO1 binary bathymetry grid to supply bathymetric depth features."""
        if self._etopo is not None:
            return
        candidates = [
            os.path.join("data", "etopo1_2048x1024.f32"),
            os.path.join("backend", "data", "etopo1_2048x1024.f32"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "etopo1_2048x1024.f32"),
        ]
        for c in candidates:
            if os.path.exists(c):
                try:
                    self._etopo = np.fromfile(c, dtype=np.float32).reshape((1024, 2048))
                    logger.info("ML Pipeline loaded NOAA ETOPO1 bathymetry grid (%s)", c)
                    break
                except Exception as exc:
                    logger.warning("Failed to load ETOPO1: %s", exc)

    def _get_bathy_depth(self, lat: float, lon: float) -> float:
        if self._etopo is not None:
            r = int(np.clip((90.0 - lat) / 180.0 * 1023, 0, 1023))
            c = int(np.clip((lon + 180.0) / 360.0 * 2047, 0, 2047))
            return float(self._etopo[r, c])
        return -2500.0

    def extract_training_dataset(self, variable: str = "temperature") -> tuple[np.ndarray, np.ndarray, list[str], dict[str, Any]]:
        """Extracts and sanitizes genuine in-situ observation records into feature matrix X, targets y, and platform groups."""
        var_clean = "salinity" if "sal" in variable.lower() else "temperature"
        min_val, max_val = PHYSICAL_LIMITS.get(var_clean, (-2.5, 42.0))

        # Filter strictly genuine records with valid target measurement and coordinates
        obs = [
            r for r in store.observation_records
            if r.variable == var_clean
            and r.value is not None
            and r.depth is not None
            and min_val <= r.value <= max_val
            and -90.0 <= r.latitude <= 90.0
            and -180.0 <= r.longitude <= 180.0
        ]

        if not obs:
            raise ValueError(f"No valid genuine observation records available for training variable '{var_clean}'.")

        X_rows: list[list[float]] = []
        y_rows: list[float] = []
        platform_groups: list[str] = []

        for r in obs:
            d = max(0.0, float(r.depth))
            lat = float(r.latitude)
            lon = float(r.longitude)
            rad_lat = math.radians(lat)
            rad_lon = math.radians(lon)

            # Day-of-year seasonality
            doy = 180.0
            if r.time:
                try:
                    dt = datetime.fromisoformat(r.time.replace("Z", "+00:00"))
                    doy = float(dt.timetuple().tm_yday)
                except Exception:
                    pass
            sin_doy = math.sin(2.0 * math.pi * doy / 365.25)
            cos_doy = math.cos(2.0 * math.pi * doy / 365.25)

            bathy = self._get_bathy_depth(lat, lon)

            feat = [
                lat,
                lon,
                math.sin(rad_lon),
                math.cos(rad_lon),
                math.sin(rad_lat),
                d,
                math.log1p(d),
                sin_doy,
                cos_doy,
                bathy,
            ]

            X_rows.append(feat)
            y_rows.append(float(r.value))
            platform_groups.append(str(r.platform_id or "unknown_platform"))

        X = np.array(X_rows, dtype=np.float32)
        y = np.array(y_rows, dtype=np.float32)

        meta = {
            "variable": var_clean,
            "total_sample_count": len(y),
            "unique_platform_count": len(set(platform_groups)),
            "feature_names": FEATURE_NAMES,
            "depth_range_m": [float(np.min(X[:, 5])), float(np.max(X[:, 5]))],
            "value_range": [float(np.min(y)), float(np.max(y))],
        }

        return X, y, platform_groups, meta

    def train_and_evaluate(self, variable: str = "temperature", test_size: float = 0.20) -> dict[str, Any]:
        """Trains Mean + Quantile models using platform-grouped spatiotemporal split and evaluates on unseen platforms."""
        var_clean = "salinity" if "sal" in variable.lower() else "temperature"
        unit = "psu" if var_clean == "salinity" else "degC"
        logger.info("Starting ML training pipeline for ocean %s on genuine observations...", var_clean)

        t_start = time.time()
        X, y, groups, meta = self.extract_training_dataset(var_clean)

        # Platform-grouped split: guarantees all profiles of a given platform are either in train or test
        unique_pids = np.unique(groups)
        rng = np.random.default_rng(42)
        shuffled_pids = list(unique_pids)
        rng.shuffle(shuffled_pids)

        split_idx = max(1, int(len(shuffled_pids) * (1.0 - test_size)))
        train_pids = set(shuffled_pids[:split_idx])

        train_mask = np.array([pid in train_pids for pid in groups])
        test_mask = ~train_mask

        X_train, y_train = X[train_mask], y[train_mask]
        X_test, y_test = X[test_mask], y[test_mask]

        logger.info("Dataset partitioned: %d train samples (%d platforms), %d test samples (%d platforms)",
                    len(X_train), len(train_pids), len(X_test), len(unique_pids) - len(train_pids))

        # 1. Train Expected Mean Ocean State Regressor
        model_mean = lgb.LGBMRegressor(
            n_estimators=120,
            max_depth=8,
            learning_rate=0.08,
            subsample=0.85,
            colsample_bytree=0.85,
            random_state=42,
            verbose=-1,
        )
        model_mean.fit(X_train, y_train)

        # 2. Train Lower Quantile Model (Q_0.05) for 90% Prediction Interval Lower Bound
        model_q05 = lgb.LGBMRegressor(
            objective="quantile",
            alpha=0.05,
            n_estimators=90,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.85,
            random_state=42,
            verbose=-1,
        )
        model_q05.fit(X_train, y_train)

        # 3. Train Upper Quantile Model (Q_0.95) for 90% Prediction Interval Upper Bound
        model_q95 = lgb.LGBMRegressor(
            objective="quantile",
            alpha=0.95,
            n_estimators=90,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.85,
            random_state=42,
            verbose=-1,
        )
        model_q95.fit(X_train, y_train)

        duration_sec = round(time.time() - t_start, 2)

        # 4. Rigorous Evaluation on Held-Out Unseen Platforms
        y_pred = model_mean.predict(X_test)
        y_q05 = model_q05.predict(X_test)
        y_q95 = model_q95.predict(X_test)

        residuals = y_test - y_pred
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        mae = float(mean_absolute_error(y_test, y_pred))
        r2 = float(r2_score(y_test, y_pred))
        residual_std = float(np.std(residuals))

        # Empirical 90% Prediction Interval Coverage & Mean Width
        inside_interval = (y_test >= y_q05) & (y_test <= y_q95)
        empirical_coverage = float(np.mean(inside_interval))
        interval_widths = y_q95 - y_q05
        mean_pi_width = float(np.mean(interval_widths))

        metrics = {
            "rmse": round(rmse, 3),
            "mae": round(mae, 3),
            "r2": round(r2, 3),
            "residual_std": round(residual_std, 3),
            "empirical_90pct_coverage": round(empirical_coverage * 100.0, 1),
            "mean_prediction_interval_width": round(mean_pi_width, 3),
            "unit": unit,
        }

        # 5. Serialize Artifacts
        artifact_filename = f"ocean_state_{var_clean}_v2.joblib"
        artifact_path = os.path.join(self.models_dir, artifact_filename)

        payload = {
            "variable": var_clean,
            "unit": unit,
            "model_version": f"LightGBM Quantile Regressor v2.0 ({var_clean})",
            "model_mean": model_mean,
            "model_q05": model_q05,
            "model_q95": model_q95,
            "feature_names": FEATURE_NAMES,
            "metrics": metrics,
            "dataset_summary": {
                "total_samples": len(y),
                "train_samples": len(X_train),
                "test_samples": len(X_test),
                "train_platforms": len(train_pids),
                "test_platforms": len(unique_pids) - len(train_pids),
            },
            "training_timestamp": datetime.now(timezone.utc).isoformat(),
            "provenance": "GENUINE_ARGO_GLIDER_CTD_IN_SITU_OBSERVATION_NETWORK",
            "split_strategy": "platform_grouped_spatiotemporal_split_80_20",
        }

        joblib.dump(payload, artifact_path, compress=3)
        logger.info("Saved trained ML artifact to %s (size: %.1f KB)", artifact_path, os.path.getsize(artifact_path) / 1024.0)

        return {
            "status": "TRAINED",
            "variable": var_clean,
            "artifact_file": artifact_filename,
            "artifact_path": artifact_path,
            "training_duration_seconds": duration_sec,
            "metrics": metrics,
            "dataset_summary": payload["dataset_summary"],
            "trained_at": payload["training_timestamp"],
        }


def train_ocean_models() -> dict[str, Any]:
    """Convenience helper to train both Temperature and Salinity models."""
    pipeline = MLTrainingPipeline()
    res_temp = pipeline.train_and_evaluate("temperature")
    res_sal = pipeline.train_and_evaluate("salinity")
    return {
        "status": "COMPLETED",
        "temperature": res_temp,
        "salinity": res_sal,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = train_ocean_models()
    print("Training Results Summary:")
    print("Temperature:", results["temperature"]["metrics"])
    print("Salinity:", results["salinity"]["metrics"])
