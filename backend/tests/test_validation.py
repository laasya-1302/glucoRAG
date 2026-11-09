import pytest
import math
from datetime import datetime
from fastapi import HTTPException
from app.validation import validate_input_sequence
from app.config import settings

VALID_24 = [142, 138, 135, 132, 129, 127, 125, 128, 131, 134, 139, 145, 148, 151, 147, 143, 140, 136, 133, 130, 128, 131, 135, 139]

def test_valid_24_readings():
    """Test 1: Input validation with exactly 24 values."""
    readings, dt = validate_input_sequence(VALID_24, "2026-10-27T12:00:00")
    assert len(readings) == 24
    assert readings == [float(v) for v in VALID_24]
    assert dt == datetime(2026, 10, 27, 12, 0, 0)

def test_rejection_of_23_values():
    """Test 2a: Rejection of 23 values."""
    with pytest.raises(HTTPException) as exc_info:
        validate_input_sequence(VALID_24[:-1])
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "InvalidSequenceLength"
    assert exc_info.value.detail["received_count"] == 23

def test_rejection_of_25_values():
    """Test 2b: Rejection of 25 values."""
    with pytest.raises(HTTPException) as exc_info:
        validate_input_sequence(VALID_24 + [140])
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "InvalidSequenceLength"
    assert exc_info.value.detail["received_count"] == 25

def test_rejection_of_missing_value():
    """Test 3a: Rejection of null/missing values."""
    bad = list(VALID_24)
    bad[5] = None
    with pytest.raises(HTTPException) as exc_info:
        validate_input_sequence(bad)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "MissingReading"
    assert exc_info.value.detail["index"] == 5

def test_rejection_of_nan_and_inf():
    """Test 3b: Rejection of NaN and infinite readings."""
    bad_nan = list(VALID_24)
    bad_nan[10] = float("nan")
    with pytest.raises(HTTPException) as exc_info:
        validate_input_sequence(bad_nan)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "NonFiniteReading"

    bad_inf = list(VALID_24)
    bad_inf[10] = float("inf")
    with pytest.raises(HTTPException) as exc_info:
        validate_input_sequence(bad_inf)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "NonFiniteReading"

def test_rejection_of_non_numeric():
    """Test 3c: Rejection of non-numeric readings."""
    bad = list(VALID_24)
    bad[3] = "invalid_number"
    with pytest.raises(HTTPException) as exc_info:
        validate_input_sequence(bad)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "NonNumericReading"

def test_rejection_of_out_of_range():
    """Test 3d: Rejection of physiologically out-of-range readings."""
    # Negative / below minimum
    bad_low = list(VALID_24)
    bad_low[0] = 5.0
    with pytest.raises(HTTPException) as exc_info:
        validate_input_sequence(bad_low)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "PhysiologicallyInvalidGlucose"

    # Extreme high / above maximum
    bad_high = list(VALID_24)
    bad_high[-1] = 850.0
    with pytest.raises(HTTPException) as exc_info:
        validate_input_sequence(bad_high)
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "PhysiologicallyInvalidGlucose"
