"""
Canonical internal data model (SRS Sec. 7/8, Architecture Sec. 10).

Every adapter — regardless of source format — normalizes into StandardRecord.
Nothing downstream (storage, query, comparison, rendering) ever sees a
source-specific shape again. This is what makes FR-038-040 (add a new
source/variable/instrument without touching core layers) possible.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal


RecordKind = Literal["model", "observation"]


class StandardRecord(BaseModel):
    """The single normalized record shape every adapter must produce."""
    kind: RecordKind
    dataset_id: str
    variable: str
    latitude: float
    longitude: float
    depth: float                 # meters, positive down
    time: str                    # ISO 8601
    value: float
    unit: str
    source_model: Optional[str] = None      # for kind == "model"
    platform_id: Optional[str] = None       # for kind == "observation"
    platform_type: Optional[str] = None     # argo | glider | ctd | bgc
    quality_flag: Optional[str] = "good"
    source_file: Optional[str] = None
    ingestion_ts: Optional[str] = None


class DatasetMeta(BaseModel):
    dataset_id: str
    label: str
    variable_list: list[str]
    units: dict[str, str]
    valid_range: dict[str, list[float]]
    provenance: str
    source_url: Optional[str] = None
    last_updated: Optional[str] = None
    kind: RecordKind


class QueryFilters(BaseModel):
    dataset_id: Optional[str] = None
    variable: Optional[str] = None
    platform_type: Optional[str] = None
    min_lat: float = -90
    max_lat: float = 90
    min_lon: float = -180
    max_lon: float = 180
    min_depth: float = 0
    max_depth: float = 6000
    time: Optional[str] = None       # nearest time step for model grids
    time_start: Optional[str] = None
    time_end: Optional[str] = None


class ComparisonResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    observation_id: str
    observation_value: float
    model_value: float
    difference: float
    unit: str
    match_method: Literal["nearest", "interpolated"]
    time_gap_hours: float
    matched_depth: float
    matched_time: str
