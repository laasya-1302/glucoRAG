# GPFormer Multimodal Glucose Forecasting & Clinical Dashboard

A production-grade, clinical-style research prototype connecting the **E1 Multimodal GPFormer 3-Seed Ensemble** (s42, s123, s2026) and legacy univariate checkpoints to a **FastAPI** Python backend and a responsive **React (Vite)** clinical dashboard.

---

## 1. System Architecture & Model Contract

### Multimodal 9-Channel Architecture (Part A)
- **Input Window:** Exactly 24 chronological slots spaced 15 minutes apart (6 hours total). Slot #24 (index 23) represents "now" (the latest reading).
- **9 Input Channels per Slot:**
  1. `0: glucose`: Standardized glucose $z = \frac{g - \mu}{\sigma}$ using `manifests/scalers_v1.json` ($\mu = 159.927$, $\sigma = 63.562$).
  2. `1: sin_tod`: $\sin\left(\frac{2\pi \cdot \text{tod}}{1440}\right)$ where $\text{tod}$ is local minutes since midnight of that slot.
  3. `2: cos_tod`: $\cos\left(\frac{2\pi \cdot \text{tod}}{1440}\right)$.
  4. `3: bolus`: Scaled units $\min\left(\frac{\text{units}}{14.9}, 3.0\right)$.
  5. `4: basal`: Scaled rate $\min\left(\frac{\text{U/h}}{3.6}, 3.0\right)$.
  6. `5: carbs`: Scaled grams $\min\left(\frac{\text{grams}}{95.0}, 3.0\right)$.
  7. `6: m_bolus`: Availability mask for bolus ($0$ if unavailable, $1$ if available).
  8. `7: m_basal`: Availability mask for basal ($0$ if unavailable, $1$ if available).
  9. `8: m_carb`: Availability mask for carbs ($0$ if unavailable, $1$ if available).

- **Three Payload States per Modality:**
  - **Not Available (`null`):** Value = 0, Mask = 0 across all slots.
  - **Available, None Given (`[]`):** Value = 0, Mask = 1 across all slots.
  - **Available, Events Given (`[...]`):** Value = scaled sum per slot, Mask = 1 across all slots.

- **Event Slot Assignment:**
  - An event at timestamp $t$ lands in the **first slot** whose timestamp is $\ge t$ (e.g., $12:07 \to 12:15$ slot, never $12:00$).
  - Multiple events mapped to the same slot are summed.
  - Events later than the latest reading ($t > t_{23}$) or earlier than $t_0 - 15\text{ min}$ are rejected with `422 {code, message}`.
  - Basal rate applies from its start time up to 24 hours lookback.

- **Forecasting Mode:**
  - If bolus, basal, and carbs are all `null` $\implies$ `cgm_only` (eval thresholds key `"E1_cgmonly"`).
  - If any input is supplied (even `[]`) $\implies$ `multimodal` (eval thresholds key `"E1"`).

- **Result Semantics:**
  - **Forecast Class (Median-Derived):** Derived strictly from the median prediction ($\text{low} < 70$, $\text{normal } 70\text{--}180$, $\text{high} > 180\text{ mg/dL}$).
  - **Threshold Alerts:** Derived separately from calibrated probabilities and `manifests/frozen_eval_v1.json` (`"Possible low glucose"` / `"Possible high glucose"` / `null`). Cells are **never** labeled "HYPO" based on the alert alone.

---

## 2. Authentication, Privacy & Security (Part B)

- **OAuth 2.0 / OpenID Connect:**
  - Google OIDC Authorization Code Flow with PKCE (`S256` code challenge and high-entropy code verifier), state parameter, and cryptographic nonce.
  - Verification on the server: validates signature, audience (`GOOGLE_CLIENT_ID`), issuer (`accounts.google.com`), and expiration.
  - Requests strictly minimal scopes: `openid email profile`. No birthday or gender scopes.
  - Extensible, provider-agnostic interface with an included `MockOAuthProvider` for automated testing and offline development.

- **Researcher Profile Completion Gate:**
  - Mandatory profile step after first login before forecasting access is granted:
    - Full Name (prefilled from OAuth provider, editable, required)
    - Age in years (required, whole number $1\text{--}120$)
    - Gender (optional: Female / Male / Non-binary / Other / Prefer not to say)
    - Consent checkbox linking to research prototype terms and privacy notice.
  - **Pediatric Safety Warning (<18):** Prominent notice *"This model has not been tested on children."* with mandatory explicit confirmation checkbox.
  - Name, age, and gender are stored solely for session management and are **never** passed to the forecasting neural network.

- **Sessions & Health Data Privacy:**
  - Sessions stored in signed, `httpOnly`, `SameSite=Lax`, `Secure` (production) cookies. No auth tokens in `localStorage`.
  - CSRF protection via double-submit `X-CSRF-Token` validation on all state-changing routes.
  - Rate limiting on auth endpoints.
  - **Zero Health Data Persistence:** SQLite `users` table stores only `id`, `provider`, `provider_sub`, `email`, `name`, `age`, `gender`, `minor_confirmed`, `consent_timestamp`, and `created_at`. No glucose, insulin, or carb data is logged or persistently stored.
  - Complete "Edit Profile" and permanent "Delete my account and data" self-service actions.

---

## 3. Environment Variables & Google Cloud OAuth Setup

### Environment Variables (`.env.example`)
Create a `.env` file in the project root:

```ini
# Environment Mode (development or production)
ENVIRONMENT=development

# Frontend Base URL
FRONTEND_URL=http://localhost:5173

# SQLite Database Storage Path
DB_PATH=data/app.db

# Cryptographic Session Cookie HMAC Secret (Generate using: python -c "import secrets; print(secrets.token_hex(32))")
SESSION_SECRET=your_32_byte_session_hmac_secret_here

# Local Development Bypass (STRICTLY disabled in production)
AUTH_DISABLED=false

# Google OAuth 2.0 / OpenID Connect Credentials
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
OAUTH_REDIRECT_URI=http://localhost:8000/auth/google/callback
```

### Google Cloud Console OAuth 2.0 Configuration
1. Open [Google Cloud Console](https://console.cloud.google.com/).
2. Create or select an existing project.
3. Navigate to **APIs & Services** $\to$ **OAuth consent screen**:
   - User Type: **External** (or Internal if using Google Workspace).
   - App Name: `BioTective GPFormer Research`.
   - Scopes: Select `.../auth/userinfo.email`, `.../auth/userinfo.profile`, and `openid`.
   - Save and proceed.
4. Navigate to **APIs & Services** $\to$ **Credentials**:
   - Click **Create Credentials** $\to$ **OAuth client ID**.
   - Application Type: **Web application**.
   - Name: `BioTective Web App`.
   - **Authorized JavaScript origins:** `http://localhost:5173`, `http://localhost:8000`
   - **Authorized redirect URIs:** `http://localhost:8000/auth/google/callback`
5. Copy the generated **Client ID** and **Client Secret** into your `.env` file.

---

## 4. How to Run Backend & Frontend

### 1. Backend Setup & Startup
```powershell
# From the repository root:
# Activate virtual environment
& "glucoRAG\backend\venv\Scripts\Activate.ps1"

# Run FastAPI backend with Uvicorn
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
The API documentation is accessible at `http://localhost:8000/docs`.

### 2. Frontend Setup & Startup
```powershell
# In a separate terminal:
cd frontend
npm install
npm run dev
```
Open your browser at `http://localhost:5173`.

---

## 5. Automated Verification & Acceptance Tests

Execute the comprehensive test suite (all 58 tests across 7 verification suites):

```powershell
& "glucoRAG\backend\venv\Scripts\python.exe" backend\run_tests.py
```

### Acceptance Checks: Demo Presets A–G Verification
All 7 demo presets reproduce the exact expected medians from the reference notebook:

| Preset | Description | Target (+30/+60/+90/+120) | Actual Median | P(hypo) (+30/+60/+90/+120) | Status |
|:---:|:---|:---:|:---:|:---:|:---:|
| **A** | Glucose only (CGM-only) | 59/79/97/106 | **59/79/97/106** | 0.514 / 0.248 / 0.152 / 0.107 | **EXACT MATCH** |
| **B** | Multimodal, no insulin, no carbs | 61/84/102/113 | **61/84/102/113** | 0.516 / 0.224 / 0.140 / 0.085 | **EXACT MATCH** |
| **C** | Carbs 30 g, insulin unavailable | 67/88/103/111 | **67/88/103/111** | 0.315 / 0.179 / 0.129 / 0.086 | **EXACT MATCH** |
| **D** | Carbs 60 g, insulin unavailable | 82/103/111/113 | **82/103/111/113** | 0.161 / 0.122 / 0.104 / 0.080 | **EXACT MATCH** |
| **E** | Carbs 60 g, insulin available none | 83/108/114/117 | **83/108/114/117** | 0.150 / 0.111 / 0.099 / 0.072 | **EXACT MATCH** |
| **F** | Carbs 60 g + bolus 4 U | 84/109/114/117 | **84/109/114/117** | 0.144 / 0.110 / 0.099 / 0.072 | **EXACT MATCH** |
| **G** | Bolus 4 U, no carbs | 64/89/107/116 | **64/89/107/116** | 0.471 / 0.187 / 0.126 / 0.075 | **EXACT MATCH** |

---

## 6. Assumptions & Open Questions

1. **Policy for Minors (< 18):**
   - *Current Implementation:* Displays a prominent warning banner (*"This model has not been tested on children."*) and requires explicit acknowledgement checkbox before profile completion. Form submission without acknowledgement is blocked.
   - *Open Question for Principal Investigator:* Should the system completely block minors (<18) or allow research access with verified parental/guardian consent?
2. **Additional OAuth Providers:**
   - *Current Implementation:* Built with an abstract `OAuthProvider` interface. Google OIDC and Mock provider are currently active.
   - *Open Question:* Would you like Apple, Microsoft, or Institutional SAML/OIDC providers added in the next release?
3. **Streamed / Clock Grid Latency:**
   - *Current Implementation:* In `grid: "clock"` mode, data is resampled to 15-minute clock marks ($\pm 2.5\text{ min}$) and strictly requires 24 continuous marks (returning `422 { code: "collecting_data", message: "Collecting data: N of 24 readings" }`).
   - *Assumption:* No missing slots are interpolated, following strict clinical data integrity guidelines.
