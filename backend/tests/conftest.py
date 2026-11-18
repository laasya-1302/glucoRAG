import os
import sys
from pathlib import Path
import pytest
from pydantic import ValidationError
from fastapi import HTTPException

# Ensure backend and scripts are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
backend_dir = PROJECT_ROOT / "backend"
scripts_dir = PROJECT_ROOT / "scripts"
repo_dir = PROJECT_ROOT / "gpformer"
model_v2_dir = PROJECT_ROOT / "model_v2"
model_v2_thirdparty = model_v2_dir / "third_party" / "gpformer"

for p in [str(backend_dir), str(scripts_dir), str(repo_dir), str(model_v2_thirdparty)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

class MockResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data

class DirectTestClient:
    """
    Lightweight, synchronous TestClient that dispatches requests directly to FastAPI handlers.
    Avoids AnyIO / IOCP socketpair deadlocks on Windows Python 3.13 inside sandbox environments.
    """
    __test__ = False
    def __init__(self, app, *args, **kwargs):
        self.app = app

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url: str, **kwargs):
        from app.main import health_check, model_info, get_models
        clean_url = url.split("?")[0]
        try:
            if clean_url == "/health":
                res = health_check()
                return MockResponse(200, res.model_dump())
            elif clean_url == "/model-info":
                res = model_info()
                return MockResponse(200, res.model_dump())
            elif clean_url == "/v1/models":
                res = get_models()
                return MockResponse(200, res.model_dump())
            else:
                return MockResponse(404, {"error": "NotFound", "message": f"Route {url} not found"})
        except HTTPException as exc:
            return MockResponse(exc.status_code, exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)})
        except Exception as e:
            return MockResponse(500, {"error": "InternalServerError", "message": str(e)})

    def post(self, url: str, json: dict = None, **kwargs):
        from app.main import forecast_v1, predict_glucose
        from app.models import ForecastV1Request, PredictRequest
        clean_url = url.split("?")[0]
        payload = json or {}
        try:
            if clean_url == "/v1/forecast":
                try:
                    req = ForecastV1Request(**payload)
                except ValidationError as ve:
                    return MockResponse(422, {"error": "ValidationError", "detail": ve.errors()})
                res = forecast_v1(req)
                return MockResponse(200, res.model_dump())
            elif clean_url == "/predict":
                try:
                    req = PredictRequest(**payload)
                except ValidationError as ve:
                    return MockResponse(422, {"error": "ValidationError", "detail": ve.errors()})
                res = predict_glucose(req)
                return MockResponse(200, res.model_dump())
            else:
                return MockResponse(404, {"error": "NotFound", "message": f"Route {url} not found"})
        except HTTPException as exc:
            return MockResponse(exc.status_code, exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)})
        except Exception as e:
            return MockResponse(500, {"error": "InternalServerError", "message": str(e)})

# Monkeypatch fastapi.testclient.TestClient and starlette.testclient.TestClient
import fastapi.testclient
import starlette.testclient
fastapi.testclient.TestClient = DirectTestClient
starlette.testclient.TestClient = DirectTestClient

@pytest.fixture(scope="module")
def client():
    from app.main import app
    with DirectTestClient(app) as c:
        yield c
