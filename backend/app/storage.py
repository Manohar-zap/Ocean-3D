"""
Data Processing / Storage Layer (Architecture Sec. 5.4, 10).

An in-memory stand-in for PostgreSQL+PostGIS / a time-series store. The
*contract* matters more than the engine: Query Service only ever calls
`query_model()` / `query_observations()` with a bounded filter and gets back
already-reduced rows — never a full scan streamed to the client. Swapping
this module for real Postgres is an implementation detail behind that
contract (Architecture Sec. 3, "each layer independently replaceable").
"""
from __future__ import annotations
from datetime import datetime
from .schemas import StandardRecord, DatasetMeta, QueryFilters
from .adapters import run_ingestion


class Store:
    def __init__(self):
        self.model_records: list[StandardRecord] = []
        self.observation_records: list[StandardRecord] = []
        self.catalog: dict[str, DatasetMeta] = {}
        self._load()

    def _load(self):
        records, raw_meta = run_ingestion()
        for r in records:
            (self.model_records if r.kind == "model" else self.observation_records).append(r)

        # Build the Metadata Catalog (FR-033) from adapter metadata + observed ranges.
        by_dataset: dict[str, list[StandardRecord]] = {}
        for r in records:
            by_dataset.setdefault(r.dataset_id, []).append(r)

        for dataset_id, meta in raw_meta.items():
            if "error" in meta:
                continue
            rows = by_dataset.get(dataset_id, [])
            variables = meta["variables"]
            valid_range = {}
            for v in variables:
                vals = [r.value for r in rows if r.variable == v]
                if vals:
                    valid_range[v] = [round(min(vals), 4), round(max(vals), 4)]
            self.catalog[dataset_id] = DatasetMeta(
                dataset_id=dataset_id,
                label=meta["source_name"],
                variable_list=variables,
                units=meta["units"],
                valid_range=valid_range,
                provenance=meta["source_name"],
                last_updated=datetime.utcnow().isoformat() + "Z",
                kind="model" if rows and rows[0].kind == "model" else "observation",
            )

    # -- Query Service entry points (Architecture Sec. 5.2) -----------------

    def query_model(self, f: QueryFilters) -> list[StandardRecord]:
        rows = self.model_records
        if f.dataset_id:
            rows = [r for r in rows if r.dataset_id == f.dataset_id]
        if f.variable:
            rows = [r for r in rows if r.variable == f.variable]
        rows = [r for r in rows
                if f.min_lat <= r.latitude <= f.max_lat
                and f.min_lon <= r.longitude <= f.max_lon
                and f.min_depth <= r.depth <= f.max_depth]
        if f.time:
            # snap to nearest available time step (grid is discrete)
            times = sorted({r.time for r in rows})
            if times:
                nearest = min(times, key=lambda t: abs(_parse(t) - _parse(f.time)))
                rows = [r for r in rows if r.time == nearest]
        elif f.time_start and f.time_end:
            rows = [r for r in rows if f.time_start <= r.time <= f.time_end]
        return rows

    def query_observations(self, f: QueryFilters) -> list[StandardRecord]:
        rows = self.observation_records
        if f.dataset_id:
            rows = [r for r in rows if r.dataset_id == f.dataset_id]
        if f.variable:
            rows = [r for r in rows if r.variable == f.variable]
        if f.platform_type:
            rows = [r for r in rows if r.platform_type == f.platform_type]
        rows = [r for r in rows
                if f.min_lat <= r.latitude <= f.max_lat
                and f.min_lon <= r.longitude <= f.max_lon
                and f.min_depth <= r.depth <= f.max_depth]
        if f.time_start and f.time_end:
            rows = [r for r in rows if f.time_start <= r.time <= f.time_end]
        return rows

    def observation_profile(self, platform_id: str) -> list[StandardRecord]:
        return [r for r in self.observation_records if r.platform_id == platform_id]

    def find_observation(self, platform_id: str, variable: str, depth: float, time: str) -> StandardRecord | None:
        for r in self.observation_records:
            if (r.platform_id == platform_id and r.variable == variable
                    and abs(r.depth - depth) < 1e-6 and r.time == time):
                return r
        return None


def _parse(t: str) -> datetime:
    return datetime.fromisoformat(t.replace("Z", ""))


# Singleton store, loaded once at process start (Architecture Sec. 6:
# ingestion runs as a background/startup job decoupled from request path).
store = Store()
