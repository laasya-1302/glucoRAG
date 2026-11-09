# GPFormer Glucose Forecasting Web Application

A production-grade, end-to-end clinical blood glucose forecasting web application connecting a trained **GPFormer** (Deep Domain Generalization Transformer with Quantile Decoder and Multi-Task Risk Head) to a **FastAPI** Python backend and a responsive **React (Vite)** clinical dashboard.

---

## 1. System Architecture & Discovered Specifications

### Model & Neural Architecture
- **Base Forecasting Backbone:** Original `GPFormer.Model` (`d_model=128`, `n_heads=8`, `e_layers=3`, `d_ff=2048`, `dropout=0.05`, `embed="cycF"`, `freq="cyc"`).
- **Time Embeddings:** 2-dimensional continuous sinusoidal time-of-day representation (`make_marks(hour, 2)`: $\sin(\frac{2\pi \cdot \text{hour}}{24})$ and $\cos(\frac{2\pi \cdot \text{hour}}{24})$).
- **Input Window:** Exactly 24 chronological glucose readings ($SEQ\_LEN = 24$, 6 hours at 15-minute intervals), normalized by training cohort statistics: $z = \frac{g - \mu}{\sigma}$.
- **Decoder Start Token:** Last 2 known observations ($LABEL\_LEN = 2$, 30 minutes) + 8 zeros for prediction steps.
- **Forecast Horizon:** Exactly 8 future steps ($PRED\_LEN = 8$, representing +15, +30, +45, +60, +75, +90, +105, +120 minutes).
- **Quantile Outputs:** 5 simultaneous quantiles: `0.10`, `0.25`, `0.50` (median), `0.75`, `0.90`.
- **Multi-Task Risk Prediction Head:** 2-layer MLP (`Linear(7, 32) -> GELU -> Linear(32, 3)`) reading the 5 predicted quantiles, the most recent glucose value, and normalized step position, producing calibrated softmax probabilities over 3 physiological risk classes:
  - **HYPO:** $< 70\text{ mg/dL}$ (Alert triggered if probability $\ge 30\%$)
  - **NORMAL:** $70 \text{ to } 180\text{ mg/dL}$ (Target physiological range)
  - **HYPER:** $> 180\text{ mg/dL}$ (Alert triggered if probability $\ge 50\%$)

### Exact Checkpoint Loading Procedure
1. Checkpoint metadata is loaded from `runs/<experiment>/run_info.json` to extract exact `arch` dictionary, normalization parameters (`norm.mean`, `norm.std`), and `mark_dim`.
2. The PyTorch model `GlucoseNet` is instantiated using `gp_model.build_net(repo, arch, device)`.
3. Checkpoint weights are deserialized from `runs/<experiment>/best.pt` with `torch.load(..., map_location=device, weights_only=False)`.
4. `net.load_state_dict(checkpoint["model"])` loads weights into both the GPFormer transformer and the risk MLP head.
5. The model is switched to evaluation mode (`net.eval()`) and executed inside `torch.no_grad()`.

---

## 2. Directory Layout

```text
diabetes/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py         # Paths, physiological limits, thresholds
│   │   ├── models.py         # Pydantic request/response schemas
│   │   ├── validation.py     # 24-point strict sequence validation
│   │   ├── inference.py      # GPFormerEngine (loading, caching, inference)
│   │   └── main.py           # FastAPI app & routing
│   ├── tests/
│   │   ├── test_validation.py        # Tests 1, 2, 3: Length, NaN, out-of-bounds
│   │   ├── test_inference.py         # Tests 4, 5, 6, 7, 10: Checkpoints, shapes, CI, offline eval
│   │   ├── test_api.py               # Test 8: Endpoints & error responses
│   │   └── test_frontend_contract.py # Test 9: Frontend form submission contracts
│   ├── requirements.txt
│   └── run_tests.py          # Automated test runner
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Header.jsx            # Brand, experiment picker, health indicator
│   │   │   ├── GlucoseInputForm.jsx  # 24 inputs, timestamp picker, synthetic presets
│   │   │   ├── ForecastChart.jsx     # Recharts 24h history + 8-step forecast + CI
│   │   │   ├── ForecastTable.jsx     # Step-by-step quantiles & risk probability bars
│   │   │   ├── ClinicalAlertCard.jsx # Prominent clinical warning card
│   │   │   ├── ModelInfoCard.jsx     # Checkpoint metadata & medical disclaimer
│   │   │   └── ErrorBanner.jsx       # Diagnostic error boundary
│   │   ├── services/
│   │   │   └── api.js                # Frontend API client
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css                 # Responsive clinical styling
│   ├── package.json
│   └── vite.config.js
├── gpformer/                 # Cloned GPFormer repository (models, layers, utils)
├── scripts/                  # Project data and training scripts
│   ├── gp_data.py
│   ├── gp_model.py
│   ├── gp_train.py
│   ├── gp_eval.py
│   └── resume_utils.py
├── runs/                     # Experiment checkpoints & run metadata
│   ├── gp_A/
│   │   ├── best.pt
│   │   └── run_info.json
│   └── gp_B/
│       ├── best.pt
│       └── run_info.json
├── .env.example
└── README.md
```

---

## 3. Installation & Setup

### Prerequisites
- Python 3.10+ (Tested on Python 3.12 / 3.13)
- Node.js 18+ and npm

### Backend Setup
1. Open a terminal in the project directory:
   ```bash
   cd backend
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Frontend Setup
1. In another terminal, navigate to `frontend`:
   ```bash
   cd frontend
   npm install
   ```

---

## 4. Running the Application

### 1. Launch FastAPI Backend
```bash
# In the diabetes/ directory:
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
The interactive Swagger API documentation will be available at:
👉 `http://localhost:8000/docs`

### 2. Launch React Frontend
```bash
# In the diabetes/frontend directory:
npm run dev
```
Open your browser at:
👉 `http://localhost:5173`

---

## 5. API Reference & Examples

### Health Check
`GET /health`
```json
{
  "status": "healthy",
  "api_online": true,
  "model_loaded": true,
  "current_experiment": "gp_A",
  "available_experiments": ["gp_A", "gp_B"]
}
```

### Model Information
`GET /model-info`
```json
{
  "active_experiment": "gp_A",
  "input_sequence_length": 24,
  "sampling_interval_minutes": 15,
  "total_history_hours": 6.0,
  "forecast_horizon_steps": 8,
  "forecast_horizon_minutes": 120,
  "quantiles_output": [0.1, 0.25, 0.5, 0.75, 0.9],
  "risk_classes": ["HYPO", "NORMAL", "HYPER"],
  "thresholds": { "hypo": 70.0, "hyper": 180.0 },
  "available_experiments": [
    {
      "experiment_id": "gp_A",
      "name": "Experiment A (REPLACE-BG)",
      "description": "Trained on REPLACE-BG T1D cohort",
      "checkpoint_available": true,
      "normalization_mean": 148.5,
      "normalization_std": 52.3,
      "training_sources": ["replacebg"]
    },
    {
      "experiment_id": "gp_B",
      "name": "Experiment B (REPLACE-BG + Shanghai T2D)",
      "description": "Trained on REPLACE-BG T1D and Shanghai T2D cohorts",
      "checkpoint_available": true,
      "normalization_mean": 151.2,
      "normalization_std": 54.1,
      "training_sources": ["replacebg", "shanghai_t2d"]
    }
  ]
}
```

### Predict Glucose
`POST /predict`

**Request Payload:**
```json
{
  "readings": [
    142, 138, 135, 132, 129, 127, 125, 128, 131, 134, 139, 145,
    148, 151, 147, 143, 140, 136, 133, 130, 128, 131, 135, 139
  ],
  "latest_timestamp": "2026-10-27T12:00:00",
  "experiment": "gp_A"
}
```

**Response Payload:**
```json
{
  "status": "success",
  "experiment": "gp_A",
  "experiment_description": "Experiment A (REPLACE-BG)",
  "units": "mg/dL",
  "input_summary": {
    "count": 24,
    "latest_glucose_mg_dl": 139.0,
    "latest_timestamp": "2026-10-27T12:00:00",
    "sampling_interval_minutes": 15,
    "mean_glucose_mg_dl": 136.2,
    "min_glucose_mg_dl": 125.0,
    "max_glucose_mg_dl": 151.0
  },
  "forecast": [
    {
      "step": 1,
      "horizon_minutes": 15,
      "timestamp": "2026-10-27T12:15:00",
      "glucose_median": 113.0,
      "quantiles": { "q10": 103.3, "q25": 107.5, "q50": 113.0, "q75": 116.2, "q90": 119.8 },
      "uncertainty_band": { "low_q10": 103.3, "high_q90": 119.8, "bandwidth": 16.5 },
      "risk_probabilities": { "hypo": 0.3488, "normal": 0.3218, "hyper": 0.3295 },
      "predicted_risk_class": "HYPO"
    },
    {
      "step": 2,
      "horizon_minutes": 30,
      "timestamp": "2026-10-27T12:30:00",
      "glucose_median": 124.9,
      "quantiles": { "q10": 109.9, "q25": 116.8, "q50": 124.9, "q75": 135.1, "q90": 147.8 },
      "uncertainty_band": { "low_q10": 109.9, "high_q90": 147.8, "bandwidth": 37.9 },
      "risk_probabilities": { "hypo": 0.3332, "normal": 0.3374, "hyper": 0.3294 },
      "predicted_risk_class": "NORMAL"
    }
  ],
  "clinical_alert": {
    "status": "HYPO_RISK",
    "message": "HYPO RISK: low glucose (< 70 mg/dL) possible by about +15 min (alert probability >= 30%).",
    "alert_horizon_minutes": 15
  },
  "model_version": "GPFormer-v1.0 (MLDG + Quantile Decoder + Multi-Task Risk Head)",
  "disclaimer": "EXPERIMENTAL MODEL PREDICTION ONLY. Forecasts are generated by a research neural network and must not be used as clinical diagnostic criteria, CGM replacement, or insulin dosing guidance."
}
```

---

## 6. Running Automated Tests

To execute the test suite (all 20 unit, integration, validation, and offline agreement tests):

```bash
python backend/run_tests.py
```

Test coverage:
1. **Input Validation:** Exactly 24 chronological glucose entries accepted.
2. **Length Checks:** Rejection of 23 and 25 readings with 422 Unprocessable Entity.
3. **Value Integrity:** Rejection of null, NaN, infinite, non-numeric, and non-physiological readings ($<20$ or $>600\text{ mg/dL}$).
4. **Model Loading:** Dynamic loading of Experiment A and Experiment B checkpoints.
5. **Inference & Shapes:** Output shape verification ($8 \times 5$ quantiles and $8 \times 3$ probabilities).
6. **Quantiles & Timing:** Monotonic uncertainty interval bounds and +15 min spacing.
7. **Risk Class Mapping:** Correct mapping for $<70$, $70\text{--}180$, and $>180\text{ mg/dL}$.
8. **API Diagnostics:** Response structures for `/health`, `/model-info`, and `/predict`.
9. **Frontend Contracts:** Request and response schema contracts.
10. **Offline Pipeline Agreement:** Validated that web inference matches `gp_model.predict` within numerical precision tolerance.

---

## 7. Connecting Google Drive / Colab Checkpoints

If you have trained new checkpoints in Google Colab (e.g., from `/content/drive/MyDrive/glucose_work/runs/`), you can seamlessly sync them:
1. Copy your Colab `runs/gp_A` or `runs/gp_B` directory directly into the `runs/` folder in this repository:
   ```text
   runs/
   ├── gp_A/
   │   ├── best.pt
   │   └── run_info.json
   └── gp_B/
       ├── best.pt
       └── run_info.json
   ```
2. Restart the FastAPI server, or the API will auto-detect the checkpoints on reload. No retraining or code changes required!
