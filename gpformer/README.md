# GPFormer (reproduction track)

This folder contains our reproduced and extended implementation of "GPFormer: Multi-Horizon Glucose Prediction with Deep Domain Generalization". The main pieces are:
- Reproducing the original meta-learning training loop (`main.py`).
- Training and evaluating GPFormer on processed DiaTrend, OhioT1DM, and T1DEXI data splits (`scripts/`).
- Exporting comparable prediction summaries so that GPFormer can be ranked against other methods in this study.

---

## Layout overview

```
2025Zhu_et_al_GPFormer/
|-- main.py                          # meta-learning training entrypoint (uses prebuilt dataloaders)
|-- args_generator.py                # shared CLI argument definitions
|-- models/
|   `-- GPFormer.py                  # Transformer encoder/decoder with sparse attention
|-- layers/                          # embedding, attention, encoder/decoder building blocks
|-- utils/                           # data iterator, meters, time feature helpers
|-- scripts/
|   |-- retrain_ohio_gpformer.py     # GPFormerTrainer and OhioT1DM retraining CLI
|   |-- retrain_diatrend_gpformer.py # DiaTrend 5-fold retraining (reuses GPFormerTrainer)
|   |-- retrain_t1dexi_gpformer.py   # T1DEXI 5-fold retraining (reuses GPFormerTrainer)
|   `-- test_ohio_30min.py           # rolling 30-minute inference on OhioT1DM
|-- modified_diatrend_subset/        # processed DiaTrend folds (foldX_training/test)
|-- ohioT1DM_processed/              # processed OhioT1DM split into train/test
|-- T1DEXI_cgm_processed/            # processed T1DEXI folds (foldX_training/test)
|-- saved_models/                    # checkpoints written by the scripts
|-- diatrend_retrain_predictions.csv # per-sample predictions for DiaTrend retraining
|-- ohio_retrain_predictions.csv     # per-sample predictions for Ohio retraining
|-- t1dexi_retrain_predictions.csv   # per-sample predictions for T1DEXI retraining
|-- ohio_30min_predictions.csv       # rolling 30-minute inference results on Ohio
|-- result_GPFormer - replication.csv    # Ohio evaluation table used by the study
|-- result_GPFormer - retrain_result.csv # consolidated table for retraining runs
`-- requirements.txt                 # python dependencies
```

---

## Key files and modules

- `main.py`: reproduces the original Meta-Learning for Domain Generalization (MLDG) training loop. It expects `data_loader/mldg_train_loader.pth`, `data_loader/mldg_test_loader.pth`, and `data_loader/mldg_scaler.pkl`, then saves the trained model under `saved_models/GPFormer/`.
- `args_generator.py`: centralises all model, optimiser, and meta-learning hyperparameters so scripts can override only what they need.
- `models/GPFormer.py`: implements the Transformer encoder/decoder with sparse self-attention and a final projection for multiple quantiles.
- `layers/`: low-level building blocks (time embeddings, attention modules, encoder/decoder stacks).
- `utils/data.py`: provides `ForeverDataIterator` for endless batching across domains.
- `utils/meter.py`: running averages, timers, and formatted logging for training.
- `utils/timefeatures.py`: creates sine/cosine time-of-day features reused across scripts.
- `scripts/retrain_ohio_gpformer.py`: defines `GPFormerTrainer`, handles StandardScaler fitting, dataset windowing, PyTorch dataloaders, training, evaluation, and updates `result_GPFormer - retrain_result.csv`.
- `scripts/retrain_diatrend_gpformer.py` and `scripts/retrain_t1dexi_gpformer.py`: thin wrappers around `GPFormerTrainer` that iterate over pre-defined folds.
- `scripts/test_ohio_30min.py`: loads a trained checkpoint plus scaler, performs rolling 30-minute inference on OhioT1DM (train/test/combined) and optionally stores per-sample predictions.

---

## Environment

1. Use Python 3.9 or later.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. GPU acceleration is optional but supported if your PyTorch build has CUDA enabled.

---

## How to run

### 1. Original MLDG pipeline (`main.py`)

1. Place the pre-generated MLDG assets inside `data_loader/`:
   - `mldg_train_loader.pth`
   - `mldg_test_loader.pth`
   - `mldg_scaler.pkl`
   These pickles come from the original data preparation and are not regenerated here.
2. Launch training (identical to `scripts/run.sh`):
   ```bash
   python main.py \
       --n_support_domains 16 \
       --n_query_domains 8 \
       --d_model 128 \
       --batch_size 256 \
       --n_heads 8 \
       --embed cycF \
       --enc_in 1 \
       --e_layers 3 \
       --y_diff False \
       --scale_fn 2 \
       --ql True \
       --c_out 5 \
       --lr 0.001 \
       --iters_per_epoch 500 \
       --train_epochs 50 \
       --seq_len 72 \
       --pred_len 24
   ```
3. The script writes the trained checkpoint to `saved_models/GPFormer/GPFormer.pth` and keeps predictions in memory for downstream evaluation.

### 2. Dataset-specific retraining scripts (`scripts/`)

Each retraining CLI fits a `StandardScaler`, builds PyTorch dataloaders, trains for the requested number of epochs, writes per-sample predictions, and updates `result_GPFormer - retrain_result.csv`.

- **OhioT1DM**
  ```bash
  python scripts/retrain_ohio_gpformer.py \
      --data-root ohioT1DM_processed \
      --epochs 50 \
      --batch-size 256 \
      --learning-rate 1e-4 \
      --seq-len 72 \
      --label-len 6 \
      --pred-len 24 \
      --target-step 6 \
      --predictions-csv ohio_retrain_predictions.csv \
      --summary-csv "result_GPFormer - retrain_result.csv"
  ```
  The `ohioT1DM_processed/` directory must contain `train/` and `test/` subfolders with cleaned CSV files keyed by `PtID`.

- **DiaTrend (five folds)**
  ```bash
  python scripts/retrain_diatrend_gpformer.py \
      --data-root modified_diatrend_subset \
      --folds 1 2 3 4 5 \
      --predictions-csv diatrend_retrain_predictions.csv \
      --summary-csv "result_GPFormer - retrain_result.csv"
  ```
  Data must follow the `fold{n}_training/` and `fold{n}_test/` convention.

- **T1DEXI (five folds)**
  ```bash
  python scripts/retrain_t1dexi_gpformer.py \
      --data-root T1DEXI_cgm_processed \
      --folds 1 2 3 4 5 \
      --predictions-csv t1dexi_retrain_predictions.csv \
      --summary-csv "result_GPFormer - retrain_result.csv"
  ```

All scripts accept `--epochs`, `--batch-size`, `--learning-rate`, `--seq-len`, and related options so you can reproduce or extend experiments.

### 3. Ohio rolling evaluation (`scripts/test_ohio_30min.py`)

This script evaluates any trained GPFormer checkpoint with a 30-minute horizon on OhioT1DM:
```bash
python scripts/test_ohio_30min.py \
    --model-path saved_models/GPFormer/GPFormer.pth \
    --scaler-path data_loader/mldg_scaler.pkl \
    --data-root ohioT1DM_processed \
    --split combined \
    --output-csv "result_GPFormer - replication.csv" \
    --save-predictions ohio_30min_predictions.csv \
    --batch-size 256 \
    --seq-len 72 \
    --label-len 6 \
    --pred-len 24 \
    --target-step 6
```
- `--split` accepts `train`, `test`, or `combined`.
- If `--save-predictions` is omitted the script only updates the summary table; providing a path writes per-sample predictions.
- Metrics overwrite or extend `result_GPFormer - replication.csv`.

---

## Data and results

- **Datasets**: `modified_diatrend_subset/`, `ohioT1DM_processed/`, and `T1DEXI_cgm_processed/` already follow the folder layout expected by the scripts (train/test or fold splits).
- **Checkpoints**: retraining scripts store models in `saved_models/` (one file per dataset/fold).
- **Predictions**: `*_retrain_predictions.csv` and `ohio_30min_predictions.csv` keep detailed predictions for further analysis.
- **Summary tables**:
  - `result_GPFormer - retrain_result.csv` collects per-subject 30-minute RMSE/MAE for all retraining runs.
  - `result_GPFormer - replication.csv` gathers the replication setting used for cross-method comparison on OhioT1DM.

---

## Notes

- Horizons other than 30 minutes can be explored by changing `--target-step` together with `--pred-len`.
- To adapt GPFormer to a new dataset, follow the preprocessing conventions in the retraining scripts (time column normalised to a datetime index and a single glucose column), then call `GPFormerTrainer.prepare_data`.
- Large CSVs bundled here were derived from publicly available datasets; please respect each dataset's licence or data-use agreement.
