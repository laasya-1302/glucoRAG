from typing import Any, Optional
from datetime import datetime
from ..inference import engine as legacy_engine
from .e1_inference import e1_service

MODEL_METADATA = [
    {
        "model_id": "e1_gpformer",
        "name": "E1 Multimodal GPFormer (3-Seed Ensemble)",
        "description": "Multi-horizon GPFormer with 9 input channels (CGM + Insulin + Carbs), 3-seed ensemble (s42, s123, s2026), and calibrated uncertainty intervals.",
        "type": "multimodal_ensemble",
        "training_sources": ["REPLACE-BG", "HuPA", "D1NAMO"],
        "checkpoint_available": True,
        "input_features": ["glucose", "sin_tod", "cos_tod", "bolus", "basal", "carb", "m_bolus", "m_basal", "m_carb"],
        "supports_multimodal": True
    },
    {
        "model_id": "experiment_a",
        "name": "Experiment A (REPLACE-BG)",
        "description": "GPFormer univariate model trained on REPLACE-BG T1D cohort.",
        "type": "univariate_checkpoint",
        "training_sources": ["REPLACE-BG"],
        "checkpoint_available": True,
        "input_features": ["glucose", "time_marks"],
        "supports_multimodal": False
    },
    {
        "model_id": "experiment_b",
        "name": "Experiment B (REPLACE-BG + Shanghai T2D)",
        "description": "GPFormer multi-domain model trained on REPLACE-BG T1D and Shanghai T2D cohorts.",
        "type": "multidomain_checkpoint",
        "training_sources": ["REPLACE-BG", "Shanghai T2D"],
        "checkpoint_available": True,
        "input_features": ["glucose", "time_marks"],
        "supports_multimodal": False
    }
]

def normalize_model_id(model_id: str) -> str:
    m = model_id.strip().lower()
    if m in ("gp_a", "experiment_a", "a"):
        return "experiment_a"
    if m in ("gp_b", "experiment_b", "b"):
        return "experiment_b"
    if m in ("e1_gpformer", "e1", "e1_multimodal"):
        return "e1_gpformer"
    return m

def get_registered_models() -> list[dict[str, Any]]:
    # Dynamic check of checkpoint availability
    models = []
    e1_ready = e1_service.is_ready()
    exp_ready = legacy_engine.is_ready()

    for item in MODEL_METADATA:
        m = dict(item)
        if m["model_id"] == "e1_gpformer":
            m["checkpoint_available"] = e1_ready
        else:
            m["checkpoint_available"] = exp_ready
        models.append(m)
    return models

def is_model_supported(model_id: str) -> bool:
    norm = normalize_model_id(model_id)
    return norm in ("experiment_a", "experiment_b", "e1_gpformer")

def run_model_inference(
    model_id: str,
    readings: list[float],
    latest_dt: datetime,
    bolus_events: Optional[list[dict]] = None,
    basal_events: Optional[list[dict]] = None,
    carb_events: Optional[list[dict]] = None,
    # Backward compat
    insulin_events: Optional[list[dict]] = None,
) -> dict[str, Any]:
    norm_id = normalize_model_id(model_id)

    if norm_id == "e1_gpformer":
        result = e1_service.predict(
            readings=readings,
            latest_dt=latest_dt,
            bolus_events=bolus_events,
            basal_events=basal_events,
            carb_events=carb_events,
            insulin_events=insulin_events,
        )
        return {
            "model_id": "e1_gpformer",
            "model_name": "E1 Multimodal GPFormer (3-Seed Ensemble)",
            "mode": result["mode"],
            "inputs_used": result.get("inputs_used", ["glucose", "time"]),
            "forecast": result["forecast"],
            "clinical_alert": result["clinical_alert"],
            "model_version": result["model_version"],
            "disclaimer": result["disclaimer"]
        }
    elif norm_id == "experiment_a":
        res = legacy_engine.predict(readings, latest_dt, experiment="gp_A")
        return {
            "model_id": "experiment_a",
            "model_name": "Experiment A (REPLACE-BG)",
            "mode": "cgm_only",
            "inputs_used": ["glucose", "time"],
            "forecast": [s.model_dump() for s in res.forecast],
            "clinical_alert": res.clinical_alert.model_dump(),
            "model_version": res.model_version,
            "disclaimer": res.disclaimer
        }
    elif norm_id == "experiment_b":
        res = legacy_engine.predict(readings, latest_dt, experiment="gp_B")
        return {
            "model_id": "experiment_b",
            "model_name": "Experiment B (REPLACE-BG + Shanghai T2D)",
            "mode": "cgm_only",
            "inputs_used": ["glucose", "time"],
            "forecast": [s.model_dump() for s in res.forecast],
            "clinical_alert": res.clinical_alert.model_dump(),
            "model_version": res.model_version,
            "disclaimer": res.disclaimer
        }
    else:
        raise ValueError(f"Unsupported model_id: '{model_id}'")
