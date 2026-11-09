import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve base directories safely
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "GPFormer Glucose Forecasting API"
    VERSION: str = "1.0.0"
    
    # Model directories
    REPO_DIR: Path = Path(os.getenv("REPO_DIR", str(PROJECT_ROOT / "gpformer")))
    SCRIPTS_DIR: Path = Path(os.getenv("SCRIPTS_DIR", str(PROJECT_ROOT / "scripts")))
    RUNS_DIR: Path = Path(os.getenv("RUNS_DIR", str(PROJECT_ROOT / "runs")))
    
    DEFAULT_EXPERIMENT: str = os.getenv("DEFAULT_EXPERIMENT", "gp_A")
    AVAILABLE_EXPERIMENTS: list[str] = ["gp_A", "gp_B", "e1_gpformer", "experiment_a", "experiment_b"]
    
    # Domain parameters
    INPUT_STEPS: int = 24
    PRED_STEPS: int = 8
    SAMPLING_INTERVAL_MINUTES: int = 15
    MIN_GLUCOSE_MG_DL: float = 20.0
    MAX_GLUCOSE_MG_DL: float = 600.0
    
    # Clinical thresholds (mg/dL)
    HYPO_THRESHOLD: float = 70.0
    HYPER_THRESHOLD: float = 180.0
    HYPO_ALERT_PROBABILITY: float = 0.30  # As defined in gp_eval.py
    
    # Quantiles
    QUANTILES: tuple[float, ...] = (0.1, 0.25, 0.5, 0.75, 0.9)
    MEDIAN_INDEX: int = 2
    
    # Server / CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"
    ]
    
    model_config = {
        "env_file": ".env",
        "extra": "allow"
    }

settings = Settings()
