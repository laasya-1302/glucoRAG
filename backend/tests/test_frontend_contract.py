import pytest
from fastapi.testclient import TestClient
from app.main import app

VALID_24 = [142, 138, 135, 132, 129, 127, 125, 128, 131, 134, 139, 145, 148, 151, 147, 143, 140, 136, 133, 130, 128, 131, 135, 139]

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_frontend_payload_contract(client):
    """Verifies that the exact payload shape sent by GlucoseInputForm.jsx is parsed and processed cleanly."""
    frontend_payload = {
        "readings": [float(x) for x in VALID_24],
        "latest_timestamp": "2026-10-27T14:30:00",
        "experiment": "gp_A"
    }

    res = client.post("/predict", json=frontend_payload)
    assert res.status_code == 200
    data = res.json()

    # Verify all fields expected by App.jsx, ForecastChart.jsx, and ForecastTable.jsx
    assert "status" in data and data["status"] == "success"
    assert "units" in data and data["units"] == "mg/dL"
    assert "forecast" in data and len(data["forecast"]) == 8
    assert "clinical_alert" in data
    assert "input_summary" in data

    # Verify forecast step structure matches frontend requirements
    for step in data["forecast"]:
        assert "step" in step
        assert "horizon_minutes" in step
        assert "timestamp" in step
        assert "glucose_median" in step
        assert "quantiles" in step
        assert "uncertainty_band" in step
        assert "risk_probabilities" in step
        assert "predicted_risk_class" in step

        # Verify quantiles dictionary
        q = step["quantiles"]
        for q_key in ["q10", "q25", "q50", "q75", "q90"]:
            assert q_key in q
            assert isinstance(q[q_key], (int, float))

        # Verify uncertainty band dictionary
        band = step["uncertainty_band"]
        assert "low_q10" in band and "high_q90" in band and "bandwidth" in band
        assert band["bandwidth"] >= 0

        # Verify risk probabilities dictionary
        probs = step["risk_probabilities"]
        for p_key in ["hypo", "normal", "hyper"]:
            assert p_key in probs
            assert 0.0 <= probs[p_key] <= 1.0

        # Verify predicted risk class
        assert step["predicted_risk_class"] in ["HYPO", "NORMAL", "HYPER"]

    # Verify clinical alert structure matches ClinicalAlertCard.jsx
    alert = data["clinical_alert"]
    assert "status" in alert
    assert alert["status"] in ["NORMAL", "HYPO_RISK", "HYPER_RISK"]
    assert "message" in alert
    assert isinstance(alert["message"], str)

def test_frontend_error_handling_structure(client):
    """Verifies that 422 validation errors contain clear machine-readable and human-readable diagnostic messages."""
    # Test missing field
    res = client.post("/predict", json={"readings": [100.0] * 23})
    assert res.status_code == 422
    err = res.json()
    assert "error" in err or "detail" in err
    msg = err.get("message") or str(err.get("detail"))
    assert "24" in msg

    # Test out-of-range value
    bad_readings = list(VALID_24)
    bad_readings[0] = 999.0
    res_range = client.post("/predict", json={"readings": bad_readings})
    assert res_range.status_code == 422
    err_range = res_range.json()
    msg_range = err_range.get("message") or str(err_range.get("detail"))
    assert "physiological" in msg_range.lower() or "acceptable" in msg_range.lower()
