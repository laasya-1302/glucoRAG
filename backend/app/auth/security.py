import hmac
import hashlib
import time
from collections import defaultdict
from typing import Optional
from fastapi import Request, HTTPException, Depends
from ..config import settings
from ..db.database import db, UserRecord, SessionRecord

# Rate limiter: in-memory IP -> list of timestamps
_rate_limit_lock = defaultdict(list)

def check_rate_limit(request: Request, max_requests: int = 20, window_seconds: int = 60):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    timestamps = _rate_limit_lock[client_ip]
    # Prune old timestamps
    valid = [ts for ts in timestamps if now - ts < window_seconds]
    if len(valid) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail={"error": "RateLimitExceeded", "message": "Too many requests. Please slow down."}
        )
    valid.append(now)
    _rate_limit_lock[client_ip] = valid

def sign_session_id(session_id: str) -> str:
    key = settings.SESSION_SECRET.encode("utf-8")
    sig = hmac.new(key, session_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{session_id}.{sig}"

def verify_signed_session_id(signed_value: Optional[str]) -> Optional[str]:
    if not signed_value or "." not in signed_value:
        return None
    session_id, sig = signed_value.rsplit(".", 1)
    key = settings.SESSION_SECRET.encode("utf-8")
    expected = hmac.new(key, session_id.encode("utf-8"), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected):
        return session_id
    return None

def create_signed_session_cookie(response, session_id: str):
    signed = sign_session_id(session_id)
    is_secure = settings.ENVIRONMENT.lower() == "production"
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=signed,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/"
    )

def clear_session_cookie(response):
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/"
    )

def verify_csrf_token(request: Request, session: SessionRecord):
    """
    Validates CSRF token on state-changing requests (POST, PUT, DELETE, PATCH).
    Reads from header 'X-CSRF-Token'.
    """
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        token = request.headers.get("X-CSRF-Token")
        if not token or not hmac.compare_digest(token, session.csrf_token):
            raise HTTPException(
                status_code=403,
                detail={"error": "CSRFCheckFailed", "message": "Invalid or missing CSRF token."}
            )

async def get_current_user(request: Request) -> Optional[UserRecord]:
    raw_cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_id = verify_signed_session_id(raw_cookie)
    if not session_id:
        return None

    session = db.get_session(session_id)
    if not session:
        return None

    # Attach session to request state for CSRF and route use
    request.state.session = session
    user = db.get_user_by_id(session.user_id)
    return user

async def require_active_user(
    request: Request,
    current_user: Optional[UserRecord] = Depends(get_current_user)
) -> UserRecord:
    # Check AUTH_DISABLED flag for local development only (strictly blocked in production)
    if settings.AUTH_DISABLED and settings.ENVIRONMENT.lower() != "production":
        # Return or provision a mock developer user
        dev_user = db.get_or_create_user("dev", "local_dev_user", "dev@example.org", "Dev Researcher")
        if not dev_user.profile_complete:
            dev_user = db.update_user_profile(dev_user.id, "Dev Researcher", 30, "Prefer not to say", True, True)
        return dev_user

    if not current_user:
        raise HTTPException(
            status_code=401,
            detail={"error": "Unauthorized", "message": "Authentication required. Please sign in."}
        )
    return current_user

async def require_complete_profile(
    user: UserRecord = Depends(require_active_user)
) -> UserRecord:
    if not user.profile_complete:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "ProfileIncomplete",
                "message": "User profile must be completed (name, age, consent) before using forecasting tools.",
                "user": {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "age": user.age,
                    "gender": user.gender,
                    "profile_complete": False
                }
            }
        )
    return user
