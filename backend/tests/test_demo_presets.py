import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import db

DEMO_GLUCOSE = [110, 98, 99, 89, 96, 92, 87, 85, 84, 81, 82, 80, 75, 73, 74, 72, 70, 68, 67, 66, 64, 62, 65, 60]

PRESETS = {
    "A": {
        "name": "Glucose only (CGM-only)",
        "bolus": None,
        "basal": None,
        "carbs": None,
        "expected_medians": [59, 79, 97, 106],
        "expected_mode": "cgm_only"
    },
    "B": {
        "name": "Multimodal, no insulin, no carbs",
        "bolus": [],
        "basal": 0.9,
        "carbs": [],
        "expected_medians": [61, 84, 102, 113],
        "expected_mode": "multimodal"
    },
    "C": {
        "name": "Carbs 30 g, insulin data unavailable",
        "bolus": None,
        "basal": None,
        "carbs": [{"time": "2026-11-10T12:30:00", "carbs": 30.0}],
        "expected_medians": [67, 88, 103, 111],
        "expected_mode": "multimodal"
    },
    "D": {
        "name": "Carbs 60 g, insulin data unavailable",
        "bolus": None,
        "basal": None,
        "carbs": [{"time": "2026-11-10T12:30:00", "carbs": 60.0}],
        "expected_medians": [82, 103, 111, 113],
        "expected_mode": "multimodal"
    },
    "E": {
        "name": "Carbs 60 g, insulin available, none given",
        "bolus": [],
        "basal": 0.9,
        "carbs": [{"time": "2026-11-10T12:30:00", "carbs": 60.0}],
        "expected_medians": [83, 108, 114, 117],
        "expected_mode": "multimodal"
    },
    "F": {
        "name": "Carbs 60 g + bolus 4 U",
        "bolus": [{"time": "2026-11-10T12:30:00", "units": 4.0}],
        "basal": 0.9,
        "carbs": [{"time": "2026-11-10T12:30:00", "carbs": 60.0}],
        "expected_medians": [84, 109, 114, 117],
        "expected_mode": "multimodal"
    },
    "G": {
        "name": "Bolus 4 U, no carbs",
        "bolus": [{"time": "2026-11-10T12:30:00", "units": 4.0}],
        "basal": 0.9,
        "carbs": [],
        "expected_medians": [64, 89, 107, 116],
        "expected_mode": "multimodal"
    }
}

@pytest.fixture(scope="module")
def auth_client():
    with TestClient(app) as client:
        user = db.get_or_create_user(
            provider="mock",
            provider_sub="presets_tester_sub",
            email="presets@example.com",
            name="Presets Tester"
        )
        db.update_user_profile(
            user_id=user.id,
            name="Presets Tester",
            age=40,
            gender="Non-binary",
            consent=True,
            minor_confirmed=False
        )
        res = client.post("/auth/mock/login", json={
            "email": "presets@example.com",
            "name": "Presets Tester",
            "sub": "presets_tester_sub"
        })
        csrf_token = res.json()["csrf_token"]
        client.headers.update({"X-CSRF-Token": csrf_token})
        yield client

@pytest.mark.parametrize("preset_key", ["A", "B", "C", "D", "E", "F", "G"])
def test_demo_preset_acceptance(auth_client, preset_key):
    cfg = PRESETS[preset_key]
    payload = {
        "model_id": "e1_gpformer",
        "readings": DEMO_GLUCOSE,
        "latest_timestamp": "2026-11-10T12:30:00",
        "bolus": cfg["bolus"],
        "basal": cfg["basal"],
        "carbs": cfg["carbs"],
        "grid": "manual"
    }

    res = auth_client.post("/v1/forecast", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["mode"] == cfg["expected_mode"]
    
    # Check +30, +60, +90, +120
    actual_medians = [
        data["forecast_30m"],
        data["forecast_60m"],
        data["forecast_90m"],
        data["forecast_120m"]
    ]
    expected_medians = cfg["expected_medians"]

    print(f"\nPreset {preset_key} ({cfg['name']}): Actual={actual_medians}, Expected={expected_medians}")
    for act, exp in zip(actual_medians, expected_medians):
        diff = abs(act - exp)
        assert diff <= 3.0, f"Preset {preset_key} median diff exceeds 3 mg/dL: actual={act}, expected={exp}, diff={diff}"
