import abc
import base64
import hashlib
import json
import secrets
import time
import urllib.request
import urllib.parse
from typing import Optional, Any
from ..config import settings

def generate_code_verifier() -> str:
    """Generates a high-entropy cryptographic code verifier for PKCE."""
    return secrets.token_urlsafe(64)

def generate_code_challenge(verifier: str) -> str:
    """Computes code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

class OAuthProvider(abc.ABC):
    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        pass

    @abc.abstractmethod
    def get_authorization_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: Optional[str] = None
    ) -> str:
        pass

    @abc.abstractmethod
    def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: Optional[str] = None
    ) -> dict[str, Any]:
        pass

    @abc.abstractmethod
    def verify_id_token(
        self,
        id_token: str,
        expected_nonce: Optional[str] = None
    ) -> dict[str, Any]:
        pass

class GoogleOAuthProvider(OAuthProvider):
    AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    TOKENINFO_ENDPOINT = "https://oauth2.googleapis.com/tokeninfo"

    @property
    def provider_name(self) -> str:
        return "google"

    def get_authorization_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: Optional[str] = None
    ) -> str:
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri or settings.OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile", # Strictly openid, email, profile. No birthday/gender.
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "select_account"
        }
        return f"{self.AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: Optional[str] = None
    ) -> dict[str, Any]:
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri or settings.OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier
        }).encode("utf-8")

        req = urllib.request.Request(
            self.TOKEN_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise ValueError(f"Failed to exchange OAuth code: {error_body}")
        except Exception as e:
            raise ValueError(f"OAuth code exchange failed: {e}")

    def verify_id_token(
        self,
        id_token: str,
        expected_nonce: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Verifies ID token with Google's servers, validating signature, issuer, audience, and expiry.
        """
        url = f"{self.TOKENINFO_ENDPOINT}?id_token={urllib.parse.quote(id_token)}"
        try:
            with urllib.request.urlopen(url, timeout=10.0) as resp:
                claims = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise ValueError(f"Invalid Google ID token: {error_body}")
        except Exception as e:
            raise ValueError(f"ID token verification failed: {e}")

        # Check audience
        aud = claims.get("aud")
        if aud != settings.GOOGLE_CLIENT_ID:
            raise ValueError(f"ID token audience mismatch: expected {settings.GOOGLE_CLIENT_ID}, got {aud}")

        # Check issuer
        iss = claims.get("iss")
        if iss not in ("accounts.google.com", "https://accounts.google.com"):
            raise ValueError(f"ID token issuer mismatch: {iss}")

        # Check expiration
        exp = int(claims.get("exp", 0))
        if exp < time.time():
            raise ValueError("ID token has expired.")

        # Check nonce if available
        if expected_nonce and "nonce" in claims:
            if claims["nonce"] != expected_nonce:
                raise ValueError("ID token nonce mismatch.")

        return {
            "sub": claims["sub"],
            "email": claims["email"],
            "name": claims.get("name", claims.get("email", "").split("@")[0]),
            "picture": claims.get("picture")
        }

class MockOAuthProvider(OAuthProvider):
    """
    Mock OAuth provider for test suites and offline local development.
    Supports full PKCE, state, nonce validation, and simulated token exchange.
    """
    def __init__(self):
        self.valid_codes: dict[str, dict[str, str]] = {}
        self.issued_tokens: dict[str, dict[str, Any]] = {}

    @property
    def provider_name(self) -> str:
        return "mock"

    def register_mock_code(self, code: str, verifier: str, user_info: dict[str, Any], nonce: Optional[str] = None):
        challenge = generate_code_challenge(verifier)
        self.valid_codes[code] = {
            "verifier": verifier,
            "challenge": challenge,
            "user_info": user_info,
            "nonce": nonce or ""
        }

    def get_authorization_url(
        self,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: Optional[str] = None
    ) -> str:
        base = redirect_uri or settings.OAUTH_REDIRECT_URI
        # Generate an automatic code for mock flow
        code = f"mock_code_{secrets.token_hex(8)}"
        self.valid_codes[code] = {
            "challenge": code_challenge,
            "user_info": {
                "sub": "mock_sub_12345",
                "email": "researcher@example.org",
                "name": "Dr. Research User"
            },
            "nonce": nonce
        }
        return f"{base}?code={code}&state={state}"

    def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: Optional[str] = None
    ) -> dict[str, Any]:
        if code not in self.valid_codes:
            raise ValueError(f"Invalid mock authorization code: {code}")
        
        entry = self.valid_codes[code]
        expected_challenge = generate_code_challenge(code_verifier)
        if entry["challenge"] != expected_challenge:
            raise ValueError("PKCE code_verifier does not match code_challenge.")

        # Create mock ID token
        token_id = f"mock_jwt_{secrets.token_hex(16)}"
        user = entry["user_info"]
        self.issued_tokens[token_id] = {
            "sub": user["sub"],
            "email": user["email"],
            "name": user["name"],
            "aud": "mock_client_id",
            "iss": "mock_issuer",
            "exp": int(time.time()) + 3600,
            "nonce": entry.get("nonce", "")
        }
        return {"id_token": token_id, "access_token": f"mock_at_{secrets.token_hex(8)}"}

    def verify_id_token(
        self,
        id_token: str,
        expected_nonce: Optional[str] = None
    ) -> dict[str, Any]:
        # Handle expired / invalid test tokens
        if id_token == "expired_token":
            raise ValueError("ID token has expired.")
        if id_token == "wrong_audience_token":
            raise ValueError("ID token audience mismatch.")

        claims = self.issued_tokens.get(id_token)
        if not claims:
            # Fallback simple mock payload for test tokens
            if id_token.startswith("mock_jwt_"):
                return {
                    "sub": "mock_user_id",
                    "email": "user@example.com",
                    "name": "Test User"
                }
            raise ValueError(f"Unrecognized mock token: {id_token}")

        if claims["exp"] < time.time():
            raise ValueError("ID token has expired.")

        if expected_nonce and claims.get("nonce"):
            if claims["nonce"] != expected_nonce:
                raise ValueError("ID token nonce mismatch.")

        return {
            "sub": claims["sub"],
            "email": claims["email"],
            "name": claims["name"]
        }

mock_oauth_provider = MockOAuthProvider()
google_oauth_provider = GoogleOAuthProvider()

def get_oauth_provider(name: str = "google") -> OAuthProvider:
    if name.lower() == "mock":
        return mock_oauth_provider
    return google_oauth_provider
