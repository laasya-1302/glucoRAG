import os
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import torch

from .config import settings
from .models import (
    ForecastStep,
    QuantileDict,
    UncertaintyBand,
    RiskProbabilities,
    ClinicalAlert,
    InputSummary,
    PredictResponse,
    ExperimentDetails,
    ModelInfoResponse
)

# Ensure GPFormer repo and scripts are in sys.path
repo_dir_str = str(settings.REPO_DIR.resolve())
scripts_dir_str = str(settings.SCRIPTS_DIR.resolve())

if repo_dir_str not in sys.path:
    sys.path.insert(0, repo_dir_str)
if scripts_dir_str not in sys.path:
    sys.path.insert(0, scripts_dir_str)

import gp_model
from gp_data import make_marks, CLASSES, HYPO, HYPER, SEQ_LEN, LABEL_LEN, PRED_LEN, WIN

class GPFormerEngine:
    """
    Manages loading, caching, and inference of trained GPFormer models for Experiment A and B.
    """
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.loaded_models: dict[str, dict] = {}
        self.active_experiment = settings.DEFAULT_EXPERIMENT
        self._ensure_environment()

    def _ensure_environment(self):
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    def load_experiment(self, exp_name: str) -> dict:
        """
        Loads the trained checkpoint and run metadata once into memory for the requested experiment.
        """
        if exp_name in ("experiment_a", "a"):
            exp_name = "gp_A"
        elif exp_name in ("experiment_b", "b"):
            exp_name = "gp_B"

        if exp_name in self.loaded_models:
            return self.loaded_models[exp_name]

        run_path = settings.RUNS_DIR / exp_name
        ckpt_path = run_path / "best.pt"
        info_path = run_path / "run_info.json"

        if not run_path.exists():
            raise FileNotFoundError(f"Run directory for experiment '{exp_name}' does not exist: {run_path.name}")
        if not info_path.exists():
            raise FileNotFoundError(f"run_info.json missing for experiment '{exp_name}' at {info_path.name}")
        if not ckpt_path.exists():
            raise FileNotFoundError(f"best.pt checkpoint missing for experiment '{exp_name}' at {ckpt_path.name}")

        # Load run metadata
        info = json.loads(info_path.read_text())
        norm = info["norm"]
        arch = info["arch"]
        mark_dim = info.get("mark_dim", 2)

        # Build net
        net = gp_model.build_net(repo=str(settings.REPO_DIR), arch=arch, device=self.device)

        # Load state dict
        checkpoint = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        state_dict = checkpoint["model"] if isinstance(checkpoint, dict) and "model" in checkpoint else checkpoint
        net.load_state_dict(state_dict)
        net.eval()

        self.loaded_models[exp_name] = {
            "net": net,
            "info": info,
            "norm": norm,
            "mark_dim": mark_dim,
            "arch": arch,
            "epoch": checkpoint.get("epoch", 50) if isinstance(checkpoint, dict) else None,
            "val_mae": checkpoint.get("val") if isinstance(checkpoint, dict) else None,
        }
        return self.loaded_models[exp_name]

    def warmup(self):
        """Warm up all configured experiments at startup."""
        for exp in ["gp_A", "gp_B"]:
            try:
                self.load_experiment(exp)
            except Exception as e:
                print(f"[Warning] Could not load experiment '{exp}': {e}")

    def is_ready(self) -> bool:
        if len(self.loaded_models) == 0:
            try:
                self.load_experiment(self.active_experiment)
            except Exception:
                pass
        return len(self.loaded_models) > 0

    def get_model_info(self) -> ModelInfoResponse:
        experiments_detail: list[ExperimentDetails] = []
        for exp in ["gp_A", "gp_B", "e1_gpformer"]:
            if exp == "e1_gpformer":
                experiments_detail.append(
                    ExperimentDetails(
                        experiment_id="e1_gpformer",
                        name="E1 Multimodal GPFormer (3-Seed Ensemble)",
                        description="Multi-horizon GPFormer with 9 input channels (CGM + Insulin + Carbs), 3-seed ensemble (s42, s123, s2026), and calibrated uncertainty intervals.",
                        checkpoint_available=True,
                        normalization_mean=159.93,
                        normalization_std=63.56,
                        training_sources=["REPLACE-BG", "HuPA", "D1NAMO"]
                    )
                )
                continue

            run_path = settings.RUNS_DIR / exp
            ckpt_path = run_path / "best.pt"
            info_path = run_path / "run_info.json"
            
            exists = ckpt_path.exists() and info_path.exists()
            norm_mean, norm_std, sources = 145.0, 55.0, []
            name = f"Experiment {exp.split('_')[-1]}"
            desc = f"GPFormer Model ({exp})"
            if exists:
                try:
                    info = json.loads(info_path.read_text())
                    norm_mean = info["norm"]["mean"]
                    norm_std = info["norm"]["std"]
                    sources = info.get("sources", [])
                    name = info.get("experiment_name", f"Experiment {exp.split('_')[-1]}")
                    desc = f"Trained on {', '.join(sources)}"
                except Exception:
                    pass

            experiments_detail.append(
                ExperimentDetails(
                    experiment_id=exp,
                    name=name,
                    description=desc,
                    checkpoint_available=exists,
                    normalization_mean=round(norm_mean, 2),
                    normalization_std=round(norm_std, 2),
                    training_sources=sources
                )
            )

        return ModelInfoResponse(
            active_experiment=self.active_experiment,
            input_sequence_length=settings.INPUT_STEPS,
            sampling_interval_minutes=settings.SAMPLING_INTERVAL_MINUTES,
            total_history_hours=round(settings.INPUT_STEPS * settings.SAMPLING_INTERVAL_MINUTES / 60.0, 1),
            forecast_horizon_steps=settings.PRED_STEPS,
            forecast_horizon_minutes=settings.PRED_STEPS * settings.SAMPLING_INTERVAL_MINUTES,
            quantiles_output=list(settings.QUANTILES),
            risk_classes=list(CLASSES),
            thresholds={"hypo": HYPO, "hyper": HYPER},
            available_experiments=experiments_detail
        )

    def predict(self, readings: list[float], latest_dt: datetime, experiment: str = "gp_A") -> PredictResponse:
        """
        Executes GPFormer inference given 24 readings and the latest timestamp.
        """
        exp_data = self.load_experiment(experiment)
        net = exp_data["net"]
        norm = exp_data["norm"]
        mark_dim = exp_data["mark_dim"]
        info = exp_data["info"]

        # 1. Compute 32 timestamps: 24 historical + 8 forecast (15-min intervals)
        # Reading 23 corresponds to latest_dt
        start_dt = latest_dt - timedelta(minutes=(SEQ_LEN - 1) * settings.SAMPLING_INTERVAL_MINUTES)
        all_dts = [start_dt + timedelta(minutes=i * settings.SAMPLING_INTERVAL_MINUTES) for i in range(WIN)]
        
        # Hours as float: hour + minute / 60 + second / 3600
        all_hours = [dt.hour + dt.minute / 60.0 + dt.second / 3600.0 for dt in all_dts]

        # 2. Pad glucose with dummy zeros for the 8 future steps to match to_tensors format
        g_full = np.array([readings + [0.0] * PRED_LEN], dtype=np.float32)
        h_full = np.array([all_hours], dtype=np.float32)

        # 3. Create tensors exactly as in gp_model.to_tensors
        gs = (g_full - norm["mean"]) / norm["std"]
        marks = make_marks(h_full, mark_dim)

        t = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(self.device)
        x = t(gs[:, :SEQ_LEN, None])                 # (1, 24, 1)
        xm = t(marks[:, :SEQ_LEN])                   # (1, 24, 2)
        ym = t(marks[:, SEQ_LEN - LABEL_LEN:])       # (1, 10, 2)

        # 4. Forward pass in eval mode without gradients
        net.eval()
        with torch.no_grad():
            q_norm, logits = net(x, xm, ym)
            q_mgdl = (q_norm * norm["std"] + norm["mean"]).squeeze(0).cpu().numpy() # (8, 5)
            probs = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()           # (8, 3)

        # 5. Format forecast steps
        forecast_steps: list[ForecastStep] = []
        worst_alert_status = "NORMAL"
        worst_alert_horizon = None

        for step_idx in range(PRED_LEN):
            step_num = step_idx + 1
            horizon_mins = step_num * settings.SAMPLING_INTERVAL_MINUTES
            step_dt = latest_dt + timedelta(minutes=horizon_mins)
            
            q_vals = q_mgdl[step_idx] # (5,) -> [q10, q25, q50, q75, q90]
            # Ensure quantile monotonicity bounds as in gp_eval.py
            lo = float(min(q_vals[0], q_vals[-1]))
            hi = float(max(q_vals[0], q_vals[-1]))
            med = float(q_vals[settings.MEDIAN_INDEX])
            
            p_vals = probs[step_idx] # [hypo, normal, hyper]
            hypo_prob = float(p_vals[0])
            norm_prob = float(p_vals[1])
            hyper_prob = float(p_vals[2])

            pred_class_idx = int(np.argmax(p_vals))
            pred_class_name = CLASSES[pred_class_idx]

            # Track clinical risk status
            if hypo_prob >= settings.HYPO_ALERT_PROBABILITY and worst_alert_status != "HYPO_RISK":
                worst_alert_status = "HYPO_RISK"
                worst_alert_horizon = horizon_mins
            elif hyper_prob >= 0.50 and worst_alert_status == "NORMAL":
                worst_alert_status = "HYPER_RISK"
                worst_alert_horizon = horizon_mins

            forecast_steps.append(
                ForecastStep(
                    step=step_num,
                    horizon_minutes=horizon_mins,
                    timestamp=step_dt.isoformat(),
                    glucose_median=round(med, 1),
                    quantiles=QuantileDict(
                        q10=round(float(q_vals[0]), 1),
                        q25=round(float(q_vals[1]), 1),
                        q50=round(med, 1),
                        q75=round(float(q_vals[3]), 1),
                        q90=round(float(q_vals[4]), 1)
                    ),
                    uncertainty_band=UncertaintyBand(
                        low_q10=round(lo, 1),
                        high_q90=round(hi, 1),
                        bandwidth=round(hi - lo, 1)
                    ),
                    risk_probabilities=RiskProbabilities(
                        hypo=round(hypo_prob, 4),
                        normal=round(norm_prob, 4),
                        hyper=round(hyper_prob, 4)
                    ),
                    predicted_risk_class=pred_class_name
                )
            )

        # 6. Formulate clinical alert summary message
        if worst_alert_status == "HYPO_RISK":
            alert_msg = f"HYPO RISK: low glucose (< 70 mg/dL) possible by about +{worst_alert_horizon} min (alert probability >= {settings.HYPO_ALERT_PROBABILITY:.0%})."
        elif worst_alert_status == "HYPER_RISK":
            alert_msg = f"HYPER RISK: high glucose (> 180 mg/dL) likely by about +{worst_alert_horizon} min."
        else:
            alert_msg = "NORMAL: No acute low or high glucose excursion predicted across the 2-hour window."

        clinical_alert = ClinicalAlert(
            status=worst_alert_status,
            message=alert_msg,
            alert_horizon_minutes=worst_alert_horizon
        )

        input_summary = InputSummary(
            count=len(readings),
            latest_glucose_mg_dl=round(readings[-1], 1),
            latest_timestamp=latest_dt.isoformat(),
            sampling_interval_minutes=settings.SAMPLING_INTERVAL_MINUTES,
            mean_glucose_mg_dl=round(float(np.mean(readings)), 1),
            min_glucose_mg_dl=round(float(np.min(readings)), 1),
            max_glucose_mg_dl=round(float(np.max(readings)), 1)
        )

        exp_desc = info.get("experiment_name", f"GPFormer {experiment}")

        return PredictResponse(
            status="success",
            experiment=experiment,
            experiment_description=exp_desc,
            units="mg/dL",
            input_summary=input_summary,
            forecast=forecast_steps,
            clinical_alert=clinical_alert,
            model_version="GPFormer-v1.0 (MLDG + Quantile Decoder + Multi-Task Risk Head)",
            disclaimer=(
                "EXPERIMENTAL MODEL PREDICTION ONLY. Forecasts are generated by a research neural network "
                "and must not be used as clinical diagnostic criteria, CGM replacement, or insulin dosing guidance. "
                "Always verify readings with an approved medical CGM or fingerstick glucometer."
            )
        )

# Global singleton engine
engine = GPFormerEngine()
