import os
import sys
import json
<<<<<<< HEAD
import hashlib
=======
import math
>>>>>>> origin/main
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any, Union
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

class PreprocessResult(tuple):
    def __new__(cls, x, mode, inputs_used, inspector=None):
        return super().__new__(cls, (x, mode, inputs_used))

    def __init__(self, x, mode, inputs_used, inspector=None):
        self.x = x
        self.mode = mode
        self.inputs_used = inputs_used
        self.inspector = inspector or {}

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
        self.checkpoint_hashes: dict[str, str] = {}
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
            
            # Compute sha256
            h = hashlib.sha256()
            with open(ckpt_path, "rb") as bf:
                while chunk := bf.read(65536):
                    h.update(chunk)
            self.checkpoint_hashes[s] = h.hexdigest()

            bb = GPBackbone()
            net = Net(bb, residual=True).to(self.device)
            ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
            state_dict = ckpt["model"] if isinstance(ckpt, dict) and "model" in ckpt else ckpt
            net.load_state_dict(state_dict)
            net.eval()
            self.models[s] = net

        self._is_loaded = True

<<<<<<< HEAD
    def warmup(self):
        """Warms up and verifies all 3 ensemble checkpoints are loaded."""
        if not self._is_loaded:
            self.load_artifacts()

=======
    # def is_ready(self) -> bool:
    #     return self._is_loaded and len(self.models) == 3
    def warmup(self):
        """Ensure the E1 ensemble is loaded before serving requests."""
        if not self.is_ready():
            self.load_artifacts()

        if not self.is_ready():
            raise RuntimeError("E1 GPFormer ensemble failed to load.")

        print("[INFO] E1 Multimodal GPFormer 3-seed ensemble is ready.")

>>>>>>> origin/main
    def is_ready(self) -> bool:
        return self._is_loaded and len(self.models) == 3
        
    def preprocess(
        self,
        readings: list[float],
<<<<<<< HEAD
        slot_dts: Union[list[datetime], datetime],
        bolus: Optional[list[dict]] = None,
        basal: Optional[Union[float, list[dict], dict]] = None,
        carbs: Optional[list[dict]] = None,
        insulin_events: Optional[list[dict]] = None,
        carb_events: Optional[list[dict]] = None
    ) -> tuple[np.ndarray, str, list[str]]:
        """
        Builds the (1, 24, 9) feature tensor using the exact model contract:
        - 24 slots, 15 minutes apart, oldest -> newest (slot 23 is now).
        - Channels:
          0: glucose = (mg/dL - mean) / std
          1: sin(2*pi*tod/1440)
          2: cos(2*pi*tod/1440)
          3: bolus = clip(units_in_slot / event_caps.bolus_u, 0, 3)
          4: basal = clip(rate_U_per_h / event_caps.basal_uh, 0, 3)
          5: carbs = clip(grams_in_slot / event_caps.carb_g, 0, 3)
          6, 7, 8: availability masks for bolus, basal, carbs
        - 3 states per input:
          * None: not available (value 0, mask 0)
          * []: available, none given (mask 1, value 0)
          * list: available with events (mask 1, values assigned to slots)
        - Slot mapping rule:
          * Event at time t goes into FIRST slot where t_slot >= t (12:07 -> 12:15 slot, never 12:00)
          * Events at latest reading go into last slot (23)
          * Events > latest reading, or < t_0 - 15min, are rejected with ValueError
          * Basal: latest rate record at or before each slot, valid up to 24h
        - Mode:
          * If bolus, basal, carbs are all None -> "cgm_only" (threshold key "E1_cgmonly")
          * If any supplied -> "multimodal" (threshold key "E1")
        """
        if isinstance(slot_dts, datetime):
            start_dt = slot_dts - timedelta(minutes=(IN_LEN - 1) * 15)
            slot_dts = [start_dt + timedelta(minutes=i * 15) for i in range(IN_LEN)]

        if bolus is None and basal is None and insulin_events:
            bolus_list = []
            basal_list = []
            for ev in insulin_events:
                t = ev.get("type", "bolus")
                if t == "basal":
                    basal_list.append(ev)
                else:
                    bolus_list.append(ev)
            bolus = bolus_list
            basal = basal_list if basal_list else None
        if carbs is None and carb_events:
            carbs = carb_events
=======
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
>>>>>>> origin/main

        if len(readings) != IN_LEN:
            raise ValueError(f"E1 GPFormer requires exactly {IN_LEN} readings, got {len(readings)}.")
        if len(slot_dts) != IN_LEN:
            raise ValueError(f"E1 GPFormer requires exactly {IN_LEN} slot timestamps, got {len(slot_dts)}.")

        mu = self.scalers["glucose"]["mean"]
        sd = self.scalers["glucose"]["std"]
        caps = self.scalers["event_caps"]

        t_first = slot_dts[0]
        t_last = slot_dts[-1]
        earliest_allowed = t_first - timedelta(minutes=15)

        x = np.zeros((1, IN_LEN, N_FEAT), dtype=np.float32)

        # 0: Normalized glucose
        g_arr = np.asarray(readings, dtype=np.float32)
        x[0, :, 0] = (g_arr - mu) / sd

        # 1, 2: Sin & Cos Time of Day (tod = minutes since midnight)
        tod_minutes = np.array([dt.hour * 60.0 + dt.minute + dt.second / 60.0 for dt in slot_dts], dtype=np.float32)
        ang = tod_minutes / 1440.0 * 2 * np.pi
        x[0, :, 1] = np.sin(ang)
        x[0, :, 2] = np.cos(ang)

<<<<<<< HEAD
        def parse_dt(val: Any) -> datetime:
            if isinstance(val, datetime):
                return val.replace(tzinfo=None)
            s = str(val).strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.fromisoformat(s).replace(tzinfo=None)

        slot_mapping = []
        rejected_events = []

        def assign_slot(event_dt: datetime, ev_type: str, raw_ev: Any, amount: float, unit: str) -> int:
            if event_dt > t_last:
                err_msg = f"Event time {event_dt.isoformat()} is after latest reading time {t_last.isoformat()}."
                rejected_events.append({"type": ev_type, "event": raw_ev, "reason": err_msg})
                raise ValueError(err_msg)
            if event_dt < earliest_allowed:
                err_msg = f"Event time {event_dt.isoformat()} is earlier than input window boundary {earliest_allowed.isoformat()}."
                rejected_events.append({"type": ev_type, "event": raw_ev, "reason": err_msg})
                raise ValueError(err_msg)
            for idx, s_dt in enumerate(slot_dts):
                if s_dt >= event_dt:
                    slot_mapping.append({
                        "type": ev_type,
                        "event_time": event_dt.isoformat(),
                        "slot_index": idx,
                        "slot_time": s_dt.isoformat(),
                        "amount": amount,
                        "unit": unit
                    })
                    return idx
            slot_mapping.append({
                "type": ev_type,
                "event_time": event_dt.isoformat(),
                "slot_index": 23,
                "slot_time": slot_dts[23].isoformat(),
                "amount": amount,
                "unit": unit
            })
            return 23

        inputs_used = ["cgm"]

        # Bolus handling
        if bolus is not None:
            inputs_used.append("bolus")
            x[0, :, 6] = 1.0 # m_bolus mask
            raw_bolus = np.zeros(IN_LEN, dtype=np.float32)
            for ev in bolus:
                ev_dt = parse_dt(ev.get("time") or ev.get("timestamp"))
                u = float(ev.get("units") if ev.get("units") is not None else ev.get("value", 0.0))
                if u < 0.0:
                    raise ValueError(f"Negative bolus amount: {u} U")
                if u > 40.0:
                    raise ValueError(f"Bolus amount exceeds maximum limit of 40 U: {u} U")
                s_idx = assign_slot(ev_dt, "bolus", ev, u, "U")
                raw_bolus[s_idx] += u
            x[0, :, 3] = np.clip(raw_bolus / caps["bolus_u"], 0.0, EVENT_CLIP)

        # Basal handling
        if basal is not None:
            inputs_used.append("basal")
            raw_basal = np.zeros(IN_LEN, dtype=np.float32)
            if isinstance(basal, (int, float)):
                rate = float(basal)
                if rate < 0.0 or rate > 5.0:
                    raise ValueError(f"Basal rate must be between 0 and 5 U/h, got {rate}")
                raw_basal[:] = rate
                x[0, :, 7] = 1.0
            elif isinstance(basal, list) and len(basal) == 0:
                # Available with nothing given -> mask 1, values 0
                x[0, :, 7] = 1.0
            else:
                # List or dict of rate records
                records = basal if isinstance(basal, list) else [basal]
                parsed_recs = []
                for rec in records:
                    rate = float(rec.get("rate") if rec.get("rate") is not None else rec.get("value", 0.0))
                    if rate < 0.0 or rate > 5.0:
                        raise ValueError(f"Basal rate must be between 0 and 5 U/h, got {rate}")
                    st_str = rec.get("start") or rec.get("started_at") or rec.get("timestamp")
                    start_dt = parse_dt(st_str) if st_str else (t_last - timedelta(hours=6))
                    end_str = rec.get("end") or rec.get("ended_at")
                    end_dt = parse_dt(end_str) if end_str else None
                    parsed_recs.append((start_dt, end_dt, rate))

                # For each slot, find latest basal record at or before that slot, valid up to 24h
                for idx, s_dt in enumerate(slot_dts):
                    valid_match = None
                    for st_dt, end_dt, rate in parsed_recs:
                        if st_dt <= s_dt:
                            if end_dt is None or s_dt <= end_dt:
                                if (s_dt - st_dt) <= timedelta(hours=24):
                                    if valid_match is None or st_dt > valid_match[0]:
                                        valid_match = (st_dt, rate)
                    if valid_match is not None:
                        raw_basal[idx] = valid_match[1]
                        x[0, idx, 7] = 1.0 # m_basal mask = 1
                    else:
                        raw_basal[idx] = 0.0
                        x[0, idx, 7] = 0.0 # m_basal mask = 0 if none
            x[0, :, 4] = np.clip(raw_basal / caps["basal_uh"], 0.0, EVENT_CLIP)

        # Carbs handling
        if carbs is not None:
            inputs_used.append("carbs")
            x[0, :, 8] = 1.0 # m_carb mask
            raw_carbs = np.zeros(IN_LEN, dtype=np.float32)
            for ev in carbs:
                ev_dt = parse_dt(ev.get("time") or ev.get("timestamp"))
                g = float(ev.get("carbs") if ev.get("carbs") is not None else (ev.get("grams") if ev.get("grams") is not None else ev.get("value", 0.0)))
                if g < 0.0:
                    raise ValueError(f"Negative carbohydrate amount: {g} g")
                if g > 370.0:
                    raise ValueError(f"Carbohydrate amount exceeds maximum limit of 370 g: {g} g")
                s_idx = assign_slot(ev_dt, "carbs", ev, g, "g")
                raw_carbs[s_idx] += g
            x[0, :, 5] = np.clip(raw_carbs / caps["carb_g"], 0.0, EVENT_CLIP)

        if bolus is None and basal is None and carbs is None:
            mode = "cgm_only"
        else:
            mode = "multimodal"
=======
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
>>>>>>> origin/main

        inspector_data = {
            "channel_sums": {
                "channel_3_bolus_scaled_sum": round(float(np.sum(x[0, :, 3])), 4),
                "channel_4_basal_scaled_sum": round(float(np.sum(x[0, :, 4])), 4),
                "channel_5_carbs_scaled_sum": round(float(np.sum(x[0, :, 5])), 4),
                "channel_6_mask_bolus_sum": round(float(np.sum(x[0, :, 6])), 4),
                "channel_7_mask_basal_sum": round(float(np.sum(x[0, :, 7])), 4),
                "channel_8_mask_carbs_sum": round(float(np.sum(x[0, :, 8])), 4),
            },
            "event_to_slot_mapping": slot_mapping,
            "rejected_events": rejected_events,
            "mode": mode,
            "inputs_used": inputs_used
        }

        return PreprocessResult(x, mode, inputs_used, inspector=inspector_data)

    @torch.inference_mode()
    def predict(
        self,
        readings: list[float],
        latest_dt: datetime,
<<<<<<< HEAD
        slot_dts: Optional[list[datetime]] = None,
        bolus: Optional[list[dict]] = None,
        basal: Optional[Union[float, list[dict], dict]] = None,
        carbs: Optional[list[dict]] = None,
=======
        bolus_events: Optional[list[dict]] = None,
        basal_events: Optional[list[dict]] = None,
        carb_events: Optional[list[dict]] = None,
        # Backward compat: insulin_events treated as bolus_events
>>>>>>> origin/main
        insulin_events: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """
        Executes the 3-model ensemble inference and applies frozen calibration.

        Three-state channel semantics for bolus_events, basal_events, carb_events:
          - None   => NOT AVAILABLE (value=0, mask=0)
          - []     => AVAILABLE, no events (value=0, mask=1 for all slots)
          - [...]  => AVAILABLE with events
        """
<<<<<<< HEAD
        if bolus is None and basal is None and insulin_events:
            bolus_list = []
            basal_list = []
            for ev in insulin_events:
                t = ev.get("type", "bolus")
                if t == "basal":
                    basal_list.append(ev)
                else:
                    bolus_list.append(ev)
            bolus = bolus_list
            basal = basal_list if basal_list else None
        if carbs is None and carb_events:
            carbs = carb_events

        if slot_dts is None:
            start_dt = latest_dt - timedelta(minutes=(IN_LEN - 1) * 15)
            slot_dts = [start_dt + timedelta(minutes=i * 15) for i in range(IN_LEN)]

        prep_res = self.preprocess(
            readings=readings,
            slot_dts=slot_dts,
            bolus=bolus,
            basal=basal,
            carbs=carbs
        )
        x_np = prep_res.x if hasattr(prep_res, "x") else prep_res[0]
        mode = prep_res.mode if hasattr(prep_res, "mode") else prep_res[1]
        inputs_used = prep_res.inputs_used if hasattr(prep_res, "inputs_used") else prep_res[2]
        inspector_data = getattr(prep_res, "inspector", {})
=======
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
>>>>>>> origin/main
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
        calib_key = "E1_cgmonly" if mode == "cgm_only" else "E1"
        calib_dict = self.frozen_eval.get(calib_key, self.frozen_eval.get("E1_cgmonly", {}))

        forecast_steps = []
        forecast_origin = latest_dt.isoformat()
        now_mgdl = float(readings[-1])

        for step_idx in range(OUT_LEN):
            horizon_mins = (step_idx + 1) * 15
            step_dt = latest_dt + timedelta(minutes=horizon_mins)
            q_vals = q_ens[step_idx]
            p_vals = p_ens[step_idx]

            raw_lo = float(q_vals[0])
            raw_hi = float(q_vals[4])
            med = float(q_vals[2])

            is_validated = horizon_mins in EVAL_HORIZONS
            h_key = str(horizon_mins)

            if is_validated and h_key in calib_dict:
                info_h = calib_dict[h_key]
                lo_shift = float(info_h["band"]["lo_shift"])
                hi_shift = float(info_h["band"]["hi_shift"])
                hypo_thr = float(info_h["hypo"]["thr"])
                hyper_thr = float(info_h["hyper"]["thr"])
                calib_thresholds = {
                    "hypo": round(hypo_thr, 4),
                    "hyper": round(hyper_thr, 4)
                }
            else:
                # Intermediate horizons (+15, +45, +75, +105) are NOT validated:
                # Use nearest shift for display band, but NO alert thresholds and NO alert
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
                hypo_thr = None
                hyper_thr = None
                calib_thresholds = None

            calib_lo = round(raw_lo + lo_shift, 1)
            calib_hi = round(raw_hi + hi_shift, 1)
            if calib_lo > calib_hi:
                calib_lo, calib_hi = calib_hi, calib_lo

            hypo_prob = float(p_vals[0])
            normal_prob = float(p_vals[1])
            hyper_prob = float(p_vals[2])

            # 1. Forecast class derived STRICTLY from MEDIAN:
            # low < 70, normal 70-180 inclusive, high > 180
            if med < 70.0:
                f_class = "low"
                p_risk = "HYPO"
            elif med <= 180.0:
                f_class = "normal"
                p_risk = "NORMAL"
            else:
                f_class = "high"
                p_risk = "HYPER"

            # 2. Separate alert derived ONLY from frozen thresholds on validated horizons:
            if is_validated and hypo_thr is not None and hyper_thr is not None:
                if hypo_prob >= hypo_thr:
                    alert = "Possible low glucose"
                elif hyper_prob >= hyper_thr:
                    alert = "Possible high glucose"
                else:
                    alert = None
            else:
                alert = None

            forecast_steps.append({
                "step": step_idx + 1,
                "horizon_minutes": horizon_mins,
                "timestamp": step_dt.isoformat(),
                "median": round(med, 1),
                "glucose_median": round(med, 1), # backward compatibility
                "lo": calib_lo,
                "hi": calib_hi,
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
                "p_hypo": round(hypo_prob, 4),
                "p_normal": round(normal_prob, 4),
                "p_hyper": round(hyper_prob, 4),
                "risk_probabilities": {
                    "hypo": round(hypo_prob, 4),
                    "normal": round(normal_prob, 4),
                    "hyper": round(hyper_prob, 4)
                },
                "forecast_class": f_class,
                "predicted_risk_class": p_risk, # backward compatibility
                "alert": alert,
                "calibrated_thresholds": calib_thresholds,
                "is_validated": is_validated
            })

        hypo_steps = [s for s in forecast_steps if s["horizon_minutes"] in EVAL_HORIZONS and s.get("alert") == "Possible low glucose"]
        hyper_steps = [s for s in forecast_steps if s["horizon_minutes"] in EVAL_HORIZONS and s.get("alert") == "Possible high glucose"]
        if hypo_steps:
            h_min = hypo_steps[0]["horizon_minutes"]
            overall_alert = {
                "status": "HYPO_RISK",
                "message": f"Possible low glucose detected at +{h_min} min.",
                "alert_horizon_minutes": h_min
            }
        elif hyper_steps:
            h_min = hyper_steps[0]["horizon_minutes"]
            overall_alert = {
                "status": "HYPER_RISK",
                "message": f"Possible high glucose detected at +{h_min} min.",
                "alert_horizon_minutes": h_min
            }
        else:
            overall_alert = {
                "status": "NORMAL",
                "message": "No immediate hypo/hyperglycemic risk flags triggered.",
                "alert_horizon_minutes": None
            }

        return {
            "mode": mode,
            "inputs_used": inputs_used,
<<<<<<< HEAD
            "forecast_origin": forecast_origin,
            "now_mgdl": now_mgdl,
=======
>>>>>>> origin/main
            "forecast": forecast_steps,
            "clinical_alert": overall_alert,
            "inspector": inspector_data,
            "ensemble_seeds": ["s42", "s123", "s2026"],
            "model_name": "E1 Multimodal GPFormer",
            "model_version": "E1 Multimodal GPFormer (3-Seed Ensemble)",
            "checkpoint_sha256": self.checkpoint_hashes,
            "disclaimer": (
                "Research prototype. Not a medical device. Do not use for insulin dosing, "
                "treatment decisions or as a safety alert. A forecast of recovery must never "
                "delay treating or rechecking a low."
            )
        }

# Global singleton
e1_service = E1InferenceService()
