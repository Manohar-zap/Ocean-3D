"""
AI Ocean-State Prediction & Uncertainty Engine (Phase 1 Correction).

Time-Aware Multi-Variable Prediction Pipeline for Ocean Environmental Conditions (Temperature & Salinity).
Loads dedicated variable-specific (+24h, +48h) ML model binaries, extracts shared time-aware lag features,
and derives approximate 95% Prediction Intervals from held-out validation error statistics.
"""
from __future__ import annotations
import os
import pickle
import logging
import math
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Any

from .schemas import FisherPredictionResponse
from .feature_builder import extract_time_aware_features_at

logger = logging.getLogger(__name__)

# Configurable Physical Bounds
PHYSICAL_BOUNDS = {
    "temperature": (-2.0, 38.0),
    "salinity": (5.0, 45.0)
}


class FisherPredictionEngine:
    """Fisher Prediction Engine supporting time-aware environmental forecasting & model-derived uncertainty."""

    def __init__(self):
        self.model_dir = os.path.join(os.path.dirname(__file__), "..", "models")

    def _resolve_model_path(self, variable: str, forecast_horizon_hours: int) -> Optional[str]:
        var_clean = "salinity" if "sal" in variable.lower() else "temperature"
        horizon = 48 if forecast_horizon_hours >= 36 else 24
        
        candidates = [
            os.path.join(self.model_dir, f"{var_clean}_{horizon}h_ml_v1.bin"),
            os.path.join("backend/models", f"{var_clean}_{horizon}h_ml_v1.bin")
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def is_model_available(self, variable: str = "temperature", forecast_horizon_hours: int = 24) -> bool:
        return self._resolve_model_path(variable, forecast_horizon_hours) is not None

    def predict_environment(
        self,
        latitude: float,
        longitude: float,
        depth: float = 0.0,
        variable: str = "temperature",
        forecast_horizon_hours: int = 24,
        time: Optional[str] = None
    ) -> FisherPredictionResponse:
        ts = time or datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        var_clean = "salinity" if "sal" in variable.lower() else "temperature"
        unit = "psu" if var_clean == "salinity" else "degC"

        model_path = self._resolve_model_path(var_clean, forecast_horizon_hours)

        # 1. Check Model File Availability
        if not model_path:
            logger.info(f"No trained ML model weights file found for {var_clean} +{forecast_horizon_hours}h.")
            return FisherPredictionResponse(
                latitude=latitude,
                longitude=longitude,
                depth=depth,
                variable=var_clean,
                forecast_horizon_hours=forecast_horizon_hours,
                prediction_value=None,
                unit=unit,
                confidence=0.0,
                uncertainty_range=None,
                provenance="PREDICTED",
                model_version="INCOIS-data-derived baseline ML model v1.0 (OFFLINE)",
                training_data_period="2018-02 to 2026-03",
                timestamp=ts,
                status="UNAVAILABLE",
                message=f"No trained prediction model found for {var_clean} +{forecast_horizon_hours}h."
            )

        # 2. Extract Shared Time-Aware Features (t0, t-1, t-2)
        feat_res = extract_time_aware_features_at(latitude, longitude, depth, var_clean, time)
        if not feat_res:
            logger.info(f"Insufficient historical time-series lag records for {var_clean} at ({latitude}, {longitude}, {depth}m).")
            return FisherPredictionResponse(
                latitude=latitude,
                longitude=longitude,
                depth=depth,
                variable=var_clean,
                forecast_horizon_hours=forecast_horizon_hours,
                prediction_value=None,
                unit=unit,
                confidence=0.0,
                uncertainty_range=None,
                provenance="PREDICTED",
                model_version="INCOIS-data-derived baseline ML model v1.0",
                training_data_period="2018-02 to 2026-03",
                timestamp=ts,
                status="INSUFFICIENT_DATA",
                message="Insufficient historical time-series lag records to construct prediction feature vector."
            )

        feature_vec, feature_dict = feat_res

        # 3. Load Trained Model Weights & Validation Error Statistics
        try:
            with open(model_path, "rb") as f:
                payload = pickle.load(f)

            weights = payload.get("weights", [])
            val_rmse = float(payload.get("rmse", 0.38))
            val_mae = float(payload.get("mae", 0.28))
            val_r2 = float(payload.get("r2", 0.85))
            val_std = float(payload.get("residual_std", val_rmse))
            model_ver = payload.get("model_version", "INCOIS-data-derived baseline ML model v1.0")

            if not weights or len(weights) != len(feature_vec):
                return FisherPredictionResponse(
                    latitude=latitude, longitude=longitude, depth=depth, variable=var_clean,
                    forecast_horizon_hours=forecast_horizon_hours, prediction_value=None,
                    unit=unit, confidence=0.0, timestamp=ts, status="ERROR",
                    message="Model weight vector dimension mismatch with feature vector."
                )

            # 4. Predict
            raw_pred = float(np.dot(feature_vec, weights))
            min_p, max_p = PHYSICAL_BOUNDS.get(var_clean, (-2.0, 42.0))
            
            is_adjusted = False
            if raw_pred < min_p:
                pred_val = min_p
                is_adjusted = True
            elif raw_pred > max_p:
                pred_val = max_p
                is_adjusted = True
            else:
                pred_val = raw_pred

            # 5. Model-Derived Uncertainty & 95% Prediction Interval (approximate 95% PI: +/- 1.96 * sigma)
            depth_unc_penalty = 0.02 * (depth / 500.0)
            horizon_unc_penalty = 0.04 * (forecast_horizon_hours / 24.0)
            sigma_pred = math.sqrt(val_std ** 2 + depth_unc_penalty ** 2 + horizon_unc_penalty ** 2)

            z_95 = 1.96 * sigma_pred
            lower_bound = round(pred_val - z_95, 2)
            upper_bound = round(pred_val + z_95, 2)

            status_str = "PHYSICAL_BOUND_ADJUSTED" if is_adjusted else "OK"

            return FisherPredictionResponse(
                latitude=latitude,
                longitude=longitude,
                depth=depth,
                variable=var_clean,
                forecast_horizon_hours=forecast_horizon_hours,
                prediction_value=round(pred_val, 2),
                unit=unit,
                confidence=0.95,  # 95% Prediction Interval Coverage Level
                uncertainty_range=[lower_bound, upper_bound],
                provenance="PREDICTED",
                model_version=model_ver,
                training_data_period=payload.get("training_data_period", "2018-02 to 2026-03"),
                timestamp=ts,
                status=status_str,
                message=f"Time-aware autoregressive prediction generated (95% PI: [{lower_bound}, {upper_bound}] {unit}, Val R2: {val_r2:.3f})"
            )
        except Exception as e:
            logger.warning(f"Error executing prediction model: {e}")
            return FisherPredictionResponse(
                latitude=latitude, longitude=longitude, depth=depth, variable=var_clean,
                forecast_horizon_hours=forecast_horizon_hours, prediction_value=None,
                unit=unit, confidence=0.0, timestamp=ts, status="ERROR", message=str(e)
            )


prediction_engine = FisherPredictionEngine()
