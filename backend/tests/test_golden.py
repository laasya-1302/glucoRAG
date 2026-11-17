import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import db

@pytest.fixture(scope="module")
def auth_client():
    with TestClient(app) as client:
        # Create user with completed profile
        user = db.get_or_create_user(
            provider="mock",
            provider_sub="golden_tester_sub",
            email="tester@example.com",
            name="Golden Tester"
        )
        db.update_user_profile(
            user_id=user.id,
            name="Golden Tester",
            age=32,
            gender="Prefer not to say",
            consent=True,
            minor_confirmed=False
        )
        res = client.post("/auth/mock/login", json={
            "email": "tester@example.com",
            "name": "Golden Tester",
            "sub": "golden_tester_sub"
        })
        assert res.status_code == 200
        csrf_token = res.json()["csrf_token"]
        client.headers.update({"X-CSRF-Token": csrf_token})
        yield client

def test_golden1_cgm_only(auth_client):
    """
    Test Golden 1 (CGM-only) against fixtures/golden1_expected.json.
    Verifies medians/bands within 0.5 mg/dL, probabilities within 0.01, identical alerts.
    """
    fixtures_dir = Path("fixtures")
    with open(fixtures_dir / "golden1_input.json", "r") as f:
        payload = json.load(f)
    with open(fixtures_dir / "golden1_expected.json", "r") as f:
        expected = json.load(f)

    res = auth_client.post("/v1/forecast", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["mode"] == expected["mode"]
    assert data["status"] == "success"

    actual_forecast = data["forecast"]
    expected_forecast = expected["forecast"]
    assert len(actual_forecast) == len(expected_forecast)

    for act, exp in zip(actual_forecast, expected_forecast):
        assert abs(act["median"] - exp["median"]) <= 0.5, f"Median diff at +{act['horizon_minutes']}m: {act['median']} vs {exp['median']}"
        assert abs(act["lo"] - exp["lo"]) <= 0.5, f"Lo diff at +{act['horizon_minutes']}m: {act['lo']} vs {exp['lo']}"
        assert abs(act["hi"] - exp["hi"]) <= 0.5, f"Hi diff at +{act['horizon_minutes']}m: {act['hi']} vs {exp['hi']}"
        assert abs(act["p_hypo"] - exp["p_hypo"]) <= 0.01, f"P(hypo) diff at +{act['horizon_minutes']}m"
        assert abs(act["p_normal"] - exp["p_normal"]) <= 0.01, f"P(normal) diff at +{act['horizon_minutes']}m"
        assert abs(act["p_hyper"] - exp["p_hyper"]) <= 0.01, f"P(hyper) diff at +{act['horizon_minutes']}m"
        assert act["alert"] == exp["alert"], f"Alert mismatch at +{act['horizon_minutes']}m: {act['alert']} vs {exp['alert']}"
        assert act["forecast_class"] == exp["forecast_class"], f"Forecast class mismatch at +{act['horizon_minutes']}m"

def test_golden2_multimodal(auth_client):
    """
    Test Golden 2 (Multimodal) against fixtures/golden2_expected.json.
    Verifies medians/bands within 0.5 mg/dL, probabilities within 0.01, identical alerts.
    """
    fixtures_dir = Path("fixtures")
    with open(fixtures_dir / "golden2_input.json", "r") as f:
        payload = json.load(f)
    with open(fixtures_dir / "golden2_expected.json", "r") as f:
        expected = json.load(f)

    res = auth_client.post("/v1/forecast", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["mode"] == expected["mode"]
    assert data["status"] == "success"

    actual_forecast = data["forecast"]
    expected_forecast = expected["forecast"]
    assert len(actual_forecast) == len(expected_forecast)

    for act, exp in zip(actual_forecast, expected_forecast):
        assert abs(act["median"] - exp["median"]) <= 0.5, f"Median diff at +{act['horizon_minutes']}m: {act['median']} vs {exp['median']}"
        assert abs(act["lo"] - exp["lo"]) <= 0.5, f"Lo diff at +{act['horizon_minutes']}m: {act['lo']} vs {exp['lo']}"
        assert abs(act["hi"] - exp["hi"]) <= 0.5, f"Hi diff at +{act['horizon_minutes']}m: {act['hi']} vs {exp['hi']}"
        assert abs(act["p_hypo"] - exp["p_hypo"]) <= 0.01, f"P(hypo) diff at +{act['horizon_minutes']}m"
        assert abs(act["p_normal"] - exp["p_normal"]) <= 0.01, f"P(normal) diff at +{act['horizon_minutes']}m"
        assert abs(act["p_hyper"] - exp["p_hyper"]) <= 0.01, f"P(hyper) diff at +{act['horizon_minutes']}m"
        assert act["alert"] == exp["alert"], f"Alert mismatch at +{act['horizon_minutes']}m: {act['alert']} vs {exp['alert']}"
        assert act["forecast_class"] == exp["forecast_class"], f"Forecast class mismatch at +{act['horizon_minutes']}m"
