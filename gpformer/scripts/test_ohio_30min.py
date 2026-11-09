import argparse
import itertools
import os
import pickle
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import inspect

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
import pandas as pd
import torch

from args_generator import args_bglp
from layers.utils import QuantileLoss
from models import GPFormer
from preprocess_ohio import load_ohio_data
try:
    from torch.serialization import add_safe_globals  # PyTorch >= 2.6
except ImportError:  # pragma: no cover - compatibility for older torch
    add_safe_globals = None


FREQ_MINUTES = 5  # OhioT1DM readings are spaced 5 minutes apart


def normalize_subject_id(value) -> Optional[str]:
    """Normalize subject identifiers to string format without trailing decimals."""
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    value_str = str(value).strip()
    if value_str.endswith(".0"):
        value_str = value_str[:-2]
    return value_str if value_str else None


def compute_time_features(index: pd.Index) -> np.ndarray:
    index = pd.DatetimeIndex(index)
    minutes_of_day = index.hour * 60 + index.minute + index.second / 60.0
    radians = 2 * np.pi * minutes_of_day / (24 * 60)
    features = np.stack([np.sin(radians), np.cos(radians)], axis=1)
    return features.astype(np.float32)


@dataclass
class SampleMeta:
    patient_id: str
    target_time: pd.Timestamp
    true_value: float


def prepare_patient_series(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare patient CGM readings without interpolation."""
    series = (
        df.sort_values("DateTime")
        .drop_duplicates("DateTime")
        .set_index("DateTime")[["GlucoseValue"]]
    )
    series.index = pd.to_datetime(series.index)
    return series.dropna()


def iterate_sequences(
    series: pd.DataFrame,
    scaler,
    seq_len: int,
    label_len: int,
    pred_len: int,
    target_step: int,
    patient_id: str,
) -> Iterable[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, SampleMeta]]:
    """Yield normalized input/output pairs, time marks, and metadata for a patient."""
    values_raw = series["GlucoseValue"].to_numpy(dtype=np.float32)
    if len(values_raw) < seq_len + pred_len:
        return
    timestamps = series.index.to_numpy(dtype="datetime64[ns]")
    time_marks = compute_time_features(series.index)

    values_scaled = scaler.transform(values_raw.reshape(-1, 1)).astype(np.float32)
    max_start = len(values_scaled) - seq_len - pred_len + 1

    for start in range(max_start):
        s_begin = start
        s_end = s_begin + seq_len
        r_begin = s_end - label_len
        r_end = r_begin + label_len + pred_len

        window_times = timestamps[s_begin:r_end]
        diffs = np.diff(window_times.astype("datetime64[m]")).astype(int)
        if not np.all(diffs == FREQ_MINUTES):
            continue

        seq_x = np.ascontiguousarray(values_scaled[s_begin:s_end])
        seq_y = np.ascontiguousarray(values_scaled[r_begin:r_end])
        seq_x_mark = np.ascontiguousarray(time_marks[s_begin:s_end])
        seq_y_mark = np.ascontiguousarray(time_marks[r_begin:r_end])

        target_index = r_begin + label_len + target_step - 1
        target_time = pd.Timestamp(window_times[target_index - s_begin])
        target_true = float(values_raw[target_index])

        meta = SampleMeta(
            patient_id=patient_id,
            target_time=target_time,
            true_value=target_true,
        )
        yield seq_x, seq_y, seq_x_mark, seq_y_mark, meta


def run_inference(
    model: torch.nn.Module,
    args,
    sequences: Iterable[Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, SampleMeta]],
    batch_size: int,
    target_step: int,
    device: torch.device,
) -> List[Tuple[str, pd.Timestamp, float, float]]:
    """Run model inference over generated sequences."""
    ql_loss = QuantileLoss()
    results: List[Tuple[str, pd.Timestamp, float, float]] = []

    batch_x: List[np.ndarray] = []
    batch_y: List[np.ndarray] = []
    batch_x_mark: List[np.ndarray] = []
    batch_y_mark: List[np.ndarray] = []
    batch_meta: List[SampleMeta] = []

    def process_batch():
        if not batch_x:
            return

        bx = torch.from_numpy(np.stack(batch_x)).to(device)
        by = torch.from_numpy(np.stack(batch_y)).to(device)
        bx_mark = torch.from_numpy(np.stack(batch_x_mark)).to(device)
        by_mark = torch.from_numpy(np.stack(batch_y_mark)).to(device)

        if args.y_diff:
            delta_trend = (
                bx[:, args.seq_len - args.label_len - 1, :1]
                .unsqueeze(1)
                .repeat(1, args.label_len + args.pred_len, 1)
            )
            by = by - delta_trend
        else:
            delta_trend = None

        dec_inp = torch.zeros_like(by[:, -args.pred_len :, :])
        dec_inp = torch.cat([by[:, : args.label_len, :], dec_inp], dim=1)

        outputs = model(bx, bx_mark, dec_inp, by_mark, by)
        outputs = outputs[:, -args.pred_len :, :]

        if args.y_diff and delta_trend is not None:
            outputs = outputs + delta_trend[:, -args.pred_len :, :]
            by = by + delta_trend[:, -args.pred_len :, :]

        preds = ql_loss.to_prediction(outputs).cpu().numpy()
        preds = preds * args.scale + args.delta

        step_index = target_step - 1

        for pred_seq, meta in zip(preds, batch_meta):
            pred_value = float(pred_seq[step_index, 0])
            results.append((meta.patient_id, meta.target_time, meta.true_value, pred_value))

        batch_x.clear()
        batch_y.clear()
        batch_x_mark.clear()
        batch_y_mark.clear()
        batch_meta.clear()

    model.eval()
    with torch.no_grad():
        for seq_x, seq_y, seq_x_mark, seq_y_mark, meta in sequences:
            batch_x.append(seq_x)
            batch_y.append(seq_y)
            batch_x_mark.append(seq_x_mark)
            batch_y_mark.append(seq_y_mark)
            batch_meta.append(meta)

            if len(batch_x) == batch_size:
                process_batch()

        process_batch()

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate GPFormer on OhioT1DM with a 30-minute horizon."
    )
    parser.add_argument(
        "--model-path",
        default="saved_models/GPFormer/GPFormer.pth",
        help="Path to the trained GPFormer model file.",
    )
    parser.add_argument(
        "--scaler-path",
        default="data_loader/mldg_scaler.pkl",
        help="Path to the scaler used during training.",
    )
    parser.add_argument(
        "--data-root",
        default="ohioT1DM_processed",
        help="Root directory containing OhioT1DM year folders.",
    )
    parser.add_argument(
        "--split",
        default="combined",
        choices=["train", "test", "combined"],
        help="Which OhioT1DM split to evaluate.",
    )
    parser.add_argument(
        "--output-csv",
        default="result_GPFormer - replication.csv",
        help="Path to the summary CSV (template) that will receive per-subject metrics.",
    )
    parser.add_argument(
        "--save-predictions",
        default=None,
        help="Optional path to save detailed per-sample predictions as CSV.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=256,
        help="Batch size for inference.",
    )
    parser.add_argument(
        "--seq-len",
        type=int,
        default=72,
        help="Number of historical steps (5-minute intervals).",
    )
    parser.add_argument(
        "--label-len",
        type=int,
        default=6,
        help="Decoder label length (number of known future steps).",
    )
    parser.add_argument(
        "--pred-len",
        type=int,
        default=24,
        help="Number of prediction steps to generate.",
    )
    parser.add_argument(
        "--target-step",
        type=int,
        default=6,
        help="Target prediction step (1-based) corresponding to 30 minutes.",
    )

    args_cli = parser.parse_args()

    if args_cli.target_step < 1 or args_cli.target_step > args_cli.pred_len:
        raise ValueError("target_step must be between 1 and pred_len inclusive.")

    if not os.path.exists(args_cli.model_path):
        raise FileNotFoundError(f"Model file not found: {args_cli.model_path}")
    if not os.path.exists(args_cli.scaler_path):
        raise FileNotFoundError(f"Scaler file not found: {args_cli.scaler_path}")

    scaler = pickle.load(open(args_cli.scaler_path, "rb"))

    raw_data = load_ohio_data(args_cli.data_root, split=args_cli.split, years=["2018", "2020"])
    if raw_data is None or raw_data.empty:
        raise RuntimeError("No OhioT1DM data could be loaded.")

    argv_backup = list(sys.argv)
    sys.argv = [sys.argv[0]]
    args = args_bglp(model="GPFormer")
    sys.argv = argv_backup
    args.seq_len = args_cli.seq_len
    args.label_len = args_cli.label_len
    args.pred_len = args_cli.pred_len
    args.n_support_domains = 16
    args.n_query_domains = 8
    args.d_model = 128
    args.batch_size = args_cli.batch_size
    args.n_heads = 8
    args.embed = "cycF"
    args.enc_in = 1
    args.dec_in = 1
    args.e_layers = 3
    args.y_diff = False
    args.scale_fn = 2
    args.ql = True
    args.c_out = 5
    args.d_layers = 1
    args.d_ff = 2048
    args.factor = 1
    args.dropout = 0.05
    args.activation = "gelu"
    args.freq = "cyc"
    args.output_attention = False

    if add_safe_globals is not None:
        add_safe_globals([GPFormer.Model])

    load_kwargs = {"map_location": "cpu"}
    if "weights_only" in inspect.signature(torch.load).parameters:
        load_kwargs["weights_only"] = False

    checkpoint = torch.load(args_cli.model_path, **load_kwargs)
    if isinstance(checkpoint, torch.nn.Module):
        state_dict = checkpoint.state_dict()
    elif isinstance(checkpoint, dict):
        state_dict = checkpoint
    else:
        raise TypeError("Unsupported checkpoint format.")

    args.use_gpu = torch.cuda.is_available()
    device = torch.device("cuda:0" if args.use_gpu else "cpu")
    args.device = device

    args.scale = scaler.scale_[0]
    args.delta = scaler.mean_[0]

    model = GPFormer.Model(args).float().to(device)
    model.load_state_dict(state_dict, strict=True)

    sequence_iters = (
        iterate_sequences(
            series=prepare_patient_series(patient_df),
            scaler=scaler,
            seq_len=args.seq_len,
            label_len=args.label_len,
            pred_len=args.pred_len,
            target_step=args_cli.target_step,
            patient_id=str(patient_id),
        )
        for patient_id, patient_df in raw_data.groupby("PtID")
    )

    sequences = itertools.chain.from_iterable(sequence_iters)

    results = run_inference(
        model=model,
        args=args,
        sequences=sequences,
        batch_size=args_cli.batch_size,
        target_step=args_cli.target_step,
        device=device,
    )

    minutes_ahead = args_cli.target_step * FREQ_MINUTES
    df_results = pd.DataFrame(
        results,
        columns=[
            "patient_id",
            "timestamp",
            "true_glucose_mg_dL",
            "predicted_glucose_mg_dL",
        ],
    )
    df_results["timestamp"] = pd.to_datetime(df_results["timestamp"], errors="coerce")

    if df_results.empty:
        raise RuntimeError("No predictions were generated. Check data coverage.")

    metrics_map: dict[str, Tuple[float, float]] = {}
    for patient_id, group in df_results.groupby("patient_id"):
        errors = group["predicted_glucose_mg_dL"] - group["true_glucose_mg_dL"]
        rmse = float(np.sqrt(np.mean(np.square(errors))))
        mae = float(np.mean(np.abs(errors)))
        metrics_map[str(patient_id)] = (rmse, mae)

    unique_subjects = sorted(
        pid
        for pid in (normalize_subject_id(pid) for pid in raw_data["PtID"].unique())
        if pid
    )
    missing_patients = [pid for pid in unique_subjects if pid not in metrics_map]
    if missing_patients:
        missing_str = ", ".join(missing_patients)
        raise RuntimeError(f"No predictions generated for subjects: {missing_str}")

    overall_errors = df_results["predicted_glucose_mg_dL"] - df_results["true_glucose_mg_dL"]
    overall_rmse = float(np.sqrt(np.mean(np.square(overall_errors))))
    overall_mae = float(np.mean(np.abs(overall_errors)))

    summary_columns = [
        "Dataset",
        "SubjectID",
        "Train on REPLACE-BG, test on entire OhioT1DM, 6h history length",
        "RMSE (PH-30-min)",
        "MAE (PH-30-min)",
    ]
    scenario_col = summary_columns[2]
    rmse_col = summary_columns[3]
    mae_col = summary_columns[4]
    summary_path = args_cli.output_csv
    os.makedirs(os.path.dirname(summary_path) or ".", exist_ok=True)
    if os.path.exists(summary_path):
        summary_df = pd.read_csv(summary_path)
    else:
        summary_df = pd.DataFrame(columns=summary_columns)

    for col in summary_columns:
        if col not in summary_df.columns:
            summary_df[col] = ""
    summary_df = summary_df[summary_columns]

    used_patients: set[str] = set()
    for idx in summary_df.index:
        pid_key = normalize_subject_id(summary_df.at[idx, "SubjectID"])
        if pid_key and pid_key in metrics_map:
            rmse, mae = metrics_map[pid_key]
            summary_df.at[idx, "Dataset"] = "OhioT1DM"
            summary_df.at[idx, "SubjectID"] = pid_key
            if pd.isna(summary_df.at[idx, scenario_col]):
                summary_df.at[idx, scenario_col] = ""
            summary_df.at[idx, rmse_col] = f"{rmse:.2f}"
            summary_df.at[idx, mae_col] = f"{mae:.2f}"
            used_patients.add(pid_key)

    for pid_key, (rmse, mae) in metrics_map.items():
        if pid_key not in used_patients:
            new_row = {
                "Dataset": "OhioT1DM",
                "SubjectID": pid_key,
                scenario_col: "",
                rmse_col: f"{rmse:.2f}",
                mae_col: f"{mae:.2f}",
            }
            summary_df = pd.concat([summary_df, pd.DataFrame([new_row])], ignore_index=True)

    summary_df["_sort"] = pd.to_numeric(summary_df["SubjectID"], errors="coerce")
    summary_df.sort_values(by=["_sort", "SubjectID"], inplace=True)
    summary_df.drop(columns="_sort", inplace=True)
    summary_df["SubjectID"] = summary_df["SubjectID"].apply(lambda x: normalize_subject_id(x) or "")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8")

    if args_cli.save_predictions:
        pred_path = args_cli.save_predictions
        os.makedirs(os.path.dirname(pred_path) or ".", exist_ok=True)
        pred_df = df_results.copy()
        pred_df["timestamp"] = pred_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        pred_df.sort_values(["patient_id", "timestamp"], inplace=True)
        pred_df.to_csv(pred_path, index=False, encoding="utf-8")
        print(f"Detailed predictions saved to {pred_path}")

    print(f"\nGenerated {len(df_results)} per-sample predictions.")
    print("\nPer-patient 30-minute metrics:")
    for pid in sorted(metrics_map.keys(), key=lambda x: int(x)):
        rmse, mae = metrics_map[pid]
        print(f"  Subject {pid}: RMSE={rmse:.2f} mg/dL, MAE={mae:.2f} mg/dL")

    print(f"\nOverall {minutes_ahead}-minute RMSE: {overall_rmse:.2f} mg/dL")
    print(f"Overall {minutes_ahead}-minute MAE:  {overall_mae:.2f} mg/dL")
    print(f"\nSaved per-subject summary to: {summary_path}")


if __name__ == "__main__":
    main()
