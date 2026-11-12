from typing import Optional, Literal, Any, Union
from pydantic import BaseModel, Field

class GlucoseReadingItem(BaseModel):
    glucose: float = Field(..., description="Glucose measurement in mg/dL")
    timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp")

class InsulinEventItem(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 timestamp of insulin administration")
    units: float = Field(..., description="Insulin units (bolus or basal rate)")
    type: Optional[str] = Field("bolus", description="'bolus' or 'basal'")

class BasalEventItem(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 timestamp of basal rate record")
    rate: float = Field(..., description="Basal rate in U/h")

class CarbEventItem(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 timestamp of carbohydrate intake")
    carbs: float = Field(..., description="Carbohydrates in grams")

class PredictRequest(BaseModel):
    readings: list[Union[float, GlucoseReadingItem]] = Field(
        ...,
        description="Exactly 24 chronological glucose readings in mg/dL, sampled at 15-minute intervals (6 hours total)."
    )
    latest_timestamp: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp for the 24th (most recent) reading. If omitted, current UTC time is used."
    )
    experiment: Optional[str] = Field(
        "gp_A",
        description="Model identifier to use: 'gp_A'/'experiment_a', 'gp_B'/'experiment_b', or 'e1_gpformer'."
    )
    model_id: Optional[str] = Field(
        None,
        description="Alternative alias for 'experiment' (e.g. 'e1_gpformer')."
    )
    insulin_events: Optional[list[Union[dict, InsulinEventItem]]] = Field(
        default=None,
        description="Alias for bolus_events (backward compatibility). None = channel not available."
    )
    bolus_events: Optional[list[Union[dict, InsulinEventItem]]] = Field(
        default=None,
        description="Bolus insulin events. None = not available, [] = available with no events."
    )
    basal_events: Optional[list[Union[dict, BasalEventItem]]] = Field(
        default=None,
        description="Basal rate records. None = not available."
    )
    carb_events: Optional[list[Union[dict, CarbEventItem]]] = Field(
        default=None,
        description="Carbohydrate events. None = not available, [] = available with no events."
    )

class ForecastV1Request(BaseModel):
    model_id: Optional[str] = Field("e1_gpformer", description="'e1_gpformer', 'experiment_a', or 'experiment_b'")
    readings: list[Union[float, GlucoseReadingItem]] = Field(
        ...,
        description="24 chronological glucose readings, either as numbers or objects with glucose and timestamp."
    )
    latest_timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp for the 24th reading")
    # Backward-compat alias: insulin_events treated as bolus_events
    insulin_events: Optional[list[Union[dict, InsulinEventItem]]] = Field(
        default=None,
        description="Alias for bolus_events (backward compatibility). None = channel not available."
    )
    bolus_events: Optional[list[Union[dict, InsulinEventItem]]] = Field(
        default=None,
        description="Bolus insulin events. None = not available, [] = available with no events."
    )
    basal_events: Optional[list[Union[dict, BasalEventItem]]] = Field(
        default=None,
        description="Basal rate records. None = not available."
    )
    carb_events: Optional[list[Union[dict, CarbEventItem]]] = Field(
        default=None,
        description="Carbohydrate events. None = not available, [] = available with no events."
    )

class QuantileDict(BaseModel):
    q10: float
    q25: float
    q50: float
    q75: float
    q90: float

class UncertaintyBand(BaseModel):
    low_q10: float
    high_q90: float
    bandwidth: float

class RiskProbabilities(BaseModel):
    hypo: float = Field(..., description="Probability of glucose < 70 mg/dL")
    normal: float = Field(..., description="Probability of glucose in 70-180 mg/dL")
    hyper: float = Field(..., description="Probability of glucose > 180 mg/dL")

class ForecastStep(BaseModel):
    step: int = Field(..., description="Step index (1 to 8)")
    horizon_minutes: int = Field(..., description="Forecast horizon in minutes (+15, +30, ..., +120)")
    timestamp: str = Field(..., description="ISO 8601 timestamp for this forecast point")
    glucose_median: float = Field(..., description="Median glucose prediction (50th percentile) in mg/dL")
    quantiles: QuantileDict
    uncertainty_band: UncertaintyBand
    risk_probabilities: RiskProbabilities
    predicted_risk_class: Literal["HYPO", "NORMAL", "HYPER"]
    calibrated_thresholds: Optional[dict[str, float]] = None

class InputSummary(BaseModel):
    count: int = 24
    latest_glucose_mg_dl: float
    latest_timestamp: str
    sampling_interval_minutes: int = 15
    mean_glucose_mg_dl: float
    min_glucose_mg_dl: float
    max_glucose_mg_dl: float

class ClinicalAlert(BaseModel):
    status: Literal["NORMAL", "HYPO_RISK", "HYPER_RISK"]
    message: str
    alert_horizon_minutes: Optional[int] = None

class PredictResponse(BaseModel):
    status: str = "success"
    experiment: str
    experiment_description: str
    mode: Optional[str] = "cgm_only"
    inputs_used: list[str] = Field(default_factory=list, description="List of input channels used")
    units: str = "mg/dL"
    input_summary: InputSummary
    forecast: list[ForecastStep]
    clinical_alert: ClinicalAlert
    model_version: str
    disclaimer: str

class HorizonSummary(BaseModel):
    horizon_minutes: int
    median: float
    p10: float
    p90: float
    risk_class: str
    risk_probabilities: RiskProbabilities

class ForecastV1Response(BaseModel):
    status: str = "success"
    model_id: str
    model_name: str
    mode: str
    units: str = "mg/dL"
    input_summary: InputSummary
    inputs_used: list[str] = Field(default_factory=list, description="List of input channels used (e.g. ['glucose','time','bolus','carbs'])")
    forecast_30m: Optional[float] = None
    forecast_60m: Optional[float] = None
    forecast_90m: Optional[float] = None
    forecast_120m: Optional[float] = None
    forecast: list[ForecastStep]
    horizons_summary: dict[str, HorizonSummary]
    clinical_alert: ClinicalAlert
    model_version: str
    disclaimer: str

class HealthResponse(BaseModel):
    status: str
    api_online: bool
    model_loaded: bool
    current_experiment: str
    available_experiments: list[str]

class ExperimentDetails(BaseModel):
    experiment_id: str
    name: str
    description: str
    checkpoint_available: bool
    normalization_mean: float
    normalization_std: float
    training_sources: list[str]

class ModelInfoResponse(BaseModel):
    active_experiment: str
    input_sequence_length: int
    sampling_interval_minutes: int
    total_history_hours: float
    forecast_horizon_steps: int
    forecast_horizon_minutes: int
    quantiles_output: list[float]
    risk_classes: list[str]
    thresholds: dict[str, float]
    available_experiments: list[ExperimentDetails]

class ModelListItem(BaseModel):
    model_id: str
    name: str
    description: str
    type: str
    training_sources: list[str]
    checkpoint_available: bool
    input_features: list[str]
    supports_multimodal: bool

class ModelsV1Response(BaseModel):
    models: list[ModelListItem]
