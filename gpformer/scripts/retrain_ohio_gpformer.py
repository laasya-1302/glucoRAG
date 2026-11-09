import argparse
import math
import os
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, Dataset

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from args_generator import args_bglp  # noqa: E402
from layers.utils import QuantileLoss  # noqa: E402
from models import GPFormer  # noqa: E402
from preprocess_ohio import load_ohio_data  # noqa: E402


FREQ_MINUTES = 5
TARGET_STEP = 6  # 30 minutes ahead when data is sampled every 5 minutes
SUMMARY_CSV = Path("result_GPFormer - retrain_result.csv")
DEFAULT_PREDICTIONS_CSV = Path("ohio_retrain_predictions.csv")


def set_random_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def normalize_subject_id(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    value_str = str(value).strip()
    if value_str.endswith(".0"):
        value_str = value_str[:-2]
    return value_str if value_str else None


def compute_time_features(index: pd.Index) -> np.ndarray:
    minutes_of_day = (
        index.hour * 60 + index.minute + index.second / 60.0
    )
    radians = 2 * np.pi * minutes_of_day / (24 * 60)
    features = np.stack([np.sin(radians), np.cos(radians)], axis=1)
    return features.astype(np.float32)


def resample_subject(series: pd.DataFrame, value_col: str) -> pd.DataFrame:
    df = series.dropna(subset=[value_col]).copy()
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df.dropna(subset=[value_col])


class SequenceDataset(Dataset):
    def __init__(self, entries: Sequence[dict]):
        self.entries = list(entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, idx: int):
        entry = self.entries[idx]
        return (
            entry["x"],
            entry["y"],
            entry["x_mark"],
            entry["y_mark"],
            entry.get("meta"),
        )


def collate_fn(batch):
    xs, ys, x_marks, y_marks, metas = zip(*batch)
    batch_x = torch.from_numpy(np.stack(xs)).float()
    batch_y = torch.from_numpy(np.stack(ys)).float()
    batch_x_mark = torch.from_numpy(np.stack(x_marks)).float()
    batch_y_mark = torch.from_numpy(np.stack(y_marks)).float()
    return batch_x, batch_y, batch_x_mark, batch_y_mark, list(metas)


def create_entries(
    subject_series: Dict[str, pd.DataFrame],
    scaler: StandardScaler,
    seq_len: int,
    label_len: int,
    pred_len: int,
    include_meta: bool,
    fold_label: str,
    dataset_name: str,
    target_step: int,
) -> List[dict]:
    entries: List[dict] = []
    for subject_id, df in subject_series.items():
        values = df.iloc[:, 0].to_numpy(dtype=np.float32)
        timestamps = df.index.to_numpy(dtype="datetime64[ns]")
        if len(values) < seq_len + pred_len:
            continue

        scaled_values = scaler.transform(values.reshape(-1, 1)).flatten().astype(np.float32)
        time_marks = compute_time_features(df.index)

        for start in range(len(values) - seq_len - pred_len + 1):
            s_begin = start
            s_end = s_begin + seq_len
            r_begin = s_end - label_len
            r_end = r_begin + label_len + pred_len
            target_index = r_begin + label_len + target_step - 1
            if target_index >= len(values):
                continue

            window_slice = slice(s_begin, r_end)
            window_times = timestamps[window_slice]
            diffs = np.diff(window_times.astype("datetime64[m]")).astype(int)
            if not np.all(diffs == FREQ_MINUTES):
                continue

            entry = {
                "x": scaled_values[s_begin:s_end][:, None],
                "y": scaled_values[r_begin:r_end][:, None],
                "x_mark": time_marks[s_begin:s_end],
                "y_mark": time_marks[r_begin:r_end],
            }

            if include_meta:
                target_timestamp = pd.Timestamp(timestamps[target_index])
                entry["meta"] = {
                    "dataset": dataset_name,
                    "subject_id": subject_id,
                    "fold": fold_label,
                    "target_timestamp": target_timestamp,
                    "true_value": float(values[target_index]),
                }

            entries.append(entry)

    return entries


class GPFormerTrainer:
    def __init__(
        self,
        device: torch.device,
        epochs: int,
        batch_size: int,
        learning_rate: float,
        seq_len: int,
        label_len: int,
        pred_len: int,
        dataset_name: str,
        target_step: int,
        predictions_csv: Path,
        summary_csv: Path,
    ):
        self.device = device
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.seq_len = seq_len
        self.label_len = label_len
        self.pred_len = pred_len
        self.dataset_name = dataset_name
        self.target_step = target_step
        self.predictions_csv = predictions_csv
        self.summary_csv = summary_csv
        self.quantile_loss = QuantileLoss()
        self.scaler = StandardScaler()
        self.args = self._build_args()
        self.model = GPFormer.Model(self.args).float().to(self.device)

    def _build_args(self):
        argv_backup = list(sys.argv)
        sys.argv = [sys.argv[0]]
        args = args_bglp(model="GPFormer")
        sys.argv = argv_backup

        args.seq_len = self.seq_len
        args.label_len = self.label_len
        args.pred_len = self.pred_len
        args.enc_in = 1
        args.dec_in = 1
        args.c_out = 5
        args.n_heads = 8
        args.d_model = 128
        args.e_layers = 3
        args.d_layers = 1
        args.d_ff = 2048
        args.factor = 1
        args.dropout = 0.05
        args.embed = "cycF"
        args.freq = "cyc"
        args.activation = "gelu"
        args.output_attention = False
        args.y_diff = False
        args.scale_fn = 2
        args.ql = True
        args.device = self.device
        args.use_gpu = self.device.type == "cuda"
        return args

    def prepare_data(
        self,
        train_series: Dict[str, pd.DataFrame],
        test_series: Dict[str, pd.DataFrame],
    ):
        all_train_values = np.concatenate(
            [df.iloc[:, 0].to_numpy(dtype=np.float32) for df in train_series.values()]
        ).reshape(-1, 1)
        self.scaler.fit(all_train_values)
        self.args.scale = float(self.scaler.scale_[0])
        self.args.delta = float(self.scaler.mean_[0])

        train_entries = create_entries(
            train_series,
            self.scaler,
            self.seq_len,
            self.label_len,
            self.pred_len,
            include_meta=False,
            fold_label="train",
            dataset_name=self.dataset_name,
            target_step=self.target_step,
        )
        test_entries = create_entries(
            test_series,
            self.scaler,
            self.seq_len,
            self.label_len,
            self.pred_len,
            include_meta=True,
            fold_label="test",
            dataset_name=self.dataset_name,
            target_step=self.target_step,
        )

        if not train_entries:
            raise RuntimeError("No valid training sequences were generated.")
        if not test_entries:
            raise RuntimeError("No valid testing sequences were generated.")

        self.train_loader = DataLoader(
            SequenceDataset(train_entries),
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=0,
            collate_fn=collate_fn,
            drop_last=False,
        )
        self.test_loader = DataLoader(
            SequenceDataset(test_entries),
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=0,
            collate_fn=collate_fn,
            drop_last=False,
        )

    def train(self):
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.learning_rate)
        for epoch in range(1, self.epochs + 1):
            self.model.train()
            losses: List[float] = []
            for batch_x, batch_y, batch_x_mark, batch_y_mark, _ in self.train_loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                batch_x_mark = batch_x_mark.to(self.device)
                batch_y_mark = batch_y_mark.to(self.device)

                dec_inp = torch.zeros_like(batch_y[:, -self.pred_len :, :]).float()
                dec_inp = torch.cat([batch_y[:, : self.label_len, :], dec_inp], dim=1)

                outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark, batch_y)
                outputs = outputs[:, -self.pred_len :, :]
                target = batch_y[:, -self.pred_len :, :]

                loss = self.quantile_loss(outputs, target)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                optimizer.step()

                losses.append(loss.item())

            avg_loss = float(np.mean(losses))
            print(f"[Epoch {epoch}/{self.epochs}] Training quantile loss: {avg_loss:.4f}")

    def evaluate(self) -> Tuple[List[dict], Dict[str, Tuple[float, float]]]:
        self.model.eval()
        predictions: List[dict] = []
        per_subject: Dict[str, List[Tuple[float, float]]] = defaultdict(list)

        with torch.no_grad():
            for batch_x, batch_y, batch_x_mark, batch_y_mark, metas in self.test_loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                batch_x_mark = batch_x_mark.to(self.device)
                batch_y_mark = batch_y_mark.to(self.device)

                dec_inp = torch.zeros_like(batch_y[:, -self.pred_len :, :]).float()
                dec_inp = torch.cat([batch_y[:, : self.label_len, :], dec_inp], dim=1)

                outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark, batch_y)
                outputs = outputs[:, -self.pred_len :, :]

                preds = self.quantile_loss.to_prediction(outputs).cpu().numpy()
                preds = preds * self.scaler.scale_[0] + self.scaler.mean_[0]

                for pred_seq, meta in zip(preds, metas):
                    if meta is None:
                        continue
                    subject_id = normalize_subject_id(meta["subject_id"])
                    timestamp = pd.Timestamp(meta["target_timestamp"])
                    true_value = float(meta["true_value"])
                    pred_value = float(pred_seq[self.target_step - 1, 0])

                    predictions.append(
                        {
                            "dataset": meta["dataset"],
                            "subject_id": subject_id,
                            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                            "true_glucose_mg_dL": true_value,
                            "predicted_glucose_mg_dL": pred_value,
                            "fold": meta["fold"],
                        }
                    )
                    per_subject[subject_id].append((true_value, pred_value))

        metrics: Dict[str, Tuple[float, float]] = {}
        for subject_id, pairs in per_subject.items():
            trues = np.array([t for t, _ in pairs], dtype=np.float32)
            preds = np.array([p for _, p in pairs], dtype=np.float32)
            rmse = float(np.sqrt(np.mean((preds - trues) ** 2)))
            mae = float(np.mean(np.abs(preds - trues)))
            metrics[subject_id] = (rmse, mae)

        return predictions, metrics

    def save_predictions(self, records: List[dict]):
        df = pd.DataFrame(records)
        df.sort_values(["subject_id", "timestamp"], inplace=True)
        os.makedirs(self.predictions_csv.parent, exist_ok=True)
        pred_df = df.copy()
        if "timestamp" in pred_df.columns:
            ts = pd.to_datetime(pred_df["timestamp"], errors="coerce")
            formatted = ts.dt.strftime("%Y-%m-%d %H:%M:%S")
            pred_df["timestamp"] = formatted.fillna(pred_df["timestamp"].astype(str))
        pred_df.to_csv(self.predictions_csv, index=False, encoding="utf-8")
        print(f"Saved per-sample predictions to {self.predictions_csv}")

    def update_summary(self, metrics: Dict[str, Tuple[float, float]]):
        summary_columns = [
            "Dataset",
            "SubjectID",
            "Martinsson_retrained",
            "vanDoorn_retrained",
            "Deng_retrained",
            "Lee_retrained",
            "Rabby_retrained",
            "Li_retrained",
            "baseline",
            "PatchTST_retrained",
            "GPFormer (PH=30mins) RMSE",
            "GPFormer (PH=30mins) MAE",
        ]
        if self.summary_csv.exists():
            summary_df = pd.read_csv(self.summary_csv)
        else:
            summary_df = pd.DataFrame(columns=summary_columns)

        for col in summary_columns:
            if col not in summary_df.columns:
                summary_df[col] = ""

        for subject_id, (rmse, mae) in metrics.items():
            mask = (summary_df["Dataset"] == self.dataset_name) & (
                summary_df["SubjectID"].astype(str) == subject_id
            )
            if mask.any():
                summary_df.loc[mask, "GPFormer (PH=30mins) RMSE"] = f"{rmse:.2f}"
                summary_df.loc[mask, "GPFormer (PH=30mins) MAE"] = f"{mae:.2f}"
            else:
                new_row = {
                    "Dataset": self.dataset_name,
                    "SubjectID": subject_id,
                    "GPFormer (PH=30mins) RMSE": f"{rmse:.2f}",
                    "GPFormer (PH=30mins) MAE": f"{mae:.2f}",
                }
                summary_df = pd.concat([summary_df, pd.DataFrame([new_row])], ignore_index=True)

        summary_df.to_csv(self.summary_csv, index=False, encoding="utf-8")
        print(f"Updated summary metrics in {self.summary_csv}")


def load_split_series(split: str, seq_len: int, pred_len: int) -> Dict[str, pd.DataFrame]:
    df = load_ohio_data("ohioT1DM_processed", split=split, years=["2018", "2020"])
    if df is None or df.empty:
        raise RuntimeError(f"No data loaded for split '{split}'.")

    grouped: Dict[str, pd.DataFrame] = {}
    for subject_id, sub_df in df.groupby("PtID"):
        sub_df = sub_df.sort_values("DateTime")
        sub_df = sub_df.drop_duplicates("DateTime")
        sub_df = sub_df.set_index("DateTime")[["GlucoseValue"]]
        sub_df.index = pd.to_datetime(sub_df.index)
        sub_df = resample_subject(sub_df, "GlucoseValue")
        if len(sub_df) >= seq_len + pred_len:
            grouped[str(subject_id)] = sub_df

    if not grouped:
        raise RuntimeError(f"No valid subject sequences for split '{split}'.")
    return grouped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrain GPFormer on OhioT1DM (processed splits).")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs.")
    parser.add_argument("--batch-size", type=int, default=256, help="Training batch size.")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="Optimizer learning rate.")
    parser.add_argument("--seq-len", type=int, default=72, help="Input history length (5-min steps).")
    parser.add_argument("--label-len", type=int, default=6, help="Decoder label length.")
    parser.add_argument("--pred-len", type=int, default=24, help="Prediction length (5-min steps).")
    parser.add_argument(
        "--target-step",
        type=int,
        default=TARGET_STEP,
        help="Prediction step (1-based) used for metrics (6 -> 30 minutes).",
    )
    parser.add_argument(
        "--predictions-csv",
        type=Path,
        default=DEFAULT_PREDICTIONS_CSV,
        help="Output CSV for per-sample predictions.",
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=SUMMARY_CSV,
        help="Summary CSV file to update with metrics.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    return parser.parse_args()


def main():
    args = parse_args()
    set_random_seed(args.seed)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    if not (1 <= args.target_step <= args.pred_len):
        raise ValueError("target_step must be between 1 and pred_len (inclusive).")

    print("Loading OhioT1DM processed training split...")
    train_series = load_split_series("train", args.seq_len, args.pred_len)
    print(f"Loaded {len(train_series)} training subjects.")

    print("Loading OhioT1DM processed testing split...")
    test_series = load_split_series("test", args.seq_len, args.pred_len)
    print(f"Loaded {len(test_series)} testing subjects.")

    trainer = GPFormerTrainer(
        device=device,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        seq_len=args.seq_len,
        label_len=args.label_len,
        pred_len=args.pred_len,
        dataset_name="OhioT1DM",
        target_step=args.target_step,
        predictions_csv=args.predictions_csv,
        summary_csv=args.summary_csv,
    )
    trainer.prepare_data(train_series, test_series)
    trainer.train()
    predictions, metrics = trainer.evaluate()
    trainer.save_predictions(predictions)
    trainer.update_summary(metrics)


if __name__ == "__main__":
    main()
