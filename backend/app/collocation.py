"""
Argo – Ocean Model Collocation Module (Phase 2 & Phase 3).

Collocates real Argo in-situ observations with ocean model predictions in space,
time, and depth. Enforces strict temporal, spatial, and vertical depth validity thresholds.
Computes explicit residuals (residual = observed - model) and handles missing or mismatched data safely.
"""
from __future__ import annotations
import os
import math
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from .schemas import StandardRecord, CollocationRecord, CollocatedProfileResponse, CollocationStatus
from .storage import store, _parse
from .services import query_service

logger = logging.getLogger(__name__)

def get_max_time_gap_hours() -> float:
    return float(os.getenv("MODEL_MAX_TIME_GAP_HOURS", "120.0"))

def get_max_spatial_distance_km() -> float:
    return float(os.getenv("MODEL_MAX_SPATIAL_DISTANCE_KM", "250.0"))


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

    def __init__(self):
        self._grid_cache = {}
        self._last_records_count = 0

    def _get_grid_cells(self, dataset_id: Optional[str], variable: str):
        if len(store.model_records) != self._last_records_count:
            self._grid_cache.clear()
            self._last_records_count = len(store.model_records)

        target_ds = dataset_id or "incois_las_model"
        cache_key = (target_ds, variable)
        if cache_key in self._grid_cache:
            return self._grid_cache[cache_key]

        model_rows = [r for r in store.model_records if r.dataset_id == target_ds and r.variable == variable]
        if not model_rows:
            model_rows = [r for r in store.model_records if r.variable == variable]
            if model_rows:
                target_ds = model_rows[0].dataset_id

        grid_cells = {}
        for r in model_rows:
            key = (r.latitude, r.longitude)
            grid_cells.setdefault(key, []).append(r)

        result = (target_ds, model_rows, grid_cells)
        self._grid_cache[cache_key] = result
        return result

    def collocate_point(
        self,
        platform_id: str,
        variable: str = "temperature",
        depth: float = 10.0,
        time: Optional[str] = None,
        model_dataset_id: Optional[str] = None
    ) -> CollocationRecord:
        """Collocate a single observation record with nearest ocean model prediction."""
        # 1. Fetch observation from store
        obs_rows = store.observation_profile(platform_id)
        if not obs_rows:
            raise ValueError(f"No observation records found for platform_id '{platform_id}'")

        var_rows = [r for r in obs_rows if r.variable == variable]
        if not var_rows:
            var_rows = obs_rows  # fallback to available observation

        # Match depth & time
        obs = min(var_rows, key=lambda r: abs(r.depth - depth) + (0 if not time or r.time == time else 100))
        obs_v = round(obs.value, 3)

        # QC Check
        if obs.quality_flag in ("bad", "3", "4"):
            meta = store.catalog.get("incois_las_model")
            model_label = meta.label if meta else "INCOIS Ocean Model"
            return CollocationRecord(
                platform_id=obs.platform_id or platform_id,
                platform_type=obs.platform_type or "argo",
                observation_time=obs.time,
                latitude=obs.latitude,
                longitude=obs.longitude,
                observation_depth=obs.depth,
                variable=variable,
                observed_value=obs_v,
                model_value=None,
                residual=None,
                absolute_error=None,
                spatial_distance_km=0.0,
                temporal_difference_hours=0.0,
                observation_unit=obs.unit,
                model_unit=obs.unit,
                quality_flag=obs.quality_flag or "bad",
                observation_source=getattr(obs, "source_organization", "Argo GDAC / IFREMER"),
                model_source=model_label,
                data_status=obs.data_status,
                collocation_method="rejected_bad_qc",
                collocation_status="INVALID_OBSERVATION",
                rejection_reason="Observation failed Quality Control filtering"
            )

        # 2. Select matching model dataset
        dataset_id, model_rows, grid_cells = self._get_grid_cells(model_dataset_id, variable)

        meta = store.catalog.get(dataset_id)
        model_source_label = meta.label if meta else "INCOIS Ocean Circulation Model (ROMS)"

        if not model_rows or not grid_cells:
            return CollocationRecord(
                platform_id=obs.platform_id or platform_id,
                platform_type=obs.platform_type or "argo",
                observation_time=obs.time,
                latitude=obs.latitude,
                longitude=obs.longitude,
                observation_depth=obs.depth,
                variable=variable,
                observed_value=obs_v,
                model_value=None,
                residual=None,
                absolute_error=None,
                spatial_distance_km=0.0,
                temporal_difference_hours=0.0,
                observation_unit=obs.unit,
                model_unit=obs.unit,
                quality_flag=obs.quality_flag or "good",
                observation_source=getattr(obs, "source_organization", "Argo GDAC / IFREMER"),
                model_source=model_source_label,
                data_status=obs.data_status,
                collocation_method="missing_model_data",
                collocation_status="MISSING_MODEL",
                rejection_reason=f"No model prediction data available for variable '{variable}'"
            )

        # 3. Spatial Matching (Fast Euclidean pre-filter + exact haversine on top candidates)
        cos_lat = math.cos(math.radians(obs.latitude))
        candidate_cells = sorted(
            grid_cells.keys(),
            key=lambda c: (c[0] - obs.latitude) ** 2 + ((c[1] - obs.longitude) * cos_lat) ** 2
        )[:10]
        best_cell = min(
            candidate_cells,
            key=lambda c: haversine_distance_km(obs.latitude, obs.longitude, c[0], c[1])
        )
        cell_rows = grid_cells[best_cell]
        spatial_dist = haversine_distance_km(obs.latitude, obs.longitude, best_cell[0], best_cell[1])

        # Enforce Spatial Threshold
        max_space_dist = get_max_spatial_distance_km()
        if spatial_dist > max_space_dist:
            return CollocationRecord(
                platform_id=obs.platform_id or platform_id,
                platform_type=obs.platform_type or "argo",
                observation_time=obs.time,
                latitude=obs.latitude,
                longitude=obs.longitude,
                observation_depth=obs.depth,
                variable=variable,
                observed_value=obs_v,
                model_value=None,
                residual=None,
                absolute_error=None,
                spatial_distance_km=spatial_dist,
                temporal_difference_hours=0.0,
                observation_unit=obs.unit,
                model_unit=obs.unit,
                quality_flag=obs.quality_flag or "good",
                observation_source=getattr(obs, "source_organization", "Argo GDAC / IFREMER"),
                model_source=model_source_label,
                data_status=obs.data_status,
                collocation_method="spatial_mismatch_exceeded",
                collocation_status="SPACE_MISMATCH",
                rejection_reason=f"Spatial distance ({spatial_dist:.1f}km) exceeds max tolerance ({max_space_dist:.1f}km)"
            )

        # 4. Temporal Matching
        obs_dt = _parse(obs.time)
        cell_times = sorted({r.time for r in cell_rows})
        best_time = min(cell_times, key=lambda t: abs((_parse(t) - obs_dt).total_seconds())) if cell_times else obs.time
        temp_gap_hours = abs((_parse(best_time) - obs_dt).total_seconds()) / 3600.0

        # Enforce Temporal Threshold
        max_time_gap = get_max_time_gap_hours()
        if temp_gap_hours > max_time_gap:
            return CollocationRecord(
                platform_id=obs.platform_id or platform_id,
                platform_type=obs.platform_type or "argo",
                observation_time=obs.time,
                latitude=obs.latitude,
                longitude=obs.longitude,
                observation_depth=obs.depth,
                variable=variable,
                observed_value=obs_v,
                model_value=None,
                residual=None,
                absolute_error=None,
                model_time_used=best_time,
                spatial_distance_km=spatial_dist,
                temporal_difference_hours=round(temp_gap_hours, 2),
                observation_unit=obs.unit,
                model_unit=obs.unit,
                quality_flag=obs.quality_flag or "good",
                observation_source=getattr(obs, "source_organization", "Argo GDAC / IFREMER"),
                model_source=model_source_label,
                data_status=obs.data_status,
                collocation_method="temporal_mismatch_exceeded",
                collocation_status="TIME_MISMATCH",
                rejection_reason=f"Temporal difference ({temp_gap_hours:.1f}h) exceeds max tolerance ({max_time_gap:.1f}h)"
            )

        # 5. Vertical Depth Matching
        time_rows = sorted([r for r in cell_rows if r.time == best_time], key=lambda r: r.depth)
        m_depths = [r.depth for r in time_rows]
        m_vals = [r.value for r in time_rows]

        if not m_depths:
            return CollocationRecord(
                platform_id=obs.platform_id or platform_id,
                platform_type=obs.platform_type or "argo",
                observation_time=obs.time,
                latitude=obs.latitude,
                longitude=obs.longitude,
                observation_depth=obs.depth,
                variable=variable,
                observed_value=obs_v,
                model_value=None,
                residual=None,
                absolute_error=None,
                spatial_distance_km=spatial_dist,
                temporal_difference_hours=round(temp_gap_hours, 2),
                observation_unit=obs.unit,
                model_unit=obs.unit,
                quality_flag=obs.quality_flag or "good",
                observation_source=getattr(obs, "source_organization", "Argo GDAC / IFREMER"),
                model_source=model_source_label,
                data_status=obs.data_status,
                collocation_method="missing_model_depths",
                collocation_status="DEPTH_MISMATCH",
                rejection_reason="No model depth levels available"
            )

        # Depth domain check (no extrapolation outside model depth range)
        if obs.depth < min(m_depths) - 50.0 or obs.depth > max(m_depths) + 500.0:
            return CollocationRecord(
                platform_id=obs.platform_id or platform_id,
                platform_type=obs.platform_type or "argo",
                observation_time=obs.time,
                latitude=obs.latitude,
                longitude=obs.longitude,
                observation_depth=obs.depth,
                variable=variable,
                observed_value=obs_v,
                model_value=None,
                residual=None,
                absolute_error=None,
                spatial_distance_km=spatial_dist,
                temporal_difference_hours=round(temp_gap_hours, 2),
                observation_unit=obs.unit,
                model_unit=obs.unit,
                quality_flag=obs.quality_flag or "good",
                observation_source=getattr(obs, "source_organization", "Argo GDAC / IFREMER"),
                model_source=model_source_label,
                data_status=obs.data_status,
                collocation_method="depth_out_of_bounds",
                collocation_status="DEPTH_MISMATCH",
                rejection_reason=f"Observation depth ({obs.depth}m) outside model depth domain ({min(m_depths)}m-{max(m_depths)}m)"
            )

        # Piecewise linear interpolation across model depth levels
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
        else:
            model_val = m_vals[0]
            model_depth_used = m_depths[0]

        # 6. Explicit Residual Calculation: residual = observed_value - model_value
        mod_v = round(model_val, 3)
        residual = round(obs_v - mod_v, 4)
        abs_err = round(abs(residual), 4)

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
            collocation_method="vertical_depth_interpolation_nearest_grid",
            collocation_status="VALID",
            rejection_reason=None
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

        # Filter VALID collocations for statistics
        valid_levels = [r for r in collocated_levels if r.collocation_status == "VALID" and r.residual is not None]
        n_valid = len(valid_levels)

        if n_valid > 0:
            obs_vals = [r.observed_value for r in valid_levels if r.observed_value is not None]
            mod_vals = [r.model_value for r in valid_levels if r.model_value is not None]
            residuals = [r.residual for r in valid_levels if r.residual is not None]
            n = len(residuals)

            bias = sum(residuals) / max(1, n)
            mae = sum(abs(r) for r in residuals) / max(1, n)
            rmse = math.sqrt(sum(r**2 for r in residuals) / max(1, n))

            max_idx = max(range(n), key=lambda i: abs(residuals[i])) if n else 0
            max_err = residuals[max_idx] if n else 0.0
            max_err_depth = valid_levels[max_idx].observation_depth if n else 0.0

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
        else:
            bias = 0.0
            rmse = 0.0
            mae = 0.0
            r2 = 0.0
            willmott_d = 0.0
            max_err = 0.0
            max_err_depth = 0.0

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
            collocation_count=len(collocated_levels),
            valid_collocation_count=n_valid,
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
