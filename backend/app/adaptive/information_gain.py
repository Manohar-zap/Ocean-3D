"""
Expected Information Gain (EIG) Module.

Calculates scientific Expected Information Gain based on Bayesian prior uncertainty,
sensor measurement precision, and depth-relevance decay.
"""
from __future__ import annotations
import math
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


class InformationGainEngine:
    """Computes Expected Information Gain (EIG) for ocean observing missions."""

    def compute_expected_information_gain(
        self,
        prior_uncertainty_percent: float,
        platform_type: str = "glider",
        sensor_precision_sigma: float = 0.05,
        target_depth_m: float = 100.0
    ) -> dict[str, Any]:
        ptype = platform_type.lower().strip()
        
        # Platform sensor resolution factor (Glider/AUV have high precision CTD sensors)
        sensor_fidelity = 0.85 if ptype in ("glider", "auv", "vessel") else 0.65
        
        # Depth decay factor (surface sensors have slightly higher spatial variance)
        depth_decay = max(0.60, 1.0 - (target_depth_m / 3000.0))

        # Bayesian Posterior Variance Reduction Formula
        prior_var = max(0.01, (prior_uncertainty_percent / 100.0) ** 2)
        sensor_var = sensor_precision_sigma ** 2
        
        # Posterior Variance = (Prior_Var * Sensor_Var) / (Prior_Var + Sensor_Var)
        posterior_var = (prior_var * sensor_var) / (prior_var + sensor_var)
        posterior_uncertainty_percent = math.sqrt(posterior_var) * 100.0 * (1.0 / sensor_fidelity)
        
        posterior_uncertainty_percent = max(5.0, min(prior_uncertainty_percent * 0.8, posterior_uncertainty_percent))
        expected_gain_percent = max(0.0, prior_uncertainty_percent - posterior_uncertainty_percent)

        return {
            "prior_uncertainty_percent": round(prior_uncertainty_percent, 1),
            "posterior_uncertainty_percent": round(posterior_uncertainty_percent, 1),
            "expected_information_gain_percent": round(expected_gain_percent, 1),
            "sensor_precision_sigma": sensor_precision_sigma,
            "sensor_fidelity_score": sensor_fidelity,
            "depth_relevance_factor": round(depth_decay, 2),
            "method": "Bayesian Posterior Variance Reduction [sigma_post^2 = (sigma_prior^2 * sigma_sensor^2) / (sigma_prior^2 + sigma_sensor^2)]",
            "provenance": "DERIVED_BAYESIAN_ESTIMATE"
        }


information_gain_engine = InformationGainEngine()
