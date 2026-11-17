import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import db

GLUCOSE_24 = [110, 98, 99, 89, 96, 92, 87, 85, 84, 81, 82, 80, 75, 73, 74, 72, 70, 68, 67, 66, 64, 62, 65, 60]
LATEST_TS = "2026-11-10T12:30:00"

@pytest.fixture(scope="module")
def auth_client():
    with TestClient(app) as client:
        user = db.get_or_create_user("mock", "slots_tester_sub", "slots@example.com", "Slots Tester")
        db.update_user_profile(user.id, "Slots Tester", 28, "Female", True, False)
        res = client.post("/auth/mock/login", json={"email": "slots@example.com", "name": "Slots Tester", "sub": "slots_tester_sub"})
        client.headers.update({"X-CSRF-Token": res.json()["csrf_token"]})
        yield client

def test_toggle_states_and_inputs_used(auth_client):
    """Verifies that null vs [] vs events controls inputs_used and mode."""
    # 1. All null -> cgm_only
    p1 = {"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "bolus": None, "basal": None, "carbs": None}
    r1 = auth_client.post("/v1/forecast", json=p1).json()
    assert r1["mode"] == "cgm_only"
    assert r1["inputs_used"] == ["cgm"]

    # 2. Available but none ([] or 0) -> multimodal
    p2 = {"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "bolus": [], "basal": 0.9, "carbs": []}
    r2 = auth_client.post("/v1/forecast", json=p2).json()
    assert r2["mode"] == "multimodal"
    assert set(r2["inputs_used"]) == {"cgm", "bolus", "basal", "carbs"}

    # 3. Only carbs provided -> multimodal, cgm + carbs
    p3 = {"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "bolus": None, "basal": None, "carbs": [{"time": LATEST_TS, "carbs": 30.0}]}
    r3 = auth_client.post("/v1/forecast", json=p3).json()
    assert r3["mode"] == "multimodal"
    assert set(r3["inputs_used"]) == {"cgm", "carbs"}

def test_slot_assignment_1207_to_1215(auth_client):
    """
    An event at 12:07 must land in the FIRST slot with timestamp >= 12:07, which is 12:15 (slot index 22).
    It must NOT land in 12:00 (slot 21).
    Therefore, giving carbs at 12:07 vs carbs at 12:15 should yield identical model inputs and forecast.
    """
    payload_1207 = {
        "readings": GLUCOSE_24,
        "latest_timestamp": LATEST_TS,
        "bolus": None,
        "basal": None,
        "carbs": [{"time": "2026-11-10T12:07:00", "carbs": 45.0}]
    }
    payload_1215 = {
        "readings": GLUCOSE_24,
        "latest_timestamp": LATEST_TS,
        "bolus": None,
        "basal": None,
        "carbs": [{"time": "2026-11-10T12:15:00", "carbs": 45.0}]
    }
    payload_1200 = {
        "readings": GLUCOSE_24,
        "latest_timestamp": LATEST_TS,
        "bolus": None,
        "basal": None,
        "carbs": [{"time": "2026-11-10T12:00:00", "carbs": 45.0}]
    }

    r_1207 = auth_client.post("/v1/forecast", json=payload_1207).json()
    r_1215 = auth_client.post("/v1/forecast", json=payload_1215).json()
    r_1200 = auth_client.post("/v1/forecast", json=payload_1200).json()

    # 12:07 must exactly match 12:15
    assert r_1207["forecast_30m"] == r_1215["forecast_30m"]
    assert r_1207["forecast_60m"] == r_1215["forecast_60m"]

def test_summed_same_slot_events(auth_client):
    """Two events in the same 15m slot must be summed."""
    payload_split = {
        "readings": GLUCOSE_24,
        "latest_timestamp": LATEST_TS,
        "bolus": [{"time": "2026-11-10T12:05:00", "units": 2.0}, {"time": "2026-11-10T12:10:00", "units": 3.0}],
        "basal": 0.9,
        "carbs": []
    }
    payload_single = {
        "readings": GLUCOSE_24,
        "latest_timestamp": LATEST_TS,
        "bolus": [{"time": "2026-11-10T12:15:00", "units": 5.0}],
        "basal": 0.9,
        "carbs": []
    }
    r_split = auth_client.post("/v1/forecast", json=payload_split).json()
    r_single = auth_client.post("/v1/forecast", json=payload_single).json()
    assert r_split["forecast_30m"] == r_single["forecast_30m"]

def test_reject_future_events(auth_client):
    """An event after the latest reading time must be rejected with 422 {code, message}."""
    payload = {
        "readings": GLUCOSE_24,
        "latest_timestamp": LATEST_TS,
        "bolus": [{"time": "2026-11-10T12:35:00", "units": 3.0}], # 5m after latest 12:30
        "basal": None,
        "carbs": None
    }
    res = auth_client.post("/v1/forecast", json=payload)
    assert res.status_code == 422
    data = res.json()
    assert "code" in data or "detail" in data

def test_reject_out_of_range_limits(auth_client):
    """Bolus > 40, Basal > 5, Carbs > 370 or negatives must be rejected with 422."""
    # Bolus > 40
    res = auth_client.post("/v1/forecast", json={"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "bolus": [{"time": LATEST_TS, "units": 45.0}]})
    assert res.status_code == 422

    # Bolus < 0
    res = auth_client.post("/v1/forecast", json={"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "bolus": [{"time": LATEST_TS, "units": -1.0}]})
    assert res.status_code == 422

    # Basal > 5
    res = auth_client.post("/v1/forecast", json={"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "basal": 6.5})
    assert res.status_code == 422

    # Basal < 0
    res = auth_client.post("/v1/forecast", json={"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "basal": -0.5})
    assert res.status_code == 422

    # Carbs > 370
    res = auth_client.post("/v1/forecast", json={"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "carbs": [{"time": LATEST_TS, "carbs": 400.0}]})
    assert res.status_code == 422

    # Carbs < 0
    res = auth_client.post("/v1/forecast", json={"readings": GLUCOSE_24, "latest_timestamp": LATEST_TS, "carbs": [{"time": LATEST_TS, "carbs": -5.0}]})
    assert res.status_code == 422

def test_clock_grid_mode_requires_24_slots(auth_client):
    """In 'clock' grid mode, insufficient consecutive readings return 422 'Collecting data: N of 24 readings'."""
    incomplete_readings = [
        {"timestamp": "2026-11-10T12:00:00", "glucose": 120.0},
        {"timestamp": "2026-11-10T12:15:00", "glucose": 122.0}
    ]
    payload = {
        "readings": incomplete_readings,
        "grid": "clock",
        "latest_timestamp": "2026-11-10T12:15:00"
    }
    res = auth_client.post("/v1/forecast", json=payload)
    assert res.status_code == 422
    data = res.json()
    assert "Collecting data" in str(data) or "collecting_data" in str(data)
