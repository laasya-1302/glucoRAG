from typing import Any, Optional, Union
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
<<<<<<< HEAD
    slot_dts: Optional[list[datetime]] = None,
    bolus: Optional[list[Any]] = None,
    basal: Optional[Union[float, list[Any], dict]] = None,
    carbs: Optional[list[Any]] = None,
=======
    bolus_events: Optional[list[dict]] = None,
    basal_events: Optional[list[dict]] = None,
    carb_events: Optional[list[dict]] = None,
    # Backward compat
>>>>>>> origin/main
    insulin_events: Optional[list[dict]] = None,
) -> dict[str, Any]:
    norm_id = normalize_model_id(model_id)

    if norm_id == "e1_gpformer":
        # Handle backward compatibility with insulin_events / carb_events if bolus/carbs are None
        if bolus is None and basal is None and insulin_events:
            bolus_list = []
            basal_list = []
            for ev in insulin_events:
                t = ev.get("type", "bolus")
                if t == "basal":
                    basal_list.append(ev)
                else:
                    bolus_list.append(ev)
            bolus = bolus_list
            basal = basal_list if basal_list else None
        if carbs is None and carb_events:
            carbs = carb_events

        result = e1_service.predict(
            readings=readings,
            latest_dt=latest_dt,
<<<<<<< HEAD
            slot_dts=slot_dts,
            bolus=bolus,
            basal=basal,
            carbs=carbs
=======
            bolus_events=bolus_events,
            basal_events=basal_events,
            carb_events=carb_events,
            insulin_events=insulin_events,
>>>>>>> origin/main
        )
        return {
            "model_id": "e1_gpformer",
            "model_name": result.get("model_name", "E1 Multimodal GPFormer (3-Seed Ensemble)"),
            "mode": result["mode"],
<<<<<<< HEAD
            "inputs_used": result.get("inputs_used", ["cgm"]),
            "forecast_origin": result.get("forecast_origin"),
            "now_mgdl": result.get("now_mgdl"),
            "checkpoint_sha256": result.get("checkpoint_sha256"),
=======
            "inputs_used": result.get("inputs_used", ["glucose", "time"]),
>>>>>>> origin/main
            "forecast": result["forecast"],
            "clinical_alert": result.get("clinical_alert"),
            "inspector": result.get("inspector"),
            "model_version": result["model_version"],
            "disclaimer": result["disclaimer"]
        }
    elif norm_id == "experiment_a":
        res = legacy_engine.predict(readings, latest_dt, experiment="gp_A")
        return {
            "model_id": "experiment_a",
            "model_name": "Experiment A (REPLACE-BG)",
            "mode": "cgm_only",
<<<<<<< HEAD
            "inputs_used": ["cgm"],
            "forecast_origin": latest_dt.isoformat(),
            "now_mgdl": float(readings[-1]),
            "checkpoint_sha256": {},
=======
            "inputs_used": ["glucose", "time"],
>>>>>>> origin/main
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
<<<<<<< HEAD
            "inputs_used": ["cgm"],
            "forecast_origin": latest_dt.isoformat(),
            "now_mgdl": float(readings[-1]),
            "checkpoint_sha256": {},
=======
            "inputs_used": ["glucose", "time"],
>>>>>>> origin/main
            "forecast": [s.model_dump() for s in res.forecast],
            "clinical_alert": res.clinical_alert.model_dump(),
            "model_version": res.model_version,
            "disclaimer": res.disclaimer
        }
    else:
        raise ValueError(f"Unsupported model_id: '{model_id}'")
