import math
from typing import Any, Optional
from datetime import datetime, timedelta
from fastapi import HTTPException
from .config import settings

def parse_iso_dt(ts_val: Any) -> datetime:
    if isinstance(ts_val, datetime):
        return ts_val.replace(tzinfo=None)
    clean_ts = str(ts_val).replace("Z", "+00:00")
    return datetime.fromisoformat(clean_ts).replace(tzinfo=None)

def validate_input_sequence(
    readings: list[Any],
    latest_timestamp_str: str | None = None
) -> tuple[list[float], datetime]:
    """
    Validates the 24 glucose readings and timestamp for standard manual mode.
    """
    validated, latest_dt, _ = validate_forecast_inputs(readings, latest_timestamp_str, grid="manual")
    return validated, latest_dt

def validate_forecast_inputs(
    readings: list[Any],
    latest_timestamp_str: Optional[str] = None,
    grid: str = "manual",
    units: str = "mg/dL"
) -> tuple[list[float], datetime, list[datetime]]:
    """
    Validates glucose sequence under 'manual' or 'clock' grid modes:
    - 'manual': exactly 24 readings 15 minutes apart. Uses individual timestamps if supplied, else computed from latest_dt.
    - 'clock': streamed data resampled to 15-minute clock marks (nearest reading within +/-2.5 min, never filled).
      Requires 24 consecutive slots, else raises 422 'Collecting data: N of 24 readings'.
    """
    if not isinstance(readings, list):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "InvalidInputFormat",
                "message": f"Expected a JSON list for 'readings', received {type(readings).__name__}."
            }
        )

    clean_units = units.strip()
    if clean_units.lower() not in ("mg/dl", "mgdl"):
        raise HTTPException(
            status_code=422,
            detail={"error": "UnsupportedUnits", "message": f"Unsupported glucose units '{units}'. Expected 'mg/dL'."}
        )

    # 1. Clock Grid Mode
    if grid.lower() == "clock":
        # Extract all reading items with timestamp and numeric value
        extracted_stream: list[tuple[datetime, float]] = []
        for idx, item in enumerate(readings):
            g_val = None
            t_val = None
            if isinstance(item, dict):
                g_val = item.get("glucose")
                t_val = item.get("timestamp") or item.get("time")
            elif hasattr(item, "glucose"):
                g_val = getattr(item, "glucose")
                t_val = getattr(item, "timestamp", None) or getattr(item, "time", None)

            if g_val is None or t_val is None:
                continue
            try:
                dt_obj = parse_iso_dt(t_val)
                f_val = float(g_val)
                if not (math.isnan(f_val) or math.isinf(f_val)):
                    extracted_stream.append((dt_obj, f_val))
            except Exception:
                continue

        if latest_timestamp_str:
            ref_dt = parse_iso_dt(latest_timestamp_str)
        elif extracted_stream:
            ref_dt = max(dt for dt, _ in extracted_stream)
        else:
            ref_dt = datetime.now()

        # Build 24 clock marks: rounded to nearest 15m ending at ref_dt
        minute_round = (ref_dt.minute // 15) * 15
        clock_end = ref_dt.replace(minute=minute_round, second=0, microsecond=0)
        clock_marks = [clock_end - timedelta(minutes=(23 - i) * 15) for i in range(24)]

        resampled_readings: list[float] = []
        for mark in clock_marks:
            # Find nearest reading within +/- 2.5 minutes
            best_val = None
            best_diff = None
            for dt_obj, val in extracted_stream:
                diff_sec = abs((dt_obj - mark).total_seconds())
                if diff_sec <= 2.5 * 60:
                    if best_diff is None or diff_sec < best_diff:
                        best_diff = diff_sec
                        best_val = val
            if best_val is not None:
                resampled_readings.append(best_val)

        matched_count = len(resampled_readings)
        if matched_count < 24:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "CollectingData",
                    "code": "collecting_data",
                    "message": f"Collecting data: {matched_count} of 24 readings",
                    "count": matched_count,
                    "expected": 24
                }
            )
        return resampled_readings, clock_end, clock_marks

    # 2. Manual Grid Mode
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
    slot_dts: list[datetime] = []
    has_individual_timestamps = True
    extracted_timestamp = latest_timestamp_str

    for idx, item in enumerate(readings):
        val = item
        item_ts = None
        if isinstance(item, dict):
            val = item.get("glucose")
            item_ts = item.get("timestamp") or item.get("time")
            if idx == count - 1 and not extracted_timestamp and item_ts:
                extracted_timestamp = item_ts
        elif hasattr(item, "glucose"):
            val = getattr(item, "glucose")
            item_ts = getattr(item, "timestamp", None) or getattr(item, "time", None)
            if idx == count - 1 and not extracted_timestamp and item_ts:
                extracted_timestamp = item_ts

        if not item_ts:
            has_individual_timestamps = False
        else:
            try:
                slot_dts.append(parse_iso_dt(item_ts))
            except Exception:
                has_individual_timestamps = False

        if val is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "MissingReading",
                    "index": idx,
                    "message": (
                        f"Reading at index {idx} (-{(23 - idx) * 15} min) is missing (null/None). "
                        "The GPFormer architecture requires an uninterrupted 24-point sequence."
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
                        f"physiological range [{settings.MIN_GLUCOSE_MG_DL}, {settings.MAX_GLUCOSE_MG_DL}] mg/dL."
                    )
                }
            )

        validated_readings.append(round(num, 2))

    if extracted_timestamp:
        try:
            parsed_dt = parse_iso_dt(extracted_timestamp)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "InvalidTimestampFormat",
                    "message": f"Could not parse timestamp ('{extracted_timestamp}'). Expected ISO 8601 format."
                }
            )
    elif has_individual_timestamps and slot_dts:
        parsed_dt = slot_dts[-1]
    else:
        parsed_dt = datetime.now()

    if not has_individual_timestamps or len(slot_dts) != 24:
        start_dt = parsed_dt - timedelta(minutes=(settings.INPUT_STEPS - 1) * 15)
        slot_dts = [start_dt + timedelta(minutes=i * 15) for i in range(settings.INPUT_STEPS)]

    return validated_readings, parsed_dt, slot_dts
