import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import db

GLUCOSE_24 = [110, 98, 99, 89, 96, 92, 87, 85, 84, 81, 82, 80, 75, 73, 74, 72, 70, 68, 67, 66, 64, 62, 65, 60]
LATEST_TS = "2026-11-10T12:30:00"

@pytest.fixture(scope="module")
def auth_client():
    with TestClient(app) as client:
        user = db.get_or_create_user("mock", "det_tester_sub", "det@example.com", "Determinism Tester")
        db.update_user_profile(user.id, "Determinism Tester", 35, "Male", True, False)
        res = client.post("/auth/mock/login", json={"email": "det@example.com", "name": "Determinism Tester", "sub": "det_tester_sub"})
        client.headers.update({"X-CSRF-Token": res.json()["csrf_token"]})
        yield client

def test_same_input_twice_identical_output(auth_client):
    payload = {
        "model_id": "e1_gpformer",
        "readings": GLUCOSE_24,
        "latest_timestamp": LATEST_TS,
        "bolus": [{"time": "2026-11-10T12:30:00", "units": 4.0}],
        "basal": 0.9,
        "carbs": [{"time": "2026-11-10T12:30:00", "carbs": 60.0}],
        "grid": "manual"
    }

    res1 = auth_client.post("/v1/forecast", json=payload).json()
    res2 = auth_client.post("/v1/forecast", json=payload).json()

    assert res1["forecast_30m"] == res2["forecast_30m"]
    assert res1["forecast_60m"] == res2["forecast_60m"]
    assert res1["forecast_90m"] == res2["forecast_90m"]
    assert res1["forecast_120m"] == res2["forecast_120m"]
    assert res1["mode"] == res2["mode"]
    assert res1["checkpoint_sha256"] == res2["checkpoint_sha256"]

    # Verify all 8 steps have exact matching medians and bounds
    for s1, s2 in zip(res1["forecast"], res2["forecast"]):
        assert s1["median"] == s2["median"]
        assert s1["lo"] == s2["lo"]
        assert s1["hi"] == s2["hi"]
        assert s1["p_hypo"] == s2["p_hypo"]
        assert s1["p_normal"] == s2["p_normal"]
        assert s1["p_hyper"] == s2["p_hyper"]
        assert s1["alert"] == s2["alert"]

def test_future_events_rejected_strict_causality(auth_client):
    """
    Events after the forecast origin (12:30) must be rejected with 422,
    guaranteeing that changing hypothetical data in the future cannot alter the origin forecast.
    """
    payload_future = {
        "model_id": "e1_gpformer",
        "readings": GLUCOSE_24,
        "latest_timestamp": LATEST_TS,
        "bolus": [{"time": "2026-11-10T12:45:00", "units": 5.0}], # 15 min after origin
        "basal": 0.9,
        "carbs": []
    }
    res = auth_client.post("/v1/forecast", json=payload_future)
    assert res.status_code == 422
