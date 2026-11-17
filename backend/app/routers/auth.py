import base64
import hmac
import hashlib
import json
import secrets
import time
from typing import Optional, Literal
from fastapi import APIRouter, Request, Response, HTTPException, Depends, Query, status
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from ..config import settings
from ..db.database import db, UserRecord
from ..auth.oauth import (
    get_oauth_provider,
    generate_code_verifier,
    generate_code_challenge
)
from ..auth.security import (
    check_rate_limit,
    create_signed_session_cookie,
    clear_session_cookie,
    verify_csrf_token,
    require_active_user,
    get_current_user
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

OAUTH_STATE_COOKIE = "gpformer_oauth_state"

def sign_data(data_dict: dict) -> str:
    raw = json.dumps(data_dict).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii")
    sig = hmac.new(settings.SESSION_SECRET.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"

def verify_data(signed_str: Optional[str]) -> Optional[dict]:
    if not signed_str or "." not in signed_str:
        return None
    b64, sig = signed_str.rsplit(".", 1)
    expected_sig = hmac.new(settings.SESSION_SECRET.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        raw = base64.urlsafe_b64decode(b64.encode("ascii")).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None

# Pydantic Schemas for Auth
class ProfileUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="User full name")
    age: int = Field(..., ge=1, le=120, description="Age in years (1 to 120)")
    gender: Optional[Literal["Female", "Male", "Non-binary", "Other", "Prefer not to say"]] = None
    consent: bool = Field(..., description="Mandatory research prototype and privacy notice consent")
    minor_confirmed: Optional[bool] = Field(False, description="Explicit confirmation if user is under 18")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Name cannot be empty.")
        return s

class MockLoginRequest(BaseModel):
    email: str = "researcher@example.org"
    name: str = "Dr. Jane Research"
    sub: Optional[str] = None
    code: Optional[str] = None
    code_verifier: Optional[str] = None
    state: Optional[str] = None
    nonce: Optional[str] = None

@router.get("/google/login")
async def google_login(request: Request, response: Response):
    check_rate_limit(request)
    provider = get_oauth_provider("google")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    auth_url = provider.get_authorization_url(
        state=state,
        nonce=nonce,
        code_challenge=code_challenge
    )

    state_payload = {
        "state": state,
        "nonce": nonce,
        "code_verifier": code_verifier,
        "exp": int(time.time()) + 600 # 10 minutes
    }
    signed_state = sign_data(state_payload)

    # If request accepts JSON or has json param, return the url
    if "application/json" in request.headers.get("accept", "") or request.query_params.get("format") == "json":
        res = JSONResponse({"authorization_url": auth_url, "state": state})
    else:
        res = RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)

    res.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=signed_state,
        max_age=600,
        httponly=True,
        secure=settings.ENVIRONMENT.lower() == "production",
        samesite="lax",
        path="/"
    )
    return res

@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None
):
    check_rate_limit(request)
    if error:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error={error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail={"error": "MissingParameters", "message": "Code and state required."})

    raw_state_cookie = request.cookies.get(OAUTH_STATE_COOKIE)
    state_data = verify_data(raw_state_cookie)
    if not state_data or state_data.get("state") != state or state_data.get("exp", 0) < time.time():
        raise HTTPException(
            status_code=400,
            detail={"error": "InvalidState", "message": "OAuth state parameter invalid or expired."}
        )

    code_verifier = state_data["code_verifier"]
    expected_nonce = state_data.get("nonce")

    provider = get_oauth_provider("google")
    try:
        tokens = provider.exchange_code(code=code, code_verifier=code_verifier)
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("No ID token returned from token endpoint.")

        claims = provider.verify_id_token(id_token=id_token, expected_nonce=expected_nonce)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "AuthenticationFailed", "message": str(e)}
        )

    # Provision user and session
    user = db.get_or_create_user(
        provider="google",
        provider_sub=claims["sub"],
        email=claims["email"],
        name=claims.get("name") or claims["email"].split("@")[0]
    )

    session_id, csrf_token = db.create_session(user.id, settings.SESSION_MAX_AGE_SECONDS)

    res = RedirectResponse(f"{settings.FRONTEND_URL}/?auth=success", status_code=status.HTTP_302_FOUND)
    create_signed_session_cookie(res, session_id)
    res.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return res

@router.post("/mock/login")
async def mock_login(request: Request, response: Response, payload: MockLoginRequest):
    """
    Test harness endpoint for simulated OAuth login.
    """
    check_rate_limit(request)
    sub = payload.sub or f"mock_sub_{secrets.token_hex(6)}"
    user = db.get_or_create_user(
        provider="mock",
        provider_sub=sub,
        email=payload.email,
        name=payload.name
    )
    session_id, csrf_token = db.create_session(user.id, settings.SESSION_MAX_AGE_SECONDS)
    create_signed_session_cookie(response, session_id)
    return {
        "status": "success",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "age": user.age,
            "gender": user.gender,
            "profile_complete": user.profile_complete
        },
        "csrf_token": csrf_token
    }

@router.get("/me")
async def get_me(request: Request, user: UserRecord = Depends(require_active_user)):
    session = getattr(request.state, "session", None)
    csrf_token = session.csrf_token if session else ""
    return {
        "id": user.id,
        "provider": user.provider,
        "email": user.email,
        "name": user.name,
        "age": user.age,
        "gender": user.gender,
        "minor_confirmed": user.minor_confirmed,
        "profile_complete": user.profile_complete,
        "consent_timestamp": user.consent_timestamp,
        "csrf_token": csrf_token
    }

@router.post("/profile")
async def update_profile(
    request: Request,
    payload: ProfileUpdateRequest,
    user: UserRecord = Depends(require_active_user)
):
    session = getattr(request.state, "session", None)
    if session:
        verify_csrf_token(request, session)

    if not payload.consent:
        raise HTTPException(
            status_code=422,
            detail={"error": "ConsentRequired", "message": "Consent to research prototype terms is mandatory."}
        )

    if payload.age < 18 and not payload.minor_confirmed:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "MinorConfirmationRequired",
                "message": "Explicit confirmation required: this model has not been tested on children."
            }
        )

    updated = db.update_user_profile(
        user_id=user.id,
        name=payload.name,
        age=payload.age,
        gender=payload.gender,
        consent=payload.consent,
        minor_confirmed=bool(payload.minor_confirmed)
    )

    return {
        "status": "success",
        "user": {
            "id": updated.id,
            "email": updated.email,
            "name": updated.name,
            "age": updated.age,
            "gender": updated.gender,
            "minor_confirmed": updated.minor_confirmed,
            "profile_complete": updated.profile_complete,
            "consent_timestamp": updated.consent_timestamp
        }
    }

@router.post("/logout")
async def logout(request: Request, response: Response, user: UserRecord = Depends(require_active_user)):
    session = getattr(request.state, "session", None)
    if session:
        verify_csrf_token(request, session)
        db.delete_session(session.session_id)

    clear_session_cookie(response)
    return {"status": "success", "message": "Logged out successfully."}

@router.delete("/me")
async def delete_account(request: Request, response: Response, user: UserRecord = Depends(require_active_user)):
    session = getattr(request.state, "session", None)
    if session:
        verify_csrf_token(request, session)

    db.delete_user(user.id)
    clear_session_cookie(response)
    return {"status": "success", "message": "User account and all stored profile data permanently deleted."}
