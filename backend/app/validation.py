import math
from typing import Any
from datetime import datetime
from fastapi import HTTPException
from .config import settings

def validate_input_sequence(readings: list[Any], latest_timestamp_str: str | None = None) -> tuple[list[float], datetime]:
    """
    Validates the 24 glucose readings and timestamp:
    - Must be exactly 24 readings.
    - Each reading can be a number, dict, or object with a 'glucose' field.
    - Each reading must be a valid finite number.
    - Readings must be within physiological glucose limits (settings.MIN_GLUCOSE_MG_DL to settings.MAX_GLUCOSE_MG_DL).
    - Missing readings (None / NaN / Inf) are rejected with clear explanation.
    - Timestamp must be valid ISO 8601 if supplied, otherwise defaults to now or the timestamp of the 24th reading.
    """
    if not isinstance(readings, list):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "InvalidInputFormat",
                "message": f"Expected a JSON list of numbers or reading objects for 'readings', received {type(readings).__name__}."
            }
        )

    count = len(readings)
    if count != settings.INPUT_STEPS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "InvalidSequenceLength",
                "message": (
                    f"The model requires exactly {settings.INPUT_STEPS} chronological glucose readings "
                    f"representing 6 hours at 15-minute intervals. Received {count} reading(s). "
                    "Missing values cannot be silently invented or imputed."
                ),
                "expected_count": settings.INPUT_STEPS,
                "received_count": count
            }
        )

    validated_readings: list[float] = []
    extracted_timestamp = latest_timestamp_str

    for idx, item in enumerate(readings):
        val = item
        if isinstance(item, dict):
            val = item.get("glucose")
            if idx == count - 1 and not extracted_timestamp and item.get("timestamp"):
                extracted_timestamp = item.get("timestamp")
        elif hasattr(item, "glucose"):
            val = getattr(item, "glucose")
            if idx == count - 1 and not extracted_timestamp and getattr(item, "timestamp", None):
                extracted_timestamp = getattr(item, "timestamp")

        if val is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "MissingReading",
                    "index": idx,
                    "message": (
                        f"Reading at index {idx} (-{(23 - idx) * 15} min) is missing (null/None). "
                        "The GPFormer architecture requires an uninterrupted 24-point sequence. "
                        "Do not silently impute missing CGM readings; please provide a continuous 6-hour segment."
                    )
                }
            )

        try:
            num = float(val)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "NonNumericReading",
                    "index": idx,
                    "message": f"Reading at index {idx} is non-numeric: '{val}'."
                }
            )

        if math.isnan(num) or math.isinf(num):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "NonFiniteReading",
                    "index": idx,
                    "message": f"Reading at index {idx} is non-finite (NaN or Infinite)."
                }
            )

        if num < settings.MIN_GLUCOSE_MG_DL or num > settings.MAX_GLUCOSE_MG_DL:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "PhysiologicallyInvalidGlucose",
                    "index": idx,
                    "value": num,
                    "message": (
                        f"Reading at index {idx} is {num:.1f} mg/dL, which falls outside the acceptable "
                        f"physiological range [{settings.MIN_GLUCOSE_MG_DL}, {settings.MAX_GLUCOSE_MG_DL}] mg/dL. "
                        "Please verify glucose meter/CGM data."
                    )
                }
            )

        validated_readings.append(round(num, 2))

    # Validate or initialize timestamp
    if extracted_timestamp:
        try:
            # Handle ISO formats including trailing 'Z'
            clean_ts = str(extracted_timestamp).replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(clean_ts)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "InvalidTimestampFormat",
                    "message": f"Could not parse timestamp ('{extracted_timestamp}'). Expected ISO 8601 format (e.g., '2026-10-27T12:00:00'). Error: {str(e)}"
                }
            )
    else:
        parsed_dt = datetime.now()

    return validated_readings, parsed_dt

    return validated_readings, parsed_dt
