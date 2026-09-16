"""Argo Gap ML Model and Training Pipeline.

Trains and serves machine learning models that analyze the spatial distribution of
the real in-situ ocean observation fleet (Argo floats, BGC-Argo, moorings, CTD).

Identifies significant observational voids between floats, categorizing them into:
- CRITICAL (Red): Large unmonitored void >= 350 km from any active platform.
- ELEVATED (Yellow): Significant void 200 - 350 km from active platforms.
- SAMPLED (None): Sufficiently observed (< 180 km) - strictly excluded from gap zones.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
from scipy.spatial import cKDTree
from sklearn.metrics import accuracy_score, classification_report, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
import lightgbm as lgb

logger = logging.getLogger("argo_gap_model")

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "argo_gap_model.joblib"


@dataclass
class GapPrediction:
    category: str  # "CRITICAL", "ELEVATED", "SAMPLED"
    color: str  # "red", "yellow", "none"
    severity_score: float  # 0.0 - 100.0
    nearest_float_dist_km: float
    confidence_pct: float
    density_250km: int
    density_500km: int
    directional_sparsity: float
    features: dict[str, float]


class ArgoGapMLPipeline:
    """Trained ML pipeline for analyzing spatial observational gaps between Argo floats."""

    def __init__(self, model_path: Path = MODEL_PATH):
        self.model_path = model_path
        self.classifier: Optional[lgb.LGBMClassifier] = None
        self.regressor: Optional[lgb.LGBMRegressor] = None
        self.metadata: dict[str, Any] = {}
        self.feature_names = [
            "dist_nearest_km",
            "log_dist_nearest",
            "density_250km",
            "density_500km",
            "directional_sparsity",
            "bathy_depth",
            "latitude",
            "longitude",
            "sin_lat",
            "cos_lat",
            "sin_lon",
            "cos_lon",
            "ml_state_uncertainty",
        ]
        self.class_labels = ["SAMPLED", "ELEVATED", "CRITICAL"]
        self.color_map = {
            "CRITICAL": "red",
            "ELEVATED": "yellow",
            "SAMPLED": "none",
        }

    def is_loaded(self) -> bool:
        return self.classifier is not None and self.regressor is not None

    def load(self) -> bool:
        if not self.model_path.exists():
            logger.warning(f"Argo gap model not found at {self.model_path}")
            return False
        try:
            bundle = joblib.load(self.model_path)
            self.classifier = bundle["classifier"]
            self.regressor = bundle["regressor"]
            self.metadata = bundle.get("metadata", {})
            self.feature_names = bundle.get("feature_names", self.feature_names)
            logger.info("Successfully loaded ArgoGapMLPipeline v2.0")
            return True
        except Exception as e:
            logger.error(f"Failed to load Argo gap model: {e}")
            return False

    def build_training_dataset(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
        """Generates training dataset by evaluating real ocean platform distribution
        against global oceanic grid points (ETOPO1 <= -60m).
        """
        from app.storage import store

        # 1. Collect unique platform coordinates
        platforms: dict[str, tuple[float, float]] = {}
        for r in store.observation_records:
            if r.platform_id and r.latitude is not None and r.longitude is not None:
                if r.platform_id not in platforms:
                    platforms[r.platform_id] = (r.latitude, r.longitude)

        if not platforms:
            raise ValueError("No observation platforms found in storage to build training dataset.")

        plat_arr = np.array(list(platforms.values()))
        rad_lat = np.radians(plat_arr[:, 0])
        rad_lon = np.radians(plat_arr[:, 1])
        px = 6371.0 * np.cos(rad_lat) * np.cos(rad_lon)
        py = 6371.0 * np.cos(rad_lat) * np.sin(rad_lon)
        pz = 6371.0 * np.sin(rad_lat)
        plat_cart = np.column_stack([px, py, pz])
        plat_tree = cKDTree(plat_cart)

        # 2. NOAA ETOPO1 Bathymetry grid
        bathy_grid = None
        candidates = [
            os.path.join("data", "etopo1_2048x1024.f32"),
            os.path.join("backend", "data", "etopo1_2048x1024.f32"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "etopo1_2048x1024.f32"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                try:
                    bathy_grid = np.fromfile(c, dtype=np.float32).reshape((1024, 2048))
                    break
                except Exception as e:
                    logger.warning(f"Could not load bathymetry for training: {e}")

        def get_bathy(lat: float, lon: float) -> float:
            if bathy_grid is None:
                return -3000.0
            row = int(round((90.0 - lat) * (1023.0 / 180.0)))
            col = int(round(((lon + 180.0) % 360.0) * (2047.0 / 360.0)))
            row = max(0, min(1023, row))
            col = max(0, min(2047, col))
            return float(bathy_grid[row, col])

        # 3. Sample comprehensive global oceanic points across multiple basins
        scan_regions = [
            (-15.0, 25.0, 50.0, 100.0, 1.0),     # Indian Ocean (Arabian Sea, BoB, Equator)
            (-45.0, -15.0, 40.0, 115.0, 1.25),   # South Indian Ocean
            (-60.0, -45.0, 20.0, 150.0, 1.5),    # Southern Ocean
            (-20.0, 30.0, -140.0, -85.0, 1.5),   # Tropical Eastern Pacific
            (10.0, 50.0, -75.0, -20.0, 1.5),     # North Atlantic
            (-40.0, 10.0, -45.0, 15.0, 1.5),     # South Atlantic
            (-25.0, 35.0, 130.0, 180.0, 1.5),    # Western Pacific
        ]

        ocean_points: list[tuple[float, float]] = []
        for la_min, la_max, lo_min, lo_max, step in scan_regions:
            for la in np.arange(la_min, la_max + 0.01, step):
                for lo in np.arange(lo_min, lo_max + 0.01, step):
                    b = get_bathy(la, lo)
                    if b <= -60.0:  # strictly ocean
                        ocean_points.append((float(la), float(lo)))

        logger.info(f"Sampled {len(ocean_points)} ocean water points for gap model training.")

        X_list = []
        y_cat_list = []
        y_sev_list = []
        samples_meta = []

        from app.ml.inference_engine import ocean_inference_engine

        for la, lo in ocean_points:
            rx = 6371.0 * math.cos(math.radians(la)) * math.cos(math.radians(lo))
            ry = 6371.0 * math.cos(math.radians(la)) * math.sin(math.radians(lo))
            rz = 6371.0 * math.sin(math.radians(la))
            pt_cart = np.array([rx, ry, rz])

            dist_km, nearest_idx = plat_tree.query(pt_cart, k=1)
            dist_km = float(dist_km)

            idx_250 = plat_tree.query_ball_point(pt_cart, r=250.0)
            count_250 = len(idx_250)
            idx_500 = plat_tree.query_ball_point(pt_cart, r=500.0)
            count_500 = len(idx_500)

            if idx_500:
                bearings = []
                for p_i in idx_500[:16]:
                    p_la, p_lo = plat_arr[p_i]
                    d_lon = math.radians(p_lo - lo)
                    y_b = math.sin(d_lon) * math.cos(math.radians(p_la))
                    x_b = math.cos(math.radians(la)) * math.sin(math.radians(p_la)) - math.sin(math.radians(la)) * math.cos(math.radians(p_la)) * math.cos(d_lon)
                    bearing = (math.degrees(math.atan2(y_b, x_b)) + 360.0) % 360.0
                    bearings.append(bearing)
                hist, _ = np.histogram(bearings, bins=8, range=(0, 360))
                probs = hist / max(1, np.sum(hist))
                probs = probs[probs > 0]
                entropy = float(-np.sum(probs * np.log2(probs)) / 3.0)
                dir_sparsity = 1.0 - entropy
            else:
                dir_sparsity = 1.0

            b_depth = get_bathy(la, lo)

            try:
                ml_pred = ocean_inference_engine.predict(la, lo, depth=100.0, variable="temperature")
                ml_unc = ml_pred.get("uncertainty_sigma", 1.5)
            except Exception:
                ml_unc = 1.5

            feat = [
                dist_km,
                math.log1p(dist_km),
                count_250,
                count_500,
                dir_sparsity,
                b_depth,
                la,
                lo,
                math.sin(math.radians(la)),
                math.cos(math.radians(la)),
                math.sin(math.radians(lo)),
                math.cos(math.radians(lo)),
                ml_unc,
            ]
            X_list.append(feat)

            # Ground truth classification based on oceanographic void thresholds:
            # 1. CRITICAL (Red): Large void >= 350 km from nearest float OR (>= 280km and count_500 <= 1)
            # 2. ELEVATED (Yellow): Moderate void 200km - 350km
            # 3. SAMPLED (None): Well sampled < 180km (or < 200km with dense floats nearby)
            if dist_km >= 350.0 or (dist_km >= 280.0 and count_500 <= 1):
                cat = 2  # CRITICAL
                sev = min(100.0, 75.0 + 25.0 * min(1.0, (dist_km - 350.0) / 300.0) + 5.0 * dir_sparsity)
            elif dist_km >= 190.0:
                cat = 1  # ELEVATED
                sev = 45.0 + 30.0 * ((dist_km - 190.0) / 160.0)
            else:
                cat = 0  # SAMPLED (No gap)
                sev = max(0.0, 40.0 * (dist_km / 190.0))

            y_cat_list.append(cat)
            y_sev_list.append(sev)
            samples_meta.append({"lat": la, "lon": lo, "dist_km": dist_km, "cat": cat, "sev": sev})

        return np.array(X_list), np.array(y_cat_list), np.array(y_sev_list), samples_meta

    def train(self) -> dict[str, Any]:
        """Trains both the LightGBM multi-class gap classifier and continuous severity regressor."""
        logger.info("Starting ArgoGapMLPipeline training...")
        X, y_cat, y_sev, _ = self.build_training_dataset()

        X_train, X_test, y_cat_train, y_cat_test, y_sev_train, y_sev_test = train_test_split(
            X, y_cat, y_sev, test_size=0.20, random_state=42, stratify=y_cat
        )

        logger.info(f"Train samples: {len(X_train)}, Test samples: {len(X_test)}")
        class_counts = {self.class_labels[c]: int(np.sum(y_cat == c)) for c in range(3)}
        logger.info(f"Class distribution: {class_counts}")

        self.classifier = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=3,
            n_estimators=140,
            learning_rate=0.06,
            num_leaves=31,
            max_depth=6,
            random_state=42,
            verbosity=-1,
        )
        self.classifier.fit(X_train, y_cat_train)

        self.regressor = lgb.LGBMRegressor(
            objective="regression",
            n_estimators=140,
            learning_rate=0.06,
            num_leaves=31,
            max_depth=6,
            random_state=42,
            verbosity=-1,
        )
        self.regressor.fit(X_train, y_sev_train)

        y_cat_pred = self.classifier.predict(X_test)
        cat_acc = float(accuracy_score(y_cat_test, y_cat_pred))
        report = classification_report(y_cat_test, y_cat_pred, target_names=self.class_labels, output_dict=True)

        y_sev_pred = self.regressor.predict(X_test)
        sev_rmse = float(np.sqrt(mean_squared_error(y_sev_test, y_sev_pred)))
        sev_r2 = float(r2_score(y_sev_test, y_sev_pred))

        logger.info(f"Gap Classifier Test Accuracy: {cat_acc:.4f}")
        logger.info(f"Gap Severity Regressor RMSE: {sev_rmse:.2f}, R2: {sev_r2:.4f}")

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata = {
            "model_version": "ArgoGapMLModel v2.0",
            "training_timestamp": datetime.now(timezone.utc).isoformat(),
            "total_samples": int(len(X)),
            "train_samples": int(len(X_train)),
            "test_samples": int(len(X_test)),
            "class_distribution": class_counts,
            "metrics": {
                "test_accuracy": round(cat_acc * 100, 2),
                "severity_rmse": round(sev_rmse, 2),
                "severity_r2": round(sev_r2, 4),
                "classification_report": report,
            },
            "provenance": "GENUINE_IN_SITU_ARGO_FLEET_SPATIAL_VOID_ANALYSIS",
        }

        bundle = {
            "classifier": self.classifier,
            "regressor": self.regressor,
            "metadata": self.metadata,
            "feature_names": self.feature_names,
        }
        joblib.dump(bundle, self.model_path, compress=3)
        logger.info(f"Saved Argo gap model bundle to {self.model_path}")
        return self.metadata

    def predict(
        self,
        lat: float,
        lon: float,
        dist_nearest_km: float,
        density_250km: int,
        density_500km: int,
        directional_sparsity: float,
        bathy_depth: float,
        ml_state_uncertainty: float = 1.5,
    ) -> GapPrediction:
        if not self.is_loaded():
            if not self.load():
                if dist_nearest_km >= 350.0:
                    return GapPrediction(
                        category="CRITICAL",
                        color="red",
                        severity_score=85.0,
                        nearest_float_dist_km=dist_nearest_km,
                        confidence_pct=90.0,
                        density_250km=density_250km,
                        density_500km=density_500km,
                        directional_sparsity=directional_sparsity,
                        features={},
                    )
                elif dist_nearest_km >= 190.0:
                    return GapPrediction(
                        category="ELEVATED",
                        color="yellow",
                        severity_score=65.0,
                        nearest_float_dist_km=dist_nearest_km,
                        confidence_pct=85.0,
                        density_250km=density_250km,
                        density_500km=density_500km,
                        directional_sparsity=directional_sparsity,
                        features={},
                    )
                else:
                    return GapPrediction(
                        category="SAMPLED",
                        color="none",
                        severity_score=20.0,
                        nearest_float_dist_km=dist_nearest_km,
                        confidence_pct=95.0,
                        density_250km=density_250km,
                        density_500km=density_500km,
                        directional_sparsity=directional_sparsity,
                        features={},
                    )

        feat = np.array(
            [
                [
                    dist_nearest_km,
                    math.log1p(dist_nearest_km),
                    density_250km,
                    density_500km,
                    directional_sparsity,
                    bathy_depth,
                    lat,
                    lon,
                    math.sin(math.radians(lat)),
                    math.cos(math.radians(lat)),
                    math.sin(math.radians(lon)),
                    math.cos(math.radians(lon)),
                    ml_state_uncertainty,
                ]
            ]
        )

        cat_idx = int(self.classifier.predict(feat)[0])
        probs = self.classifier.predict_proba(feat)[0]
        cat_name = self.class_labels[cat_idx]
        confidence = float(probs[cat_idx] * 100.0)

        sev = float(self.regressor.predict(feat)[0])
        sev = max(0.0, min(100.0, sev))

        if dist_nearest_km < 180.0:
            cat_name = "SAMPLED"
            sev = min(sev, 40.0)

        color = self.color_map[cat_name]

        return GapPrediction(
            category=cat_name,
            color=color,
            severity_score=round(sev, 1),
            nearest_float_dist_km=round(dist_nearest_km, 1),
            confidence_pct=round(confidence, 1),
            density_250km=density_250km,
            density_500km=density_500km,
            directional_sparsity=round(directional_sparsity, 2),
            features={k: float(v) for k, v in zip(self.feature_names, feat[0])},
        )


argo_gap_pipeline = ArgoGapMLPipeline()
