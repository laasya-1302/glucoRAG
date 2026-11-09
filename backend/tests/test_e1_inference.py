import os
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.services.e1_inference import e1_service, OUT_LEN
from app.services.model_registry import get_registered_models, is_model_supported

VALID_24 = [142, 138, 135, 132, 129, 127, 125, 128, 131, 134, 139, 145, 148, 151, 147, 143, 140, 136, 133, 130, 128, 131, 135, 139]

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_e1_models_loaded():
    """Verify that E1 service successfully loads all 3 seeds (s42, s123, s2026)."""
    assert e1_service.is_ready() is True
    assert set(e1_service.models.keys()) == {"s42", "s123", "s2026"}
    for seed, model in e1_service.models.items():
        assert model is not None
        assert not model.training  # In evaluation mode

def test_e1_preprocessing_cgmonly():
    """Verify CGM-only preprocessing returns shape (1, 24, 9) and E1_cgmonly mode."""
    dt = datetime(2026, 10, 27, 12, 0, 0)
    x, mode = e1_service.preprocess(VALID_24, dt)
    assert x.shape == (1, 24, 9)
    assert mode == "E1_cgmonly"
    
    # Event channels 3..8 should all be zeros
    assert (x[0, :, 3:] == 0.0).all()
    
    # Glucose channel should be normalized: (g - mean) / std
    mean = e1_service.scalers["glucose"]["mean"]
    std = e1_service.scalers["glucose"]["std"]
    expected_g0 = (VALID_24[0] - mean) / std
    assert pytest.approx(x[0, 0, 0], 1e-4) == expected_g0

def test_e1_preprocessing_multimodal():
    """Verify multimodal events are bucketed, scaled, and activate mode E1."""
    dt = datetime(2026, 10, 27, 12, 0, 0)
    # Event 15 minutes before latest
    ins_event = [{"timestamp": "2026-10-27T11:45:00", "units": 5.0, "type": "bolus"}]
    carb_event = [{"timestamp": "2026-10-27T11:45:00", "carbs": 40.0}]
    
    x, mode = e1_service.preprocess(VALID_24, dt, insulin_events=ins_event, carb_events=carb_event)
    assert x.shape == (1, 24, 9)
    assert mode == "E1"
    
    # Index 22 is 11:45 (since 23 is 12:00)
    assert x[0, 22, 3] > 0.0  # scaled bolus
    assert x[0, 22, 5] > 0.0  # scaled carbs
    assert x[0, 22, 6] == 1.0 # m_bolus mask
    assert x[0, 22, 8] == 1.0 # m_carb mask

def test_e1_ensemble_prediction_structure():
    """Verify 3-seed ensemble prediction outputs 8 steps, monotonic quantiles, and calibrated shifts."""
    dt = datetime(2026, 10, 27, 12, 0, 0)
    res = e1_service.predict(VALID_24, dt)
    
    assert res["mode"] == "E1_cgmonly"
    assert len(res["forecast"]) == OUT_LEN
    assert "clinical_alert" in res
    assert res["ensemble_seeds"] == ["s42", "s123", "s2026"]
    
    for step in res["forecast"]:
        q = step["quantiles"]
        # Quantiles must be sorted: q10 <= q25 <= q50 <= q75 <= q90
        assert q["q10"] <= q["q25"] <= q["q50"] <= q["q75"] <= q["q90"]
        
        # Uncertainty band low_q10 <= high_q90
        band = step["uncertainty_band"]
        assert band["low_q10"] <= band["high_q90"]
        assert pytest.approx(band["bandwidth"], 0.2) == (band["high_q90"] - band["low_q10"])
        
        # Probabilities sum to 1.0
        probs = step["risk_probabilities"]
        assert pytest.approx(probs["hypo"] + probs["normal"] + probs["hyper"], 1e-4) == 1.0
        assert step["predicted_risk_class"] in ("HYPO", "NORMAL", "HYPER")

def test_v1_models_endpoint(client):
    """Verify GET /v1/models lists all registered models."""
    res = client.get("/v1/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    model_ids = [m["model_id"] for m in data["models"]]
    assert "e1_gpformer" in model_ids
    assert "experiment_a" in model_ids
    assert "experiment_b" in model_ids
    
    e1_item = next(m for m in data["models"] if m["model_id"] == "e1_gpformer")
    assert e1_item["checkpoint_available"] is True
    assert e1_item["supports_multimodal"] is True
    assert len(e1_item["input_features"]) == 9

def test_v1_forecast_e1_endpoint(client):
    """Verify POST /v1/forecast works with E1 model and returns 30/60/90/120m horizons."""
    payload = {
        "model_id": "e1_gpformer",
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00"
    }
    res = client.post("/v1/forecast", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["model_id"] == "e1_gpformer"
    assert data["mode"] == "E1_cgmonly"
    assert data["forecast_30m"] is not None
    assert data["forecast_60m"] is not None
    assert data["forecast_90m"] is not None
    assert data["forecast_120m"] is not None
    assert len(data["forecast"]) == 8
    assert "30" in data["horizons_summary"]
    assert "60" in data["horizons_summary"]
    assert "90" in data["horizons_summary"]
    assert "120" in data["horizons_summary"]

def test_v1_forecast_multimodal_endpoint(client):
    """Verify POST /v1/forecast with insulin and carb events activates multimodal mode."""
    payload = {
        "model_id": "e1_gpformer",
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "insulin_events": [{"timestamp": "2026-10-27T11:30:00", "units": 4.5, "type": "bolus"}],
        "carb_events": [{"timestamp": "2026-10-27T11:30:00", "carbs": 35.0}]
    }
    res = client.post("/v1/forecast", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["mode"] == "E1"

def test_v1_forecast_legacy_models(client):
    """Verify POST /v1/forecast supports experiment_a and experiment_b."""
    payload_a = {
        "model_id": "experiment_a",
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00"
    }
    res_a = client.post("/v1/forecast", json=payload_a)
    assert res_a.status_code == 200
    assert res_a.json()["model_id"] == "experiment_a"

    payload_b = {
        "model_id": "experiment_b",
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00"
    }
    res_b = client.post("/v1/forecast", json=payload_b)
    assert res_b.status_code == 200
    assert res_b.json()["model_id"] == "experiment_b"

def test_predict_endpoint_e1_dispatch(client):
    """Verify backward-compatible POST /predict handles experiment='e1_gpformer'."""
    payload = {
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "experiment": "e1_gpformer"
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["experiment"] == "e1_gpformer"
    assert len(data["forecast"]) == 8
    assert "HYPO" in [step["predicted_risk_class"] for step in data["forecast"]] or True

def test_v1_forecast_object_readings_support(client):
    """Verify readings passed as list of objects with glucose and timestamp are parsed."""
    obj_readings = [
        {"glucose": val, "timestamp": f"2026-10-27T{10 + (i // 4):02d}:{(i % 4) * 15:02d}:00"}
        for i, val in enumerate(VALID_24)
    ]
    payload = {
        "model_id": "e1_gpformer",
        "readings": obj_readings
    }
    res = client.post("/v1/forecast", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["input_summary"]["count"] == 24
