import json
from pathlib import Path
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.e1_inference import e1_service

VALID_24 = [142, 138, 135, 132, 129, 127, 125, 128, 131, 134, 139, 145, 148, 151, 147, 143, 140, 136, 133, 130, 128, 131, 135, 139]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _load_golden2_fixtures():
    # Look in backend/tests/fixtures then fixtures
    input_paths = [
        Path(__file__).resolve().parent / "fixtures" / "golden2_input.json",
        PROJECT_ROOT / "fixtures" / "golden2_input.json"
    ]
    expected_paths = [
        Path(__file__).resolve().parent / "fixtures" / "golden2_expected.json",
        PROJECT_ROOT / "fixtures" / "golden2_expected.json"
    ]
    inp_file = next(p for p in input_paths if p.exists())
    exp_file = next(p for p in expected_paths if p.exists())
    with open(inp_file, "r", encoding="utf-8") as f:
        inp = json.load(f)
    with open(exp_file, "r", encoding="utf-8") as f:
        exp = json.load(f)
    return inp, exp

def test_golden2_fixture(client):
    """
    The golden test fixtures/golden2_* (glucose + bolus 5 U at slot 16 + basal 0.9 U/h + carbs 50 g at slot 16):
    outputs must match golden2_expected.json:
    - medians/bands within 0.5 mg/dL
    - probabilities within 0.01
    - identical risk labels
    """
    inp_payload, expected = _load_golden2_fixtures()
    res = client.post("/v1/forecast", json=inp_payload)
    assert res.status_code == 200
    actual = res.json()

    assert actual["status"] == "success"
    assert actual["model_id"] == "e1_gpformer"
    assert actual["mode"] == "E1"
    assert actual["inputs_used"] == ["glucose", "time", "bolus", "basal", "carbs"]

    # Overall summary horizons
    assert pytest.approx(actual["forecast_30m"], abs=0.5) == expected["forecast_30m"]
    assert pytest.approx(actual["forecast_60m"], abs=0.5) == expected["forecast_60m"]
    assert pytest.approx(actual["forecast_90m"], abs=0.5) == expected["forecast_90m"]
    assert pytest.approx(actual["forecast_120m"], abs=0.5) == expected["forecast_120m"]

    # Compare 8 forecast steps
    for a_step, e_step in zip(actual["forecast"], expected["forecast"]):
        assert a_step["step"] == e_step["step"]
        assert a_step["horizon_minutes"] == e_step["horizon_minutes"]
        # Median within 0.5 mg/dL
        assert pytest.approx(a_step["glucose_median"], abs=0.5) == e_step["glucose_median"]

        # Uncertainty bands within 0.5 mg/dL
        assert pytest.approx(a_step["uncertainty_band"]["low_q10"], abs=0.5) == e_step["uncertainty_band"]["low_q10"]
        assert pytest.approx(a_step["uncertainty_band"]["high_q90"], abs=0.5) == e_step["uncertainty_band"]["high_q90"]
        assert pytest.approx(a_step["uncertainty_band"]["bandwidth"], abs=0.5) == e_step["uncertainty_band"]["bandwidth"]

        # Quantiles within 0.5 mg/dL
        for q_key in ["q10", "q25", "q50", "q75", "q90"]:
            assert pytest.approx(a_step["quantiles"][q_key], abs=0.5) == e_step["quantiles"][q_key]

        # Probabilities within 0.01
        assert pytest.approx(a_step["risk_probabilities"]["hypo"], abs=0.01) == e_step["risk_probabilities"]["hypo"]
        assert pytest.approx(a_step["risk_probabilities"]["normal"], abs=0.01) == e_step["risk_probabilities"]["normal"]
        assert pytest.approx(a_step["risk_probabilities"]["hyper"], abs=0.01) == e_step["risk_probabilities"]["hyper"]

        # Identical risk labels
        assert a_step["predicted_risk_class"] == e_step["predicted_risk_class"]

    # Clinical alert identical status
    assert actual["clinical_alert"]["status"] == expected["clinical_alert"]["status"]

def test_bolus_slot_12_07():
    """
    Bolus at 12:07 lands in the 12:15 slot, not 12:00.
    With latest_dt = 12:15 (slot 23), slot 22 is 12:00.
    An event at 12:07 goes into the first 15-minute slot at or after the event time (12:15 = slot 23).
    """
    dt = datetime(2026, 10, 27, 12, 15, 0)
    bolus_event = [{"timestamp": "2026-10-27T12:07:00", "units": 4.0}]
    x, mode = e1_service.preprocess(VALID_24, dt, bolus_events=bolus_event)

    assert mode == "E1"
    # Slot 23 corresponds to 12:15, slot 22 to 12:00
    assert x[0, 23, 3] > 0.0  # Bolus landed in 12:15 slot
    assert x[0, 22, 3] == 0.0 # Did NOT land in 12:00 slot

def test_future_event_returns_422(client):
    """An event after the forecast origin (latest glucose reading) returns 422."""
    payload = {
        "model_id": "e1_gpformer",
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "bolus_events": [{"timestamp": "2026-10-27T12:07:00", "units": 5.0}] # 12:07 is after 12:00
    }
    res = client.post("/v1/forecast", json=payload)
    assert res.status_code == 422
    data = res.json()
    assert data["error"] == "FutureDatedEvent"

def test_future_basal_returns_422(client):
    """Basal event after forecast origin returns 422."""
    payload = {
        "model_id": "e1_gpformer",
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "basal_events": [{"timestamp": "2026-10-27T12:01:00", "rate": 1.0}]
    }
    res = client.post("/v1/forecast", json=payload)
    assert res.status_code == 422
    assert res.json()["error"] == "FutureDatedEvent"

def test_future_carb_returns_422(client):
    """Carb event after forecast origin returns 422."""
    payload = {
        "model_id": "e1_gpformer",
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "carb_events": [{"timestamp": "2026-10-27T12:30:00", "carbs": 30.0}]
    }
    res = client.post("/v1/forecast", json=payload)
    assert res.status_code == 422
    assert res.json()["error"] == "FutureDatedEvent"

def test_insulin_toggle_off_channels_and_masks_zero():
    """
    Insulin toggle off -> channels AND masks 0.
    (multimodal differs from glucose-only only when data is supplied).
    """
    dt = datetime(2026, 10, 27, 12, 0, 0)
    x, mode = e1_service.preprocess(
        VALID_24, dt,
        bolus_events=None,
        basal_events=None,
        carb_events=None
    )
    assert mode == "E1_cgmonly"
    # All event channels (3: bolus, 4: basal, 5: carb) and masks (6, 7, 8) must be 0
    assert (x[0, :, 3:9] == 0.0).all()

def test_insulin_toggle_on_empty_list():
    """
    Insulin toggle on with an empty list -> mask 1 and zero values.
    """
    dt = datetime(2026, 10, 27, 12, 0, 0)
    x, mode = e1_service.preprocess(
        VALID_24, dt,
        bolus_events=[],
        basal_events=[],
        carb_events=None
    )
    assert mode == "E1"
    # Bolus (channel 3) = 0, m_bolus (channel 6) = 1.0 for all slots
    assert (x[0, :, 3] == 0.0).all()
    assert (x[0, :, 6] == 1.0).all()

    # Basal (channel 4) = 0, m_basal (channel 7) = 1.0 for all slots
    assert (x[0, :, 4] == 0.0).all()
    assert (x[0, :, 7] == 1.0).all()

    # Carbs not supplied: carb value (channel 5) = 0, m_carb mask (channel 8) = 0
    assert (x[0, :, 5] == 0.0).all()
    assert (x[0, :, 8] == 0.0).all()

def test_carbs_toggle_on_empty_list():
    """Carbs toggle on with empty list -> mask 1 and zero values."""
    dt = datetime(2026, 10, 27, 12, 0, 0)
    x, mode = e1_service.preprocess(
        VALID_24, dt,
        bolus_events=None,
        basal_events=None,
        carb_events=[]
    )
    assert mode == "E1"
    assert (x[0, :, 5] == 0.0).all()
    assert (x[0, :, 8] == 1.0).all()
    # Insulin not supplied -> masks 0
    assert (x[0, :, 6] == 0.0).all()
    assert (x[0, :, 7] == 0.0).all()

def test_same_input_twice_identical_output(client):
    """Same input twice gives identical output (deterministic inference)."""
    payload = {
        "model_id": "e1_gpformer",
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "bolus_events": [{"timestamp": "2026-10-27T10:15:00", "units": 5.0}],
        "basal_events": [{"timestamp": "2026-10-27T06:00:00", "rate": 0.9}],
        "carb_events": [{"timestamp": "2026-10-27T10:15:00", "carbs": 50.0}]
    }
    res1 = client.post("/v1/forecast", json=payload)
    res2 = client.post("/v1/forecast", json=payload)

    assert res1.status_code == 200
    assert res2.status_code == 200
    data1 = res1.json()
    data2 = res2.json()

    assert data1["mode"] == data2["mode"]
    assert data1["forecast_30m"] == data2["forecast_30m"]
    assert data1["forecast_60m"] == data2["forecast_60m"]
    assert data1["forecast_90m"] == data2["forecast_90m"]
    assert data1["forecast_120m"] == data2["forecast_120m"]

    for s1, s2 in zip(data1["forecast"], data2["forecast"]):
        assert s1["glucose_median"] == s2["glucose_median"]
        assert s1["quantiles"] == s2["quantiles"]
        assert s1["uncertainty_band"] == s2["uncertainty_band"]
        assert s1["risk_probabilities"] == s2["risk_probabilities"]
        assert s1["predicted_risk_class"] == s2["predicted_risk_class"]

def test_validation_impossible_values(client):
    """Validate 422 on impossible doses / amounts."""
    # Bolus > 40
    res = client.post("/v1/forecast", json={
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "bolus_events": [{"timestamp": "2026-10-27T11:00:00", "units": 45.0}]
    })
    assert res.status_code == 422
    assert res.json()["error"] == "InvalidBolusUnits"

    # Bolus < 0
    res = client.post("/v1/forecast", json={
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "bolus_events": [{"timestamp": "2026-10-27T11:00:00", "units": -1.0}]
    })
    assert res.status_code == 422
    assert res.json()["error"] == "InvalidBolusUnits"

    # Basal > 5
    res = client.post("/v1/forecast", json={
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "basal_events": [{"timestamp": "2026-10-27T11:00:00", "rate": 6.5}]
    })
    assert res.status_code == 422
    assert res.json()["error"] == "InvalidBasalRate"

    # Carbs > 370
    res = client.post("/v1/forecast", json={
        "readings": VALID_24,
        "latest_timestamp": "2026-10-27T12:00:00",
        "carb_events": [{"timestamp": "2026-10-27T11:00:00", "carbs": 400.0}]
    })
    assert res.status_code == 422
    assert res.json()["error"] == "InvalidCarbAmount"
