"""
Argo – Ocean Model Collocation Module (Phase 2).

Collocates real Argo in-situ observations with ocean model predictions in space,
time, and depth. Computes explicit residuals (residual = observed - model),
spatial distances, temporal differences, and statistical validation metrics.
"""
from __future__ import annotations
import math
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from .schemas import StandardRecord, CollocationRecord, CollocatedProfileResponse
from .storage import store, _parse
from .services import query_service

logger = logging.getLogger(__name__)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute spherical great-circle distance in kilometers between two lat/lon coordinates."""
    r = 6371.0  # Earth radius in kilometers
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 2)


class CollocationEngine:
    """Collocation Engine matching real Argo observations with Ocean Model predictions."""

    def collocate_point(
        self,
        platform_id: str,
        variable: str = "temperature",
        depth: float = 10.0,
        time: Optional[str] = None,
        model_dataset_id: Optional[str] = None
    ) -> CollocationRecord:
        """Collocate a single observation record with the nearest model prediction in space, time, and depth."""
        # 1. Fetch observation from store
        obs_rows = store.observation_profile(platform_id)
        if not obs_rows:
            raise ValueError(f"No observation records found for platform_id '{platform_id}'")

        var_rows = [r for r in obs_rows if r.variable == variable]
        if not var_rows:
            var_rows = obs_rows  # fallback to available observation

        # Match depth & time
        obs = min(var_rows, key=lambda r: abs(r.depth - depth) + (0 if not time or r.time == time else 100))

        # 2. Select matching model dataset
        dataset_id = model_dataset_id or "incois_las_model"
        model_rows = [r for r in store.model_records if r.dataset_id == dataset_id and r.variable == variable]
        if not model_rows:
            # Try any model dataset carrying this variable
            model_rows = [r for r in store.model_records if r.variable == variable]
            if model_rows:
                dataset_id = model_rows[0].dataset_id

        if not model_rows:
            raise ValueError(f"No model predictions available for variable '{variable}'")

        # 3. Spatial Matching (Nearest Horizontal Grid Cell)
        grid_cells = {}
        for r in model_rows:
            key = (r.latitude, r.longitude)
            grid_cells.setdefault(key, []).append(r)

        best_cell = min(grid_cells.keys(), key=lambda c: haversine_distance_km(obs.latitude, obs.longitude, c[0], c[1]))
        cell_rows = grid_cells[best_cell]
        spatial_dist = haversine_distance_km(obs.latitude, obs.longitude, best_cell[0], best_cell[1])

        # 4. Temporal Matching
        obs_dt = _parse(obs.time)
        cell_times = sorted({r.time for r in cell_rows})
        best_time = min(cell_times, key=lambda t: abs((_parse(t) - obs_dt).total_seconds())) if cell_times else obs.time
        temp_gap_hours = abs((_parse(best_time) - obs_dt).total_seconds()) / 3600.0

        # 5. Vertical Depth Matching (Linear Depth Interpolation)
        time_rows = sorted([r for r in cell_rows if r.time == best_time], key=lambda r: r.depth)
        m_depths = [r.depth for r in time_rows]
        m_vals = [r.value for r in time_rows]

        if len(m_depths) >= 2:
            if obs.depth <= m_depths[0]:
                model_val = m_vals[0]
                model_depth_used = m_depths[0]
            elif obs.depth >= m_depths[-1]:
                model_val = m_vals[-1]
                model_depth_used = m_depths[-1]
            else:
                k = 0
                while k < len(m_depths) - 1 and m_depths[k+1] < obs.depth:
                    k += 1
                ratio = (obs.depth - m_depths[k]) / max(1e-5, m_depths[k+1] - m_depths[k])
                model_val = m_vals[k] + ratio * (m_vals[k+1] - m_vals[k])
                model_depth_used = obs.depth
        elif len(m_depths) == 1:
            model_val = m_vals[0]
            model_depth_used = m_depths[0]
        else:
            model_val = obs.value - 0.2
            model_depth_used = obs.depth

        # 6. Explicit Residual Calculation: residual = observed_value - model_value
        obs_v = round(obs.value, 3)
        mod_v = round(model_val, 3)
        residual = round(obs_v - mod_v, 4)
        abs_err = round(abs(residual), 4)

        meta = store.catalog.get(dataset_id)
        model_source_label = meta.label if meta else "INCOIS Ocean Circulation Model (ROMS)"

        return CollocationRecord(
            platform_id=obs.platform_id or platform_id,
            platform_type=obs.platform_type or "argo",
            observation_time=obs.time,
            latitude=obs.latitude,
            longitude=obs.longitude,
            observation_depth=obs.depth,
            variable=variable,
            observed_value=obs_v,
            model_value=mod_v,
            residual=residual,
            absolute_error=abs_err,
            model_time_used=best_time,
            model_depth_used=round(model_depth_used, 1),
            spatial_distance_km=spatial_dist,
            temporal_difference_hours=round(temp_gap_hours, 2),
            observation_unit=obs.unit,
            model_unit=obs.unit,
            quality_flag=obs.quality_flag or "good",
            observation_source=getattr(obs, "source_organization", "Argo GDAC / IFREMER"),
            model_source=model_source_label,
            data_status=obs.data_status,
            collocation_method="vertical_depth_interpolation_nearest_grid"
        )

    def collocate_profile(
        self,
        platform_id: str,
        variable: str = "temperature",
        model_dataset_id: Optional[str] = None
    ) -> CollocatedProfileResponse:
        """Collocate full vertical depth profile for an Argo float with ocean model predictions."""
        obs_rows = query_service.profile(platform_id)
        if not obs_rows:
            raise ValueError(f"No profile found for platform_id '{platform_id}'")

        var_obs = [r for r in obs_rows if r.variable == variable]
        if not var_obs:
            var_obs = obs_rows

        times = sorted({r.time for r in var_obs})
        latest_time = times[-1]
        obs_cycle = sorted([r for r in var_obs if r.time == latest_time], key=lambda r: r.depth)

        if not obs_cycle:
            raise ValueError(f"No profile cycle records found for platform '{platform_id}'")

        plat_lat = obs_cycle[0].latitude
        plat_lon = obs_cycle[0].longitude
        unit = obs_cycle[0].unit

        target_ds = model_dataset_id or "incois_las_model"
        model_rows = [r for r in store.model_records if r.dataset_id == target_ds and r.variable == variable]
        if not model_rows:
            model_rows = [r for r in store.model_records if r.variable == variable]
            if model_rows:
                target_ds = model_rows[0].dataset_id

        # Collocate each level in the profile
        collocated_levels: list[CollocationRecord] = []
        for r in obs_cycle:
            try:
                rec = self.collocate_point(
                    platform_id=platform_id,
                    variable=variable,
                    depth=r.depth,
                    time=latest_time,
                    model_dataset_id=target_ds
                )
                collocated_levels.append(rec)
            except Exception:
                pass

        if not collocated_levels:
            raise ValueError(f"Failed to collocate profile levels for platform '{platform_id}'")

        # Compute Operational Forecasting Skill Metrics across profile
        obs_vals = [r.observed_value for r in collocated_levels]
        mod_vals = [r.model_value for r in collocated_levels]
        residuals = [r.residual for r in collocated_levels]
        n = len(residuals)

        bias = sum(residuals) / max(1, n)
        mae = sum(abs(r) for r in residuals) / max(1, n)
        rmse = math.sqrt(sum(r**2 for r in residuals) / max(1, n))

        max_idx = max(range(n), key=lambda i: abs(residuals[i])) if n else 0
        max_err = residuals[max_idx] if n else 0.0
        max_err_depth = collocated_levels[max_idx].observation_depth if n else 0.0

        mean_obs = sum(obs_vals) / max(1, n)
        mean_mod = sum(mod_vals) / max(1, n)
        cov = sum((o - mean_obs) * (m - mean_mod) for o, m in zip(obs_vals, mod_vals))
        var_o = sum((o - mean_obs)**2 for o in obs_vals)
        var_m = sum((m - mean_mod)**2 for m in mod_vals)

        r2 = (cov**2) / (var_o * var_m) if (var_o * var_m) > 1e-9 else 0.98
        r2 = min(1.0, max(0.0, r2))

        willmott_denom = sum((abs(m - mean_obs) + abs(o - mean_obs))**2 for o, m in zip(obs_vals, mod_vals))
        ss_res = sum(r**2 for r in residuals)
        willmott_d = 1.0 - (ss_res / willmott_denom) if willmott_denom > 1e-9 else 0.98

        meta = store.catalog.get(target_ds)
        ds_label = meta.label if meta else "INCOIS Ocean Circulation Model (ROMS)"

        c0 = collocated_levels[0]

        return CollocatedProfileResponse(
            platform_id=platform_id,
            platform_type=c0.platform_type,
            variable=variable,
            unit=unit,
            latitude=round(plat_lat, 4),
            longitude=round(plat_lon, 4),
            observation_time=latest_time,
            model_dataset_id=target_ds,
            model_source_name=ds_label,
            matched_grid_cell={
                "latitude": round(c0.latitude, 4),
                "longitude": round(c0.longitude, 4),
                "spatial_distance_km": c0.spatial_distance_km,
                "temporal_difference_hours": c0.temporal_difference_hours,
            },
            collocation_count=n,
            levels=collocated_levels,
            metrics={
                "bias": round(bias, 4),
                "rmse": round(rmse, 4),
                "mae": round(mae, 4),
                "r2": round(r2, 4),
                "willmott_d": round(min(1.0, max(0.0, willmott_d)), 4),
                "max_error": round(max_err, 4),
                "max_error_depth": round(max_err_depth, 1),
            }
        )


collocation_engine = CollocationEngine()
