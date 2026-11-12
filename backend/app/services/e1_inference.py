import os
import sys
import json
import math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any
import numpy as np
import torch
import torch.nn as nn
from argparse import Namespace

# Ensure project paths are available
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MODEL_V2_DIR = PROJECT_ROOT / "model_v2"
GPFORMER_THIRDPARTY = MODEL_V2_DIR / "third_party" / "gpformer"

if str(GPFORMER_THIRDPARTY) not in sys.path:
    sys.path.insert(0, str(GPFORMER_THIRDPARTY))

from models import GPFormer

IN_LEN = 24
OUT_LEN = 8
N_FEAT = 9
HORIZONS = [15, 30, 45, 60, 75, 90, 105, 120]
EVAL_HORIZONS = [30, 60, 90, 120]
POS_MAP = {15: 0, 30: 1, 45: 2, 60: 3, 75: 4, 90: 5, 105: 6, 120: 7}
CLASSES = ("HYPO", "NORMAL", "HYPER")
EVENT_CLIP = 3.0

class GPBackbone(nn.Module):
    """
    Exact GPBackbone module from model_v2/src/train.py.
    Uses enc_in=7, dec_in=7, c_out=5.
    """
    def __init__(self):
        super().__init__()
        cfg = Namespace(
            pred_len=8,
            output_attention=False,
            enc_in=7,
            dec_in=7,
            c_out=5,
            d_model=128,
            n_heads=8,
            e_layers=3,
            d_layers=1,
            d_ff=2048,
            dropout=0.05,
            factor=1,
            activation="gelu",
            embed="cycF",
            freq="cyc"
        )
        self.m = GPFormer.Model(cfg).float()

    def forward(self, x):
        # x is (B, 24, 9)
        # xe takes channels: glucose(0), bolus(3), basal(4), carb(5), m_bolus(6), m_basal(7), m_carb(8)
        xe = x[..., [0, 3, 4, 5, 6, 7, 8]]
        ang = torch.atan2(x[..., 1], x[..., 2])
        xm = torch.stack([torch.sin(ang), torch.cos(ang)], -1)
        off = torch.arange(-1, 9, device=x.device, dtype=x.dtype).view(1, -1) * (15.0 / 1440.0 * 2 * np.pi)
        a2 = ang[:, -1:] + off
        ym = torch.stack([torch.sin(a2), torch.cos(a2)], -1)
        dec = torch.cat([xe[:, -2:, :], torch.zeros(x.size(0), 8, 7, device=x.device, dtype=x.dtype)], 1)
        return self.m(xe, xm, dec, ym)

class Net(nn.Module):
    """
    Exact Net wrapper module from model_v2/src/train.py.
    Includes residual connection, quantile sorting, and 7-to-3 risk head.
    """
    def __init__(self, bb: GPBackbone, residual: bool = True):
        super().__init__()
        self.bb = bb
        self.res = residual
        self.risk = nn.Sequential(nn.Linear(7, 32), nn.GELU(), nn.Linear(32, 3))

    def forward(self, x):
        q = self.bb(x)
        last = x[:, -1:, 0:1]
        if self.res:
            q = q + last
        q = torch.sort(q, -1).values
        pos = torch.linspace(1 / 8, 1, 8, device=x.device).view(1, -1, 1).expand(x.size(0), -1, -1)
        return q, self.risk(torch.cat([q, last.expand(-1, 8, -1), pos], -1))

class E1InferenceService:
    """
    Production service managing the 3-seed ensemble of E1 Multimodal GPFormer:
    - s42, s123, s2026 checkpoints
    - scalers_v1.json normalization
    - frozen_eval_v1.json risk thresholds and uncertainty band calibration
    - multimodal (CGM + insulin + carbs) and CGM-only inference

    Three-state channel semantics:
      - None   => channel NOT AVAILABLE (value=0, mask=0)
      - []     => channel available, no events (value=0, mask=1)
      - [...]  => channel available with events (values summed/carry-fwd, mask=1 where events exist)
    """
    def __init__(self):
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.models: dict[str, Net] = {}
        self.scalers: dict[str, Any] = {}
        self.frozen_eval: dict[str, Any] = {}
        self._is_loaded = False
        self.load_artifacts()

    def load_artifacts(self):
        """Loads scalers, evaluation manifests, and the 3 trained checkpoints."""
        scalers_path = MODEL_V2_DIR / "manifests" / "scalers_v1.json"
        if not scalers_path.exists():
            raise FileNotFoundError(f"E1 scalers not found at {scalers_path}")
        with open(scalers_path, "r", encoding="utf-8") as f:
            self.scalers = json.load(f)

        frozen_eval_path = MODEL_V2_DIR / "manifests" / "frozen_eval_v1.json"
        if not frozen_eval_path.exists():
            raise FileNotFoundError(f"E1 frozen eval manifest not found at {frozen_eval_path}")
        with open(frozen_eval_path, "r", encoding="utf-8") as f:
            self.frozen_eval = json.load(f)

        seeds = ["s42", "s123", "s2026"]
        for s in seeds:
            ckpt_path = MODEL_V2_DIR / "runs" / f"E1_gpf_multi_pooled_{s}" / "best.pt"
            if not ckpt_path.exists():
                raise FileNotFoundError(f"E1 checkpoint {s} not found at {ckpt_path}")
            
            bb = GPBackbone()
            net = Net(bb, residual=True).to(self.device)
            ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
            state_dict = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt
            net.load_state_dict(state_dict)
            net.eval()
            self.models[s] = net

        self._is_loaded = True

    # def is_ready(self) -> bool:
    #     return self._is_loaded and len(self.models) == 3
    def warmup(self):
        """Ensure the E1 ensemble is loaded before serving requests."""
        if not self.is_ready():
            self.load_artifacts()

        if not self.is_ready():
            raise RuntimeError("E1 GPFormer ensemble failed to load.")

        print("[INFO] E1 Multimodal GPFormer 3-seed ensemble is ready.")

    def is_ready(self) -> bool:
        return self._is_loaded and len(self.models) == 3
        
    def preprocess(
        self,
        readings: list[float],
        latest_dt: datetime,
        bolus_events: Optional[list[dict]] = None,
        basal_events: Optional[list[dict]] = None,
        carb_events: Optional[list[dict]] = None,
        # Backward compat: insulin_events treated as bolus_events
        insulin_events: Optional[list[dict]] = None,
    ) -> tuple[np.ndarray, str, list[str]]:
        """
        Builds the (1, 24, 9) feature tensor using the exact training-time preprocessing:
        0: glucose (scaled by (g - mu) / sd)
        1: sin_tod (sin of time-of-day in minutes)
        2: cos_tod (cos of time-of-day in minutes)
        3: bolus (clip(bolus / cap, 0, 3.0))
        4: basal (clip(basal / cap, 0, 3.0)) - carry-forward logic
        5: carb (clip(carb / cap, 0, 3.0))
        6: m_bolus (1.0 if channel available, 0.0 if NOT AVAILABLE)
        7: m_basal (1.0 if channel available, 0.0 if NOT AVAILABLE)
        8: m_carb  (1.0 if channel available, 0.0 if NOT AVAILABLE)

        Three-state channel semantics:
          - None   => NOT AVAILABLE: value=0, mask=0
          - []     => AVAILABLE, no events: value=0, mask=1 (all slots)
          - [...]  => AVAILABLE with events: values filled, mask=1 where event present (or globally if available)
        """
        # Backward compat: if only insulin_events is passed, treat it as bolus_events
        if bolus_events is None and insulin_events is not None:
            bolus_events = insulin_events

        if len(readings) != IN_LEN:
            raise ValueError(f"E1 GPFormer requires exactly {IN_LEN} readings, got {len(readings)}.")

        mu = self.scalers["glucose"]["mean"]
        sd = self.scalers["glucose"]["std"]
        caps = self.scalers["event_caps"]

        # Build timestamps for the 24 intervals
        # Reading 23 corresponds to latest_dt, reading 0 is latest_dt - 23*15min
        start_dt = latest_dt - timedelta(minutes=(IN_LEN - 1) * 15)
        step_dts = [start_dt + timedelta(minutes=i * 15) for i in range(IN_LEN)]

        x = np.zeros((1, IN_LEN, N_FEAT), dtype=np.float32)

        # 0: Normalized glucose
        g_arr = np.asarray(readings, dtype=np.float32)
        x[0, :, 0] = (g_arr - mu) / sd

        # 1, 2: Sin & Cos Time of Day
        tod_minutes = np.array([dt.hour * 60.0 + dt.minute + dt.second / 60.0 for dt in step_dts], dtype=np.float32)
        ang = tod_minutes / 1440.0 * 2 * np.pi
        x[0, :, 1] = np.sin(ang)
        x[0, :, 2] = np.cos(ang)

        def find_bolus_bucket(event_dt: datetime) -> Optional[int]:
            """
            Find the slot for a bolus/carb event.
            Uses ceil logic: event at 12:07 -> slot at 12:15 (first slot AT OR AFTER event time).
            Equivalent to: idx = ceil(diff_mins / 15)
            """
            diff_mins = (event_dt - start_dt).total_seconds() / 60.0
            idx = math.ceil(diff_mins / 15.0)
            if 0 <= idx < IN_LEN:
                return idx
            return None

        # --- Bolus channel (3) and m_bolus mask (6) ---
        if bolus_events is None:
            # NOT AVAILABLE: value=0, mask=0 (already zero from np.zeros)
            pass
        else:
            # AVAILABLE: set mask=1 for all slots initially; then overwrite with event values
            x[0, :, 6] = 1.0  # m_bolus = 1 for all slots (channel available)
            for ev in bolus_events:
                try:
                    ts_str = ev.get("timestamp")
                    if not ts_str:
                        continue
                    edt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    b_idx = find_bolus_bucket(edt)
                    if b_idx is not None:
                        units = float(ev.get("units", ev.get("value", 0.0)))
                        x[0, b_idx, 3] += units
                except Exception:
                    continue
            # Scale and clip bolus channel
            x[0, :, 3] = np.clip(x[0, :, 3] / caps["bolus_u"], 0.0, EVENT_CLIP)

        # --- Basal channel (4) and m_basal mask (7) with carry-forward logic ---
        if basal_events is None:
            # NOT AVAILABLE: value=0, mask=0 (already zero from np.zeros)
            pass
        else:
            # AVAILABLE: set mask=1 for all slots initially
            x[0, :, 7] = 1.0  # m_basal = 1 for all slots (channel available)
            if basal_events:
                # Parse all basal events into (datetime, rate) tuples
                parsed_basal = []
                for ev in basal_events:
                    try:
                        ts_str = ev.get("timestamp")
                        if not ts_str:
                            continue
                        edt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
                        rate = float(ev.get("rate", 0.0))
                        parsed_basal.append((edt, rate))
                    except Exception:
                        continue

                # Sort by time
                parsed_basal.sort(key=lambda t: t[0])

                # Carry-forward: for each slot, find the latest basal event at or before slot time
                # Also check events up to 24h before the window start
                cutoff = start_dt - timedelta(hours=24)
                for i, slot_dt in enumerate(step_dts):
                    # Find the latest event with edt <= slot_dt and edt >= cutoff
                    best_rate = None
                    for edt, rate in parsed_basal:
                        if edt <= slot_dt and edt >= cutoff:
                            best_rate = rate
                        elif edt > slot_dt:
                            break
                    if best_rate is not None:
                        x[0, i, 4] = best_rate

                # Scale and clip basal channel
                x[0, :, 4] = np.clip(x[0, :, 4] / caps["basal_uh"], 0.0, EVENT_CLIP)

        # --- Carb channel (5) and m_carb mask (8) ---
        if carb_events is None:
            # NOT AVAILABLE: value=0, mask=0 (already zero from np.zeros)
            pass
        else:
            # AVAILABLE: set mask=1 for all slots initially
            x[0, :, 8] = 1.0  # m_carb = 1 for all slots (channel available)
            for ev in carb_events:
                try:
                    ts_str = ev.get("timestamp")
                    if not ts_str:
                        continue
                    edt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    b_idx = find_bolus_bucket(edt)
                    if b_idx is not None:
                        carbs = float(ev.get("carbs", ev.get("grams", ev.get("value", 0.0))))
                        x[0, b_idx, 5] += carbs
                except Exception:
                    continue
            # Scale and clip carb channel
            x[0, :, 5] = np.clip(x[0, :, 5] / caps["carb_g"], 0.0, EVENT_CLIP)

        # Determine mode
        any_available = (bolus_events is not None or basal_events is not None or carb_events is not None)
        mode = "E1" if any_available else "E1_cgmonly"

        # Build inputs_used list
        inputs_used = ["glucose", "time"]
        if bolus_events is not None:
            inputs_used.append("bolus")
        if basal_events is not None:
            inputs_used.append("basal")
        if carb_events is not None:
            inputs_used.append("carbs")

        return x, mode

    @torch.inference_mode()
    def predict(
        self,
        readings: list[float],
        latest_dt: datetime,
        bolus_events: Optional[list[dict]] = None,
        basal_events: Optional[list[dict]] = None,
        carb_events: Optional[list[dict]] = None,
        # Backward compat: insulin_events treated as bolus_events
        insulin_events: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """
        Executes the 3-model ensemble inference and applies frozen calibration.

        Three-state channel semantics for bolus_events, basal_events, carb_events:
          - None   => NOT AVAILABLE (value=0, mask=0)
          - []     => AVAILABLE, no events (value=0, mask=1 for all slots)
          - [...]  => AVAILABLE with events
        """
        # Backward compat
        if bolus_events is None and insulin_events is not None:
            bolus_events = insulin_events

        x_np, mode = self.preprocess(
            readings, latest_dt,
            bolus_events=bolus_events,
            basal_events=basal_events,
            carb_events=carb_events
        )
        inputs_used = ["glucose", "time"]
        if bolus_events is not None:
            inputs_used.append("bolus")
        if basal_events is not None:
            inputs_used.append("basal")
        if carb_events is not None:
            inputs_used.append("carbs")
        x_tensor = torch.from_numpy(x_np).to(self.device)

        q_list = []
        p_list = []

        mu = self.scalers["glucose"]["mean"]
        sd = self.scalers["glucose"]["std"]

        for s, model in self.models.items():
            q_norm, logits = model(x_tensor)
            # Unscale quantiles: q * sd + mu
            q_mgdl = q_norm * sd + mu
            probs = torch.softmax(logits, dim=-1)
            q_list.append(q_mgdl.squeeze(0).cpu().numpy()) # (8, 5)
            p_list.append(probs.squeeze(0).cpu().numpy())  # (8, 3)

        # 3-Seed Ensemble Average
        q_ens = np.mean(q_list, axis=0) # (8, 5)
        p_ens = np.mean(p_list, axis=0) # (8, 3)

        # Calibration lookup from frozen_eval_v1.json
        calib_dict = self.frozen_eval.get(mode, self.frozen_eval.get("E1_cgmonly", {}))

        forecast_steps = []
        worst_alert_status = "NORMAL"
        worst_alert_horizon = None

        for step_idx in range(OUT_LEN):
            horizon_mins = (step_idx + 1) * 15
            step_dt = latest_dt + timedelta(minutes=horizon_mins)
            q_vals = q_ens[step_idx]
            p_vals = p_ens[step_idx]

            raw_lo = float(q_vals[0])
            raw_hi = float(q_vals[4])
            med = float(q_vals[2])

            # Apply calibration for 30, 60, 90, 120 or interpolated for intermediate steps
            h_key = str(horizon_mins)
            if h_key in calib_dict:
                info_h = calib_dict[h_key]
                lo_shift = float(info_h["band"]["lo_shift"])
                hi_shift = float(info_h["band"]["hi_shift"])
                hypo_thr = float(info_h["hypo"]["thr"])
                hyper_thr = float(info_h["hyper"]["thr"])
            else:
                # Interpolate shifts from nearest evaluation horizons
                # 15m borrows 30m; 45m borrows (30+60)/2; 75m borrows (60+90)/2; 105m borrows (90+120)/2
                if horizon_mins < 30:
                    ref = calib_dict.get("30", {})
                elif horizon_mins < 60:
                    ref = calib_dict.get("60", calib_dict.get("30", {}))
                elif horizon_mins < 90:
                    ref = calib_dict.get("90", calib_dict.get("60", {}))
                else:
                    ref = calib_dict.get("120", calib_dict.get("90", {}))
                
                lo_shift = float(ref.get("band", {}).get("lo_shift", 0.0))
                hi_shift = float(ref.get("band", {}).get("hi_shift", 0.0))
                hypo_thr = float(ref.get("hypo", {}).get("thr", 0.10))
                hyper_thr = float(ref.get("hyper", {}).get("thr", 0.35))

            calib_lo = round(raw_lo + lo_shift, 1)
            calib_hi = round(raw_hi + hi_shift, 1)
            # Ensure proper low <= high ordering
            if calib_lo > calib_hi:
                calib_lo, calib_hi = calib_hi, calib_lo

            hypo_prob = float(p_vals[0])
            normal_prob = float(p_vals[1])
            hyper_prob = float(p_vals[2])

            # Risk classification based on frozen evaluation calibrated threshold
            if hypo_prob >= hypo_thr:
                risk_class = "HYPO"
                if worst_alert_status != "HYPO_RISK":
                    worst_alert_status = "HYPO_RISK"
                    worst_alert_horizon = horizon_mins
            elif hyper_prob >= hyper_thr:
                risk_class = "HYPER"
                if worst_alert_status == "NORMAL":
                    worst_alert_status = "HYPER_RISK"
                    worst_alert_horizon = horizon_mins
            else:
                risk_class = "NORMAL"

            forecast_steps.append({
                "step": step_idx + 1,
                "horizon_minutes": horizon_mins,
                "timestamp": step_dt.isoformat(),
                "glucose_median": round(med, 1),
                "quantiles": {
                    "q10": round(float(q_vals[0]), 1),
                    "q25": round(float(q_vals[1]), 1),
                    "q50": round(med, 1),
                    "q75": round(float(q_vals[3]), 1),
                    "q90": round(float(q_vals[4]), 1)
                },
                "uncertainty_band": {
                    "low_q10": calib_lo,
                    "high_q90": calib_hi,
                    "bandwidth": round(calib_hi - calib_lo, 1)
                },
                "risk_probabilities": {
                    "hypo": round(hypo_prob, 4),
                    "normal": round(normal_prob, 4),
                    "hyper": round(hyper_prob, 4)
                },
                "predicted_risk_class": risk_class,
                "calibrated_thresholds": {
                    "hypo": round(hypo_thr, 4),
                    "hyper": round(hyper_thr, 4)
                }
            })

        if worst_alert_status == "HYPO_RISK":
            alert_msg = f"HYPO RISK: Low glucose (< 70 mg/dL) predicted by +{worst_alert_horizon} min."
        elif worst_alert_status == "HYPER_RISK":
            alert_msg = f"HYPER RISK: High glucose (> 180 mg/dL) predicted by +{worst_alert_horizon} min."
        else:
            alert_msg = "NORMAL: Stable glucose excursion predicted across the 2-hour forecast window."

        return {
            "mode": mode,
            "inputs_used": inputs_used,
            "forecast": forecast_steps,
            "clinical_alert": {
                "status": worst_alert_status,
                "message": alert_msg,
                "alert_horizon_minutes": worst_alert_horizon
            },
            "ensemble_seeds": ["s42", "s123", "s2026"],
            "model_version": "E1 Multimodal GPFormer (3-Seed Ensemble)",
            "disclaimer": (
                "EXPERIMENTAL MODEL PREDICTION ONLY. Forecasts are generated by a research neural network "
                "and must not be used as clinical diagnostic criteria, CGM replacement, or insulin dosing guidance. "
                "Always verify readings with an approved medical CGM or fingerstick glucometer."
            )
        }

# Global singleton
e1_service = E1InferenceService()
