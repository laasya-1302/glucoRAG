import math
from typing import Any, Optional
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


def _parse_event_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a naive datetime."""
    return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")).replace(tzinfo=None)


def validate_multimodal_events(
    bolus_events: Optional[list],
    basal_events: Optional[list],
    carb_events: Optional[list],
    latest_dt: datetime
) -> tuple[Optional[list[dict]], Optional[list[dict]], Optional[list[dict]], list[str], str]:
    """
    Validate and normalize bolus, basal, and carb event lists.

    Three-state semantics:
      - None   => channel NOT AVAILABLE
      - []     => channel available, no events
      - [...]  => channel available with events

    Returns:
        (validated_bolus, validated_basal, validated_carbs, inputs_used, mode)
    """
    # Strip timezone for naive comparison
    latest_naive = latest_dt.replace(tzinfo=None) if latest_dt.tzinfo else latest_dt

    def _coerce_list(events):
        """Convert Pydantic models in list to plain dicts."""
        if events is None:
            return None
        return [ev.model_dump() if hasattr(ev, "model_dump") else dict(ev) for ev in events]

    bolus_events = _coerce_list(bolus_events)
    basal_events = _coerce_list(basal_events)
    carb_events = _coerce_list(carb_events)

    # Validate bolus events
    validated_bolus = None
    if bolus_events is not None:
        validated_bolus = []
        for ev in bolus_events:
            ts_str = ev.get("timestamp")
            if not ts_str:
                continue
            try:
                edt = _parse_event_timestamp(ts_str)
            except (ValueError, TypeError) as e:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "InvalidEventTimestamp",
                        "message": f"Could not parse bolus event timestamp '{ts_str}': {e}"
                    }
                )
            if edt > latest_naive:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "FutureDatedEvent",
                        "message": f"Bolus event timestamp '{ts_str}' is after the latest glucose reading time '{latest_naive.isoformat()}'."
                    }
                )
            units = float(ev.get("units", ev.get("value", 0.0)))
            if units < 0 or units > 40:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "InvalidBolusUnits",
                        "message": f"Bolus units {units} is outside the valid range [0, 40] U."
                    }
                )
            validated_bolus.append({**ev, "units": units})

    # Validate basal events
    validated_basal = None
    if basal_events is not None:
        validated_basal = []
        for ev in basal_events:
            ts_str = ev.get("timestamp")
            if not ts_str:
                continue
            try:
                edt = _parse_event_timestamp(ts_str)
            except (ValueError, TypeError) as e:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "InvalidEventTimestamp",
                        "message": f"Could not parse basal event timestamp '{ts_str}': {e}"
                    }
                )
            if edt > latest_naive:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "FutureDatedEvent",
                        "message": f"Basal event timestamp '{ts_str}' is after the latest glucose reading time '{latest_naive.isoformat()}'."
                    }
                )
            rate = float(ev.get("rate", 0.0))
            if rate < 0 or rate > 5:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "InvalidBasalRate",
                        "message": f"Basal rate {rate} U/h is outside the valid range [0, 5] U/h."
                    }
                )
            validated_basal.append({**ev, "rate": rate})

    # Validate carb events
    validated_carbs = None
    if carb_events is not None:
        validated_carbs = []
        for ev in carb_events:
            ts_str = ev.get("timestamp")
            if not ts_str:
                continue
            try:
                edt = _parse_event_timestamp(ts_str)
            except (ValueError, TypeError) as e:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "InvalidEventTimestamp",
                        "message": f"Could not parse carb event timestamp '{ts_str}': {e}"
                    }
                )
            if edt > latest_naive:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "FutureDatedEvent",
                        "message": f"Carb event timestamp '{ts_str}' is after the latest glucose reading time '{latest_naive.isoformat()}'."
                    }
                )
            carbs = float(ev.get("carbs", ev.get("grams", ev.get("value", 0.0))))
            if carbs < 0 or carbs > 370:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "InvalidCarbAmount",
                        "message": f"Carb amount {carbs} g is outside the valid range [0, 370] g."
                    }
                )
            validated_carbs.append({**ev, "carbs": carbs})

    # Determine mode and inputs_used
    any_events = (validated_bolus is not None or validated_basal is not None or validated_carbs is not None)
    mode = "E1" if any_events else "E1_cgmonly"

    inputs_used = ["glucose", "time"]
    if validated_bolus is not None:
        inputs_used.append("bolus")
    if validated_basal is not None:
        inputs_used.append("basal")
    if validated_carbs is not None:
        inputs_used.append("carbs")

    return validated_bolus, validated_basal, validated_carbs, inputs_used, mode
