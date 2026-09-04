"""
Query Service, Comparison Service, Export Service (Architecture Sec. 5.2, 9).
"""
from __future__ import annotations
import csv
import io
from datetime import datetime
from .schemas import StandardRecord, QueryFilters, ComparisonResult
from .storage import store, _parse


class QueryService:
    """Single choke point for all filtered reads (FR-034-037)."""

    def model_grid(self, f: QueryFilters) -> list[StandardRecord]:
        return store.query_model(f)

    def observations(self, f: QueryFilters) -> list[StandardRecord]:
        return store.query_observations(f)

    def profile(self, platform_id: str) -> list[StandardRecord]:
        return store.observation_profile(platform_id)

    def available_times(self, dataset_id: str) -> list[str]:
        return sorted({r.time for r in store.model_records if r.dataset_id == dataset_id})


class ComparisonService:
    """Model <-> observation matching and difference (FR-029-032, Sec. 12)."""

    def compare(self, observation_id_parts: dict) -> ComparisonResult:
        platform_id = observation_id_parts["platform_id"]
        variable = observation_id_parts["variable"]
        depth = observation_id_parts["depth"]
        time = observation_id_parts["time"]

        obs = store.find_observation(platform_id, variable, depth, time)
        if obs is None:
            raise ValueError("Observation not found")

        # Find matching model dataset for this variable
        candidate_datasets = {r.dataset_id for r in store.model_records if r.variable == variable}
        if not candidate_datasets:
            raise ValueError(f"No model dataset carries variable '{variable}'")
        dataset_id = sorted(candidate_datasets)[0]

        model_rows = [r for r in store.model_records
                      if r.dataset_id == dataset_id and r.variable == variable]
        if not model_rows:
            raise ValueError("No model data available for comparison")

        # nearest neighbor in space + depth + time
        obs_t = _parse(obs.time)

        def dist(r: StandardRecord) -> float:
            dl = (r.latitude - obs.latitude) ** 2 + (r.longitude - obs.longitude) ** 2
            dd = ((r.depth - obs.depth) / 500.0) ** 2
            dt = ((_parse(r.time) - obs_t).total_seconds() / 86400.0 / 5.0) ** 2
            return dl + dd + dt

        best = min(model_rows, key=dist)
        time_gap_hours = abs((_parse(best.time) - obs_t).total_seconds()) / 3600.0
        exact_depth = abs(best.depth - obs.depth) < 1e-6
        match_method = "nearest" if not exact_depth else "nearest"

        return ComparisonResult(
            observation_id=f"{platform_id}|{variable}|{depth}|{time}",
            observation_value=obs.value,
            model_value=best.value,
            difference=round(obs.value - best.value, 4),
            unit=obs.unit,
            match_method=match_method,
            time_gap_hours=round(time_gap_hours, 2),
            matched_depth=best.depth,
            matched_time=best.time,
        )


class ExportService:
    """Packages a query result into CSV (FR-041-043)."""

    MAX_ROWS = 200_000  # exception flow: selection too large

    def to_csv(self, rows: list[StandardRecord]) -> str:
        if len(rows) > self.MAX_ROWS:
            raise ValueError(f"Selection too large for export ({len(rows)} rows, limit {self.MAX_ROWS}). "
                              f"Narrow the region, depth range, or time range and try again.")
        buf = io.StringIO()
        fieldnames = ["kind", "dataset_id", "variable", "latitude", "longitude", "depth",
                      "time", "value", "unit", "source_model", "platform_id",
                      "platform_type", "quality_flag"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r.model_dump())
        return buf.getvalue()


query_service = QueryService()
comparison_service = ComparisonService()
export_service = ExportService()
