"""
Error Analysis & Depth-Bin Error Profiling Module (Phase 3).

Filters valid collocations, tracks rejection statistics, and computes robust error statistics
(bias, RMSE, MAE, median absolute error, standard deviation) across depth bins.
"""
from __future__ import annotations
import math
import logging
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Any

from .schemas import CollocationRecord, DepthBinStats, ErrorDatasetSummary
from .storage import store
from .collocation import collocation_engine

logger = logging.getLogger(__name__)

DEPTH_BINS = [
    ("0-10 m", 0.0, 10.0),
    ("10-50 m", 10.0, 50.0),
    ("50-100 m", 50.0, 100.0),
    ("100-200 m", 100.0, 200.0),
    ("200-500 m", 200.0, 500.0),
    ("500-1000 m", 500.0, 1000.0),
    ("1000-2000 m", 1000.0, 2000.0),
    ("2000+ m", 2000.0, 12000.0)
]


class ErrorAnalysisEngine:
    """Error Statistics & Depth-Bin Profiling Engine."""

    def build_clean_error_dataset(
        self, variable: str = "temperature", dataset_id: Optional[str] = None
    ) -> tuple[list[CollocationRecord], ErrorDatasetSummary]:
        """Scans observation platforms, performs valid collocations, and produces error dataset summary."""
        all_obs = store.observation_records
        var_obs = [r for r in all_obs if r.variable == variable]

        total_obs = len(var_obs)
        valid_records: list[CollocationRecord] = []

        time_rejected = 0
        space_rejected = 0
        depth_rejected = 0
        missing_model_rejected = 0

        # Unique platforms
        platforms = sorted({r.platform_id for r in var_obs if r.platform_id})

        for pid in platforms:
            try:
                prof_resp = collocation_engine.collocate_profile(pid, variable, dataset_id)
                for level in prof_resp.levels:
                    if level.collocation_status == "VALID" and level.residual is not None:
                        valid_records.append(level)
                    elif level.collocation_status == "TIME_MISMATCH":
                        time_rejected += 1
                    elif level.collocation_status == "SPACE_MISMATCH":
                        space_rejected += 1
                    elif level.collocation_status == "DEPTH_MISMATCH":
                        depth_rejected += 1
                    elif level.collocation_status == "MISSING_MODEL":
                        missing_model_rejected += 1
            except Exception:
                pass

        valid_count = len(valid_records)

        if valid_count > 0:
            residuals = [r.residual for r in valid_records if r.residual is not None]
            abs_errs = [r.absolute_error for r in valid_records if r.absolute_error is not None]

            bias = float(np.mean(residuals))
            mae = float(np.mean(abs_errs))
            rmse = float(np.sqrt(np.mean(np.square(residuals))))
            median_abs_err = float(np.median(abs_errs))
            std_dev = float(np.std(residuals))
        else:
            bias, mae, rmse, median_abs_err, std_dev = 0.0, 0.0, 0.0, 0.0, 0.0

        depth_bins = self.compute_depth_bin_profiles(valid_records)

        summary = ErrorDatasetSummary(
            total_observations=total_obs,
            valid_collocations=valid_count,
            time_rejected=time_rejected,
            space_rejected=space_rejected,
            depth_rejected=depth_rejected,
            missing_model_rejected=missing_model_rejected,
            overall_bias=round(bias, 4),
            overall_rmse=round(rmse, 4),
            overall_mae=round(mae, 4),
            median_absolute_error=round(median_abs_err, 4),
            standard_deviation=round(std_dev, 4),
            depth_bins=depth_bins
        )

        return valid_records, summary

    def compute_depth_bin_profiles(
        self, valid_records: list[CollocationRecord]
    ) -> list[DepthBinStats]:
        """Compute depth-stratified error statistics across standard depth bins."""
        bin_stats: list[DepthBinStats] = []

        for b_name, d_min, d_max in DEPTH_BINS:
            bin_recs = [
                r for r in valid_records
                if d_min <= r.observation_depth < d_max and r.residual is not None
            ]
            n = len(bin_recs)
            if n > 0:
                residuals = [r.residual for r in bin_recs if r.residual is not None]
                abs_errs = [r.absolute_error for r in bin_recs if r.absolute_error is not None]

                bias = float(np.mean(residuals))
                mae = float(np.mean(abs_errs))
                rmse = float(np.sqrt(np.mean(np.square(residuals))))
                median_abs_err = float(np.median(abs_errs))
                std_dev = float(np.std(residuals))

                bin_stats.append(DepthBinStats(
                    bin_name=b_name,
                    depth_min=d_min,
                    depth_max=d_max,
                    sample_count=n,
                    bias=round(bias, 4),
                    rmse=round(rmse, 4),
                    mae=round(mae, 4),
                    median_absolute_error=round(median_abs_err, 4),
                    standard_deviation=round(std_dev, 4)
                ))

        return bin_stats


error_analysis_engine = ErrorAnalysisEngine()
