import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .models import (
    PredictRequest, PredictResponse, HealthResponse, ModelInfoResponse,
    ForecastV1Request, ForecastV1Response, ModelsV1Response,
    InputSummary, HorizonSummary, ClinicalAlert
)
from .validation import validate_input_sequence, validate_forecast_inputs
from .inference import engine
from .services.e1_inference import e1_service
from .services.model_registry import (
    get_registered_models, is_model_supported, run_model_inference, normalize_model_id
)
from .routers.auth import router as auth_router
from .routers.chat import router as chat_router
from .routers.history import router as history_router
from .auth.security import require_complete_profile
from .db.database import db, UserRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("gpformer_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing GPFormer inference engines and warming up models...")
    try:
        engine.warmup()
        logger.info(f"Loaded legacy experiments: {list(engine.loaded_models.keys())}")
    except Exception as e:
        logger.error(f"Error during legacy model warmup: {e}", exc_info=True)

    try:
        e1_service.warmup()
        logger.info("Loaded E1 Multimodal GPFormer 3-seed ensemble.")
    except Exception as e:
        logger.error(f"Error during E1 model warmup: {e}", exc_info=True)

    yield
    logger.info("Shutting down GPFormer API...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Production-grade API for GPFormer multi-horizon glucose forecasting and clinical risk prediction.",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(history_router)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Clean HTTP error response without stack trace leakage."""
    detail = exc.detail
    if isinstance(detail, dict):
        content = detail
    else:
        content = {"error": "RequestError", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=content)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Generic error shield to prevent leaking private filesystem paths."""
    logger.error(f"Unhandled server error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "message": "An internal error occurred during model inference. Please verify inputs or consult server logs."
        }
    )

@app.get("/health", response_model=HealthResponse, tags=["Diagnostics"])
def health_check():
    """Reports API health and whether trained models are loaded in memory."""
    legacy_loaded = engine.is_ready()
    e1_loaded = e1_service.is_ready()
    is_loaded = legacy_loaded or e1_loaded
    return HealthResponse(
        status="healthy" if is_loaded else "degraded",
        api_online=True,
        model_loaded=is_loaded,
        current_experiment=engine.active_experiment,
        available_experiments=list(settings.AVAILABLE_EXPERIMENTS)
    )

@app.get("/model-info", response_model=ModelInfoResponse, tags=["Diagnostics"])
def model_info():
    """Reports configuration, forecast horizons, supported quantiles, and available experiments."""
    return engine.get_model_info()

@app.get("/v1/models", response_model=ModelsV1Response, tags=["Models"])
def get_models():
    """Lists all registered models, their capabilities, and checkpoint availability."""
    models_list = get_registered_models()
    return ModelsV1Response(models=models_list)

@app.post("/v1/forecast", response_model=ForecastV1Response, tags=["Inference"])
def forecast_v1(
    payload: ForecastV1Request,
    user: UserRecord = Depends(require_complete_profile)
):
    """
    Unified multi-horizon forecasting endpoint supporting E1 multimodal GPFormer
    as well as Experiment A and B checkpoints.
    Requires an authenticated user with a completed profile.
    """
    model_id = payload.model_id or "e1_gpformer"
    if not is_model_supported(model_id):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_model_id",
                "error": "InvalidModelId",
                "message": f"Model '{model_id}' is not recognized. Supported models: 'e1_gpformer', 'experiment_a', 'experiment_b'."
            }
        )

    validated_readings, latest_dt, slot_dts = validate_forecast_inputs(
        payload.readings,
        payload.latest_timestamp,
        grid=payload.grid or "manual",
        units=payload.units or "mg/dL"
    )

    try:
        insulin_evs = [ev.model_dump() if hasattr(ev, "model_dump") else ev for ev in (payload.insulin_events or [])] if payload.insulin_events is not None else None
        carb_evs = [ev.model_dump() if hasattr(ev, "model_dump") else ev for ev in (payload.carb_events or [])] if payload.carb_events is not None else None

        raw_result = run_model_inference(
            model_id=model_id,
            readings=validated_readings,
            latest_dt=latest_dt,
            slot_dts=slot_dts,
            bolus=payload.bolus,
            basal=payload.basal,
            carbs=payload.carbs,
            insulin_events=insulin_evs,
            carb_events=carb_evs
        )

        input_summary = InputSummary(
            count=len(validated_readings),
            latest_glucose_mg_dl=validated_readings[-1],
            latest_timestamp=latest_dt.isoformat(),
            sampling_interval_minutes=settings.SAMPLING_INTERVAL_MINUTES,
            mean_glucose_mg_dl=round(sum(validated_readings) / len(validated_readings), 1),
            min_glucose_mg_dl=min(validated_readings),
            max_glucose_mg_dl=max(validated_readings)
        )

        forecast_steps = raw_result["forecast"]
        
        # Horizons summary for +30m, +60m, +90m, +120m
        horizons_summary = {}
        forecast_30m = None
        forecast_60m = None
        forecast_90m = None
        forecast_120m = None

        for s in forecast_steps:
            h = s["horizon_minutes"] if isinstance(s, dict) else s.horizon_minutes
            med = s["glucose_median"] if isinstance(s, dict) else s.glucose_median
            q = s["quantiles"] if isinstance(s, dict) else s.quantiles
            p10 = q["q10"] if isinstance(q, dict) else q.q10
            p90 = q["q90"] if isinstance(q, dict) else q.q90
            r_cls = s["predicted_risk_class"] if isinstance(s, dict) else s.predicted_risk_class
            r_prob = s["risk_probabilities"] if isinstance(s, dict) else s.risk_probabilities

            if h == 30:
                forecast_30m = med
            elif h == 60:
                forecast_60m = med
            elif h == 90:
                forecast_90m = med
            elif h == 120:
                forecast_120m = med

            if h in (30, 60, 90, 120):
                horizons_summary[str(h)] = HorizonSummary(
                    horizon_minutes=h,
                    median=med,
                    p10=p10,
                    p90=p90,
                    risk_class=r_cls,
                    risk_probabilities=r_prob
                )

        alert_obj = raw_result.get("clinical_alert")
        if not alert_obj:
            hypo_steps = [s for s in forecast_steps if (s.get("alert") if isinstance(s, dict) else s.alert) == "Possible low glucose"]
            hyper_steps = [s for s in forecast_steps if (s.get("alert") if isinstance(s, dict) else s.alert) == "Possible high glucose"]
            if hypo_steps:
                h_min = hypo_steps[0]["horizon_minutes"] if isinstance(hypo_steps[0], dict) else hypo_steps[0].horizon_minutes
                alert_obj = ClinicalAlert(
                    status="HYPO_RISK",
                    message=f"Possible low glucose detected at +{h_min} min.",
                    alert_horizon_minutes=h_min
                )
            elif hyper_steps:
                h_min = hyper_steps[0]["horizon_minutes"] if isinstance(hyper_steps[0], dict) else hyper_steps[0].horizon_minutes
                alert_obj = ClinicalAlert(
                    status="HYPER_RISK",
                    message=f"Possible high glucose detected at +{h_min} min.",
                    alert_horizon_minutes=h_min
                )
            else:
                alert_obj = ClinicalAlert(
                    status="NORMAL",
                    message="No immediate hypo/hyperglycemic risk flags triggered.",
                    alert_horizon_minutes=None
                )
        elif isinstance(alert_obj, dict):
            alert_obj = ClinicalAlert(**alert_obj)

        resp = ForecastV1Response(
            status="success",
            model_id=raw_result["model_id"],
            model_name=raw_result["model_name"],
            mode=raw_result.get("mode", "cgm_only"),
            inputs_used=raw_result.get("inputs_used", ["cgm"]),
            units="mg/dL",
            forecast_origin=raw_result.get("forecast_origin", latest_dt.isoformat()),
            now_mgdl=raw_result.get("now_mgdl", float(validated_readings[-1])),
            checkpoint_sha256=raw_result.get("checkpoint_sha256"),
            input_summary=input_summary,
            forecast_30m=forecast_30m,
            forecast_60m=forecast_60m,
            forecast_90m=forecast_90m,
            forecast_120m=forecast_120m,
            forecast=forecast_steps,
            horizons_summary=horizons_summary,
            clinical_alert=alert_obj,
            inspector=raw_result.get("inspector"),
            model_version=raw_result.get("model_version", "1.0.0"),
            disclaimer=raw_result.get("disclaimer", "")
        )

        # Auto-save patient inputs & prediction results to history
        try:
            summary_str = f"Now: {validated_readings[-1]:.0f} mg/dL | +30m: {forecast_30m or '--'} mg/dL ({alert_obj.status})"
            inputs_data = {
                "readings": validated_readings,
                "latest_timestamp": latest_dt.isoformat(),
                "bolus": payload.bolus,
                "basal": payload.basal,
                "carbs": payload.carbs,
                "grid": payload.grid
            }
            results_data = {
                "forecast_30m": forecast_30m,
                "forecast_60m": forecast_60m,
                "forecast_90m": forecast_90m,
                "forecast_120m": forecast_120m,
                "clinical_alert": alert_obj.model_dump() if hasattr(alert_obj, "model_dump") else alert_obj,
                "forecast": forecast_steps
            }
            db.save_prediction(
                user_id=user.id if user else "patient-default",
                model_id=model_id,
                inputs=inputs_data,
                results=results_data,
                summary=summary_str
            )
        except Exception as save_err:
            logger.warning(f"Failed to auto-save forecast to database: {save_err}")

        return resp
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_input",
                "error": "ValidationError",
                "message": str(ve)
            }
        )
    except FileNotFoundError as fnf:
        logger.error(f"Model checkpoint not found: {fnf}")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "model_unavailable",
                "error": "ModelUnavailable",
                "message": f"Model checkpoints or manifests for '{model_id}' are unavailable on the server."
            }
        )
    except Exception as e:
        logger.error(f"Inference execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "inference_error",
                "error": "InferenceError",
                "message": f"Failed to compute model predictions: {str(e)}"
            }
        )

@app.post("/predict", response_model=PredictResponse, tags=["Inference"])
def predict_glucose(payload: PredictRequest):
    """
    Accepts exactly 24 chronological glucose readings in mg/dL and a timestamp.
    Executes GPFormer inference and returns 8-step quantile predictions and risk probabilities.
    Supports Experiment A, Experiment B, and E1 Multimodal GPFormer.
    """
    # 1. Validate input sequence
    validated_readings, latest_dt = validate_input_sequence(
        payload.readings,
        payload.latest_timestamp
    )

    # 2. Validate selected experiment/model
    selected_exp = payload.model_id or payload.experiment or settings.DEFAULT_EXPERIMENT
    norm_exp = normalize_model_id(selected_exp)

    if norm_exp == "e1_gpformer":
        try:
            insulin_evs = [ev.model_dump() if hasattr(ev, "model_dump") else ev for ev in (payload.insulin_events or [])]
            carb_evs = [ev.model_dump() if hasattr(ev, "model_dump") else ev for ev in (payload.carb_events or [])]
            res = e1_service.predict(
                readings=validated_readings,
                latest_dt=latest_dt,
                insulin_events=insulin_evs,
                carb_events=carb_evs
            )
            input_summary = InputSummary(
                count=len(validated_readings),
                latest_glucose_mg_dl=validated_readings[-1],
                latest_timestamp=latest_dt.isoformat(),
                sampling_interval_minutes=settings.SAMPLING_INTERVAL_MINUTES,
                mean_glucose_mg_dl=round(sum(validated_readings) / len(validated_readings), 1),
                min_glucose_mg_dl=min(validated_readings),
                max_glucose_mg_dl=max(validated_readings)
            )
            return PredictResponse(
                status="success",
                experiment="e1_gpformer",
                experiment_description="E1 Multimodal GPFormer (3-Seed Ensemble)",
                mode=res.get("mode", "cgm_only"),
                units="mg/dL",
                input_summary=input_summary,
                forecast=res["forecast"],
                clinical_alert=res["clinical_alert"],
                model_version=res["model_version"],
                disclaimer=res["disclaimer"]
            )
        except Exception as e:
            logger.error(f"E1 Inference execution failed in /predict: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "InferenceError",
                    "message": f"Failed to compute E1 predictions: {str(e)}"
                }
            )

    # For legacy experiments (gp_A, gp_B, experiment_a, experiment_b)
    exp = "gp_A" if norm_exp == "experiment_a" else ("gp_B" if norm_exp == "experiment_b" else selected_exp)
    if exp not in ("gp_A", "gp_B"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "InvalidExperiment",
                "message": f"Experiment '{selected_exp}' is not recognized. Supported options: {settings.AVAILABLE_EXPERIMENTS}"
            }
        )

    # 3. Execute legacy inference
    try:
        response = engine.predict(
            readings=validated_readings,
            latest_dt=latest_dt,
            experiment=exp
        )
        return response
    except FileNotFoundError as fnf:
        logger.error(f"Model file not found for experiment '{exp}': {fnf}")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ModelUnavailable",
                "message": f"Checkpoint or metadata files for experiment '{exp}' are unavailable on the server."
            }
        )
    except Exception as e:
        logger.error(f"Inference execution failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "InferenceError",
                "message": f"Failed to compute model predictions: {str(e)}"
            }
        )
