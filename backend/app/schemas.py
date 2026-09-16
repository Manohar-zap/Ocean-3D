"""
Canonical internal data model (SRS Sec. 7/8, Architecture Sec. 10).

Every adapter — regardless of source format — normalizes into StandardRecord.
Nothing downstream (storage, query, comparison, rendering) ever sees a
source-specific shape again. This is what makes FR-038-040 (add a new
source/variable/instrument without touching core layers) possible.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal, Any, Union, List


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
    quality_flag: Optional[str] = "unknown"
    quality_reason: Optional[str] = None
    qc_summary: Optional[dict[str, Any]] = None
    geolocation_argoqc: Optional[int] = None
    timestamp_argoqc: Optional[int] = None
    source_file: Optional[str] = None
    ingestion_ts: Optional[str] = None
    data_status: Literal["OPERATIONAL REAL-TIME", "OPERATIONAL DATA", "REAL DATA", "CACHED REAL DATA", "DEMONSTRATION DATA"] = "OPERATIONAL REAL-TIME"
    source_organization: Optional[str] = "INCOIS / Copernicus Marine"
    product_id: Optional[str] = None
    retrieval_timestamp: Optional[str] = None


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
    data_status: Literal["OPERATIONAL REAL-TIME", "OPERATIONAL DATA", "REAL DATA", "CACHED REAL DATA", "DEMONSTRATION DATA"] = "OPERATIONAL REAL-TIME"
    source_organization: Optional[str] = "INCOIS / Copernicus Marine"
    product_id: Optional[str] = None
    retrieval_timestamp: Optional[str] = None


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


# ---------------------------------------------------------------------------
# Fisher Intelligence & Fisheries Analytics Schemas (Steps 4-8)
# ---------------------------------------------------------------------------

ProvenanceType = Literal["OBSERVED", "MODELED", "DERIVED", "PREDICTED"]


class FisherOutputMetadata(BaseModel):
    value: Union[float, str]
    unit: str
    timestamp: str
    source: str
    method: str
    confidence: float                   # 0.0 to 1.0 confidence score
    provenance: ProvenanceType
    status: Literal["OK", "UNAVAILABLE", "LOW_CONFIDENCE", "ERROR"] = "OK"


class FisherFeatureVector(BaseModel):
    latitude: float
    longitude: float
    depth: float
    time: str
    temperature: Optional[float] = None          # degC
    salinity: Optional[float] = None             # psu
    chlorophyll: Optional[float] = None          # mg/m3
    oxygen: Optional[float] = None               # umol/kg
    current_speed: Optional[float] = None        # m/s
    current_direction: Optional[float] = None    # degrees (0-360)
    bathymetry: Optional[float] = None           # meters depth
    temp_gradient: Optional[float] = None        # degC / km
    upwelling_index: Optional[float] = None      # 0.0 - 1.0
    ssta_anomaly: Optional[float] = None         # degC anomaly from mean


class HabitatSuitabilityResponse(BaseModel):
    species: str
    species_name: str
    latitude: float
    longitude: float
    depth: float
    time: str
    suitability_score: float             # 0 - 100
    confidence: float                   # 0.0 - 1.0
    provenance: ProvenanceType = "DERIVED"
    contributing_variables: dict[str, float]
    method: str
    status: str = "OK"


class FishingOpportunityZone(BaseModel):
    zone_id: str
    label: str
    center_lat: float
    center_lon: float
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    opportunity_score: float             # 0 - 100 Environmental Fishing Opportunity Index
    risk_score: float                    # 0 - 100
    confidence: float                    # 0.0 - 1.0
    provenance: ProvenanceType = "DERIVED"
    index_label: str = "Environmental Fishing Opportunity Index"
    opportunity_level: Literal["HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA"]
    contributing_variables: dict[str, float]
    why_this_area: list[str]
    method: str


class FisherEvent(BaseModel):
    event_id: str
    event_type: Literal[
        "temperature_anomaly",
        "marine_heatwave",
        "strong_current",
        "upwelling_indicator",
        "front_gradient_indicator",
        "eddy_indicator",
        "low_oxygen_condition",
        "rapid_environmental_change"
    ]
    title: str
    latitude: float
    longitude: float
    start_time: str
    detected_time: str
    severity: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    affected_area_km2: float
    affected_variables: list[str]
    detection_method: str
    confidence: float
    provenance: ProvenanceType = "DERIVED"


class FisherRiskAssessment(BaseModel):
    location: str
    latitude: float
    longitude: float
    environmental_risk_score: float       # 0 - 100
    navigational_risk_score: float        # 0 - 100
    prediction_uncertainty: float         # 0.0 - 1.0
    risk_level: Literal["SAFE", "CAUTION", "DANGER"]
    environmental_warnings: list[str]
    provenance: ProvenanceType = "DERIVED"


class FisherPredictionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    latitude: float
    longitude: float
    depth: float
    variable: str
    forecast_horizon_hours: int
    prediction_value: Optional[float] = None
    unit: str
    confidence: float = 0.0
    uncertainty_range: Optional[list[float]] = None
    provenance: ProvenanceType = "PREDICTED"
    model_version: str = "INCOIS-ML-v1.0-OFFLINE"
    training_data_period: str = "2018-02 to 2026-03"
    timestamp: str
    status: Literal["UNAVAILABLE", "OK", "ERROR", "INSUFFICIENT_DATA", "PHYSICAL_BOUND_ADJUSTED"] = "UNAVAILABLE"
    message: str = "Prediction model not connected (ML Inference Engine Offline)"


class FisherIntelligenceSummary(BaseModel):
    location_name: str
    latitude: float
    longitude: float
    depth: float
    time: str
    current_conditions: dict[str, Any]
    prediction: FisherPredictionResponse
    habitat_suitability: HabitatSuitabilityResponse
    opportunity: FishingOpportunityZone
    risk: FisherRiskAssessment
    events: list[FisherEvent]
    confidence_overall: float
    why_this_area: list[str]


# ---------------------------------------------------------------------------
# Phase 2: Argo – Ocean Model Collocation Schemas
# ---------------------------------------------------------------------------

CollocationStatus = Literal[
    "VALID",
    "TIME_MISMATCH",
    "SPACE_MISMATCH",
    "DEPTH_MISMATCH",
    "MISSING_MODEL",
    "INVALID_OBSERVATION",
    "OUT_OF_MODEL_DOMAIN",
    "INSUFFICIENT_DATA"
]


class CollocationRecord(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    platform_id: str
    platform_type: str
    observation_time: str
    latitude: float
    longitude: float
    observation_depth: float
    variable: str
    observed_value: Optional[float] = None
    model_value: Optional[float] = None
    residual: Optional[float] = None             # Explicit: residual = observed_value - model_value
    absolute_error: Optional[float] = None       # abs(residual)
    model_time_used: Optional[str] = None
    model_depth_used: Optional[float] = None
    spatial_distance_km: float                   # Horizontal distance in km
    temporal_difference_hours: float             # Time difference in hours
    observation_unit: str
    model_unit: str
    quality_flag: str
    observation_source: str
    model_source: str
    data_status: str
    collocation_method: str
    collocation_status: CollocationStatus = "VALID"
    rejection_reason: Optional[str] = None


class CollocatedProfileResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    platform_id: str
    platform_type: str
    variable: str
    unit: str
    latitude: float
    longitude: float
    observation_time: str
    model_dataset_id: str
    model_source_name: str
    matched_grid_cell: dict[str, Any]
    collocation_count: int
    valid_collocation_count: int = 0
    levels: list[CollocationRecord]
    metrics: dict[str, float]


class DepthBinStats(BaseModel):
    bin_name: str                               # e.g. "0-10 m"
    depth_min: float
    depth_max: float
    sample_count: int
    bias: float
    rmse: float
    mae: float
    median_absolute_error: float
    standard_deviation: float


class ErrorDatasetSummary(BaseModel):
    total_observations: int
    valid_collocations: int
    time_rejected: int
    space_rejected: int
    depth_rejected: int
    missing_model_rejected: int
    overall_bias: float
    overall_rmse: float
    overall_mae: float
    median_absolute_error: float
    standard_deviation: float
    depth_bins: list[DepthBinStats]


class UncertaintyPointResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    latitude: float
    longitude: float
    depth: float
    variable: str
    time: str
    observed_value: Optional[float] = None
    model_value: Optional[float] = None
    residual: Optional[float] = None
    predicted_residual: Optional[float] = None
    uncertainty: float                          # Standard deviation / 1-sigma uncertainty
    lower_bound: Optional[float] = None         # 95% confidence lower bound
    upper_bound: Optional[float] = None         # 95% confidence upper bound
    confidence_level: float = 0.95
    sample_count: int
    collocation_status: CollocationStatus
    status: Literal["VALID", "INSUFFICIENT_DATA", "ERROR"] = "VALID"
    observation_source: str
    model_source: str
    training_sample_count: int
    training_data_status: str
    model_training_version: str = "INCOIS-UNCERTAINTY-v1.0"
    message: Optional[str] = None


class UncertaintyProfileLevel(BaseModel):
    depth: float
    observed: Optional[float] = None
    model: Optional[float] = None
    residual: Optional[float] = None
    predicted_residual: Optional[float] = None
    uncertainty: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    collocation_status: CollocationStatus = "VALID"


class UncertaintyProfileResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    platform_id: str
    platform_type: str
    variable: str
    unit: str
    latitude: float
    longitude: float
    time: str
    model_dataset_id: str
    sample_count: int
    overall_rmse: float
    overall_bias: float
    confidence_level: float = 0.95
    levels: list[UncertaintyProfileLevel]
    depth_bin_profiles: list[DepthBinStats]
    status: Literal["VALID", "INSUFFICIENT_DATA", "ERROR"] = "VALID"
    observation_source: str
    model_source: str
    model_training_version: str = "INCOIS-UNCERTAINTY-v1.0"
