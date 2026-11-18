import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel

from ..db.database import db

logger = logging.getLogger("gpformer_api.history")

router = APIRouter(prefix="/v1/history", tags=["Patient History"])

class ClearResponse(BaseModel):
    status: str
    message: str

def get_optional_user_id(request: Request) -> str:
    """Extracts session user if available, otherwise defaults to patient-default."""
    try:
        from ..auth.security import get_current_user_from_request
        user = get_current_user_from_request(request)
        if user:
            return user.id
    except Exception:
        pass
    return "patient-default"

@router.get("/predictions")
def get_prediction_history(request: Request, limit: int = 50):
    """Retrieves chronological patient inputs and model prediction outcomes."""
    user_id = get_optional_user_id(request)
    records = db.get_patient_predictions(user_id=user_id, limit=limit)
    return {
        "status": "success",
        "count": len(records),
        "history": records
    }

@router.delete("/predictions", response_model=ClearResponse)
def clear_prediction_history(request: Request):
    """Clears stored prediction records."""
    user_id = get_optional_user_id(request)
    db.clear_patient_predictions(user_id=user_id)
    return ClearResponse(status="success", message="Patient prediction history cleared.")

@router.get("/chat")
def get_chat_history(request: Request, limit: int = 50):
    """Retrieves patient educational chat history with GlucoGuide AI."""
    user_id = get_optional_user_id(request)
    messages = db.get_patient_chat_history(user_id=user_id, limit=limit)
    return {
        "status": "success",
        "count": len(messages),
        "history": messages
    }

@router.delete("/chat", response_model=ClearResponse)
def clear_chat_history(request: Request):
    """Clears patient chat history."""
    user_id = get_optional_user_id(request)
    db.clear_patient_chat_history(user_id=user_id)
    return ClearResponse(status="success", message="Patient chat history cleared.")
