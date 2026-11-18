import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_chat_endpoint_online(client):
    """Verify that /v1/chat endpoint processes user queries and returns a valid reply."""
    payload = {
        "message": "What is the Rule of 15 for hypoglycemia?",
        "history": []
    }
    res = client.post("/v1/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "reply" in data
    assert len(data["reply"]) > 20
    assert data["model"] is not None

def test_chat_with_glucose_context(client):
    """Verify that telemetry glucose context is passed properly to the chatbot."""
    payload = {
        "message": "What should I do right now?",
        "history": [],
        "glucose_context": {
            "current_glucose": 62.0,
            "trend": "falling",
            "predicted_30m": 55.0,
            "risk_class": "HYPO_RISK",
            "hypo_probability": 0.85
        }
    }
    res = client.post("/v1/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "reply" in data
    assert len(data["reply"]) > 20
