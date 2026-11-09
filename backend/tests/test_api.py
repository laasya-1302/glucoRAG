import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

VALID_24 = [142, 138, 135, 132, 129, 127, 125, 128, 131, 134, 139, 145, 148, 151, 147, 143, 140, 136, 133, 130, 128, 131, 135, 139]

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_health_endpoint(client):
    """Test GET /health returns 200 and healthy status."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["api_online"] is True
    assert data["model_loaded"] is True
    assert "gp_A" in data["available_experiments"]

def test_model_info_endpoint(client):
    """Test GET /model-info returns 200 with forecast parameters."""
    res = client.get("/model-info")
    assert res.status_code == 200
    data = res.json()
    assert data["input_sequence_length"] == 24
    assert data["forecast_horizon_steps"] == 8
    assert data["sampling_interval_minutes"] == 15
    assert len(data["available_experiments"]) >= 2

def test_predict_success(client):
    """Test POST /predict with valid payload."""
    payload = {
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "experiment": "gp_A"
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["units"] == "mg/dL"
    assert len(data["forecast"]) == 8
    assert data["input_summary"]["count"] == 24
    assert data["input_summary"]["latest_glucose_mg_dl"] == 139.0

def test_predict_experiment_b(client):
    """Test POST /predict with Experiment B."""
    payload = {
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "experiment": "gp_B"
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["experiment"] == "gp_B"
    assert len(data["forecast"]) == 8

def test_predict_invalid_length_23(client):
    """Test POST /predict rejects 23 readings with 422."""
    payload = {
        "readings": VALID_24[:-1],
        "experiment": "gp_A"
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 422
    data = res.json()
    assert data["error"] == "InvalidSequenceLength"
    assert data["received_count"] == 23

def test_predict_invalid_experiment(client):
    """Test POST /predict rejects invalid experiment with 400."""
    payload = {
        "readings": VALID_24,
        "experiment": "gp_NonExistent"
    }
    res = client.post("/predict", json=payload)
    assert res.status_code == 400
    data = res.json()
    assert data["error"] == "InvalidExperiment"
