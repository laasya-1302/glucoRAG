import pytest
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import torch

from app.config import settings
from app.inference import engine
from gp_data import SEQ_LEN, PRED_LEN, LABEL_LEN, WIN, CLASSES, risk_class
import gp_model

VALID_24 = [142, 138, 135, 132, 129, 127, 125, 128, 131, 134, 139, 145, 148, 151, 147, 143, 140, 136, 133, 130, 128, 131, 135, 139]

def test_checkpoint_loading():
    """Test 4: Model checkpoint loading for both Experiment A and Experiment B."""
    exp_a = engine.load_experiment("gp_A")
    assert exp_a is not None
    assert isinstance(exp_a["net"], torch.nn.Module)
    assert "mean" in exp_a["norm"] and "std" in exp_a["norm"]
    assert exp_a["mark_dim"] == 2

    exp_b = engine.load_experiment("gp_B")
    assert exp_b is not None
    assert isinstance(exp_b["net"], torch.nn.Module)
    assert "mean" in exp_b["norm"] and "std" in exp_b["norm"]

def test_model_inference_and_shapes():
    """Test 5: Model inference execution and output tensor shapes."""
    dt = datetime(2026, 10, 27, 12, 0, 0)
    response = engine.predict(VALID_24, dt, "gp_A")

    assert response.status == "success"
    assert len(response.forecast) == settings.PRED_STEPS # exactly 8 steps
    for step in response.forecast:
        assert step.glucose_median > 0
        assert step.quantiles.q10 <= step.quantiles.q90
        # Probabilities sum to 1.0 within floating point precision
        prob_sum = step.risk_probabilities.hypo + step.risk_probabilities.normal + step.risk_probabilities.hyper
        assert pytest.approx(prob_sum, abs=1e-3) == 1.0

def test_quantile_ordering_and_forecast_timestamps():
    """Test 6: Quantile ordering and 15-minute incremental timestamps."""
    dt = datetime(2026, 10, 27, 8, 30, 0)
    response = engine.predict(VALID_24, dt, "gp_A")

    for i, step in enumerate(response.forecast):
        expected_mins = (i + 1) * 15
        assert step.horizon_minutes == expected_mins
        
        expected_time = dt + timedelta(minutes=expected_mins)
        assert step.timestamp == expected_time.isoformat()

        # Check uncertainty band bounds
        assert step.uncertainty_band.low_q10 <= step.uncertainty_band.high_q90
        assert step.uncertainty_band.bandwidth >= 0.0

def test_risk_class_mapping():
    """Test 7: Risk class mapping definitions (<70: HYPO, 70-180: NORMAL, >180: HYPER)."""
    assert risk_class(69.9) == 0
    assert risk_class(70.0) == 1
    assert risk_class(180.0) == 1
    assert risk_class(180.1) == 2

    assert CLASSES[0] == "HYPO"
    assert CLASSES[1] == "NORMAL"
    assert CLASSES[2] == "HYPER"

def test_offline_eval_pipeline_agreement():
    """
    Test 10: Agreement between web inference engine and offline evaluation pipeline (gp_model.predict)
    for the exact same input, within numerical tolerance.
    """
    dt = datetime(2026, 10, 27, 12, 0, 0)
    web_res = engine.predict(VALID_24, dt, "gp_A")

    # Offline evaluation pipeline reconstruction
    exp_data = engine.load_experiment("gp_A")
    net = exp_data["net"]
    norm = exp_data["norm"]
    mark_dim = exp_data["mark_dim"]

    start_dt = dt - timedelta(minutes=(SEQ_LEN - 1) * 15)
    all_dts = [start_dt + timedelta(minutes=i * 15) for i in range(WIN)]
    all_hours = [d.hour + d.minute / 60.0 + d.second / 3600.0 for d in all_dts]

    W = {
        "g": np.array([VALID_24 + [0.0] * PRED_LEN], dtype=np.float32),
        "hour": np.array([all_hours], dtype=np.float32)
    }

    q_offline, p_offline = gp_model.predict(net, W, norm, mark_dim, engine.device)
    q_offline = q_offline[0]
    p_offline = p_offline[0]

    for step_idx in range(PRED_LEN):
        web_step = web_res.forecast[step_idx]
        offline_median = q_offline[step_idx, settings.MEDIAN_INDEX]
        offline_q10 = q_offline[step_idx, 0]
        offline_q90 = q_offline[step_idx, 4]

        # Check median agrees within 0.1 mg/dL
        assert pytest.approx(web_step.glucose_median, abs=0.1) == offline_median
        assert pytest.approx(web_step.quantiles.q10, abs=0.1) == offline_q10
        assert pytest.approx(web_step.quantiles.q90, abs=0.1) == offline_q90

        # Check probabilities agree within 1e-4
        assert pytest.approx(web_step.risk_probabilities.hypo, abs=1e-4) == p_offline[step_idx, 0]
        assert pytest.approx(web_step.risk_probabilities.normal, abs=1e-4) == p_offline[step_idx, 1]
        assert pytest.approx(web_step.risk_probabilities.hyper, abs=1e-4) == p_offline[step_idx, 2]
