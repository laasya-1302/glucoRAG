import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import torch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from retrain_ohio_gpformer import (  # noqa: E402
    GPFormerTrainer,
    normalize_subject_id,
    resample_subject,
    set_random_seed,
)


DEFAULT_DATA_ROOT = Path("T1DEXI_cgm_processed")
DEFAULT_PREDICTIONS_CSV = Path("t1dexi_retrain_predictions.csv")
SUMMARY_CSV = Path("result_GPFormer - retrain_result.csv")


def load_fold_series(
    data_root: Path,
    fold: int,
    split: str,
    seq_len: int,
    pred_len: int,
) -> Dict[str, pd.DataFrame]:
    if split not in {"training", "test"}:
        raise ValueError("split must be 'training' or 'test'")
    folder = data_root / f"fold{fold}_{split}"
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    series_map: Dict[str, pd.DataFrame] = {}
    for csv_path in sorted(folder.glob("*.csv")):
        df = pd.read_csv(csv_path)
        if {"LBDTC", "LBORRES"} - set(df.columns):
            raise ValueError(f"Unexpected columns in {csv_path}")
        df["LBDTC"] = pd.to_datetime(df["LBDTC"])
        df = df.sort_values("LBDTC")
        df = df.drop_duplicates("LBDTC")
        df = df.set_index("LBDTC")[["LBORRES"]]
        df = resample_subject(df, "LBORRES")
        if len(df) >= seq_len + pred_len:
            subject_id = normalize_subject_id(csv_path.stem)
            if subject_id is not None:
                series_map[subject_id] = df

    if not series_map:
        raise RuntimeError(f"No valid sequences found in {folder}")
    return series_map


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrain GPFormer on T1DEXI with 5-fold splits.")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs per fold.")
    parser.add_argument("--batch-size", type=int, default=256, help="Training batch size.")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="Optimizer learning rate.")
    parser.add_argument("--seq-len", type=int, default=72, help="Input history length (5-min steps).")
    parser.add_argument("--label-len", type=int, default=6, help="Decoder label length.")
    parser.add_argument("--pred-len", type=int, default=24, help="Prediction length (5-min steps).")
    parser.add_argument(
        "--target-step",
        type=int,
        default=6,
        help="Prediction step (1-based) used for metrics (6 -> 30 minutes).",
    )
    parser.add_argument(
        "--folds",
        type=int,
        nargs="+",
        default=[1, 2, 3, 4, 5],
        help="Fold indices to process.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="Root directory containing fold subfolders.",
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
    if not (1 <= args.target_step <= args.pred_len):
        raise ValueError("target_step must be between 1 and pred_len (inclusive).")

    set_random_seed(args.seed)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    all_predictions: List[dict] = []
    aggregated_metrics: Dict[str, Tuple[float, float]] = {}
    trainer_template: GPFormerTrainer | None = None

    for fold in args.folds:
        print(f"\n===== Fold {fold} =====")
        train_series = load_fold_series(args.data_root, fold, "training", args.seq_len, args.pred_len)
        test_series = load_fold_series(args.data_root, fold, "test", args.seq_len, args.pred_len)
        print(f"Training subjects: {len(train_series)}, Testing subjects: {len(test_series)}")

        trainer = GPFormerTrainer(
            device=device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            seq_len=args.seq_len,
            label_len=args.label_len,
            pred_len=args.pred_len,
            dataset_name="T1DEXI",
            target_step=args.target_step,
            predictions_csv=args.predictions_csv,
            summary_csv=args.summary_csv,
        )
        trainer.prepare_data(train_series, test_series)
        trainer.train()
        predictions, metrics = trainer.evaluate()

        for record in predictions:
            record["fold"] = f"fold{fold}"
        all_predictions.extend(predictions)
        aggregated_metrics.update(metrics)
        trainer_template = trainer

    if not all_predictions or trainer_template is None:
        raise RuntimeError("No predictions generated across folds.")

    trainer_template.save_predictions(all_predictions)
    trainer_template.update_summary(aggregated_metrics)
    print("\nCompleted T1DEXI retraining across folds.")


if __name__ == "__main__":
    main()
