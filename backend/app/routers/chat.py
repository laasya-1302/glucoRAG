import logging
import os
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
import httpx

from ..config import settings
from ..db.database import db

logger = logging.getLogger("gpformer_api.chat")

router = APIRouter(prefix="", tags=["Patient Chatbot"])

SYSTEM_INSTRUCTION = (
    "You are GlucoGuide, an empathetic, supportive, and evidence-based AI diabetes health educator. "
    "Your purpose is to assist patients and caregivers in understanding diabetes management, "
    "including carbohydrate tracking, meal planning, physical activity effects on glycemic control, "
    "continuous glucose monitoring (CGM) interpretation, and hypoglycemia/hyperglycemia precautions.\n\n"
    "Guidelines:\n"
    "1. Clinical Safety: Always emphasize safety. If blood glucose is below 70 mg/dL, recommend the standard 'Rule of 15' "
    "(15g fast-acting carbohydrates, wait 15 minutes, recheck).\n"
    "2. Scope Boundary: You are an educational decision-support tool, NOT a physician. Never prescribe specific insulin doses "
    "or tell the patient to alter their prescribed medication regimen without consulting their healthcare provider.\n"
    "3. Contextual Awareness: When glucose readings, trends, or GPFormer predictions are provided in the context, refer to them "
    "empathetically to help the user understand what the numbers mean.\n"
    "4. Disclaimer: Include a brief disclaimer that this is educational advice and in medical emergencies emergency services "
    "or a doctor must be contacted."
)

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'model' / 'assistant'")
    content: str = Field(..., description="Message text")

class GlucoseContext(BaseModel):
    current_glucose: Optional[float] = None
    trend: Optional[str] = None
    predicted_30m: Optional[float] = None
    risk_class: Optional[str] = None
    hypo_probability: Optional[float] = None
    hyper_probability: Optional[float] = None

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Patient message")
    history: List[ChatMessage] = Field(default_factory=list, description="Previous conversation messages")
    glucose_context: Optional[GlucoseContext] = None

class ChatResponse(BaseModel):
    reply: str
    model: str
    status: str = "ok"

FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-flash-latest"
]

@router.post("/v1/chat", response_model=ChatResponse)
@router.post("/chat", response_model=ChatResponse)
async def chat_with_glucoguide(request: ChatRequest, raw_request: Request = None):
    """
    Patient decision-support and educational chatbot powered by Google Gemini.
    Provides evidence-based lifestyle, nutrition, and CGM trend guidance.
    """
    api_key = (
        getattr(settings, "GEMINI_API_KEY", "")
        or os.getenv("GEMINI_API_KEY", "")
        or os.getenv("GOOGLE_API_KEY", "")
    ).strip().strip('"\'')

    if not api_key or api_key.startswith("your_"):
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured in .env. Please configure GEMINI_API_KEY."
        )

    # Build prompt contents with context
    contents = []

    # If glucose context is present, add it as contextual note
    context_note = ""
    if request.glucose_context:
        ctx = request.glucose_context
        parts = []
        if ctx.current_glucose is not None:
            parts.append(f"Current Glucose: {ctx.current_glucose:.1f} mg/dL")
        if ctx.trend:
            parts.append(f"Trend: {ctx.trend}")
        if ctx.predicted_30m is not None:
            parts.append(f"30-min Forecast: {ctx.predicted_30m:.1f} mg/dL")
        if ctx.risk_class:
            parts.append(f"Risk Status: {ctx.risk_class}")
        if ctx.hypo_probability is not None:
            parts.append(f"Hypo Risk: {ctx.hypo_probability*100:.0f}%")
        if parts:
            context_note = f"[Patient CGM Telemetry Context: {', '.join(parts)}]\n\n"

    # Convert past history
    for msg in request.history[-10:]: # Keep last 10 messages for context
        role = "model" if msg.role in ("assistant", "model") else "user"
        contents.append({
            "role": role,
            "parts": [{"text": msg.content}]
        })

    # Add current user prompt
    user_prompt = context_note + request.message
    contents.append({
        "role": "user",
        "parts": [{"text": user_prompt}]
    })

    preferred_model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    candidate_models = [preferred_model] + [m for m in FALLBACK_MODELS if m != preferred_model]

    last_error = None
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 800
            }
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            reply_text = parts[0]["text"].strip()
                            user_id = "patient-default"
                            if raw_request:
                                try:
                                    from ..auth.security import get_current_user_from_request
                                    u = get_current_user_from_request(raw_request)
                                    if u:
                                        user_id = u.id
                                except Exception:
                                    pass

                            try:
                                ctx_dict = request.glucose_context.model_dump() if request.glucose_context else None
                                db.save_chat_message(user_id=user_id, role="user", message=request.message, glucose_context=ctx_dict)
                                db.save_chat_message(user_id=user_id, role="assistant", message=reply_text, model=model_name)
                            except Exception as db_err:
                                logger.warning(f"Failed to persist chat message to database: {db_err}")

                            return ChatResponse(
                                reply=reply_text,
                                model=model_name,
                                status="ok"
                            )
                elif resp.status_code in (404, 503):
                    logger.warning(f"Model {model_name} returned {resp.status_code}, trying fallback...")
                    last_error = resp.text
                    continue
                else:
                    logger.error(f"Gemini API returned error {resp.status_code}: {resp.text}")
                    last_error = resp.text
                    break
        except Exception as e:
            logger.warning(f"Failed to query {model_name}: {e}")
            last_error = str(e)
            continue

    raise HTTPException(
        status_code=502,
        detail=f"Unable to generate response from Gemini API: {last_error}"
    )
