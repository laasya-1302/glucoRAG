import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import db
from app.auth.oauth import mock_oauth_provider, GoogleOAuthProvider

GLUCOSE_24 = [110, 98, 99, 89, 96, 92, 87, 85, 84, 81, 82, 80, 75, 73, 74, 72, 70, 68, 67, 66, 64, 62, 65, 60]

def test_unauthenticated_forecast_blocked():
    """Unauthenticated call to /v1/forecast must return 401 Unauthorized."""
    with TestClient(app) as client:
        res = client.post("/v1/forecast", json={"readings": GLUCOSE_24})
        assert res.status_code == 401

def test_oauth_google_login_flow():
    """GET /auth/google/login initiates flow, creates signed state cookie."""
    with TestClient(app) as client:
        res = client.get("/auth/google/login?format=json")
        assert res.status_code == 200
        data = res.json()
        assert "authorization_url" in data
        assert "accounts.google.com" in data["authorization_url"]
        assert "gpformer_oauth_state" in client.cookies

def test_oauth_callback_wrong_state_rejected():
    """Callback with wrong/tampered state must return 400."""
    with TestClient(app) as client:
        # Initiate login to get cookie
        client.get("/auth/google/login?format=json")
        # Attempt callback with mismatched state
        res = client.get("/auth/google/callback?code=fake_code&state=wrong_state_123")
        assert res.status_code == 400
        assert "InvalidState" in res.text

def test_id_token_validation_wrong_audience_and_expired():
    """Server ID token verification must reject wrong audience or expired tokens."""
    # Test with Mock provider verification
    with pytest.raises(ValueError, match="expired"):
        mock_oauth_provider.verify_id_token("expired_token")

    with pytest.raises(ValueError, match="audience mismatch"):
        mock_oauth_provider.verify_id_token("wrong_audience_token")

def test_profile_completion_required_before_app_opens():
    """First-time sign-in leaves profile incomplete; /v1/forecast returns 403 until profile completed."""
    with TestClient(app) as client:
        # Sign in with a new user
        res_login = client.post("/auth/mock/login", json={
            "email": "newuser@example.org",
            "name": "Jane Newbie",
            "sub": "newbie_sub_123"
        })
        assert res_login.status_code == 200
        csrf_token = res_login.json()["csrf_token"]
        client.headers.update({"X-CSRF-Token": csrf_token})

        # Profile is not completed yet
        me_res = client.get("/auth/me")
        assert me_res.status_code == 200
        assert me_res.json()["profile_complete"] is False

        # Attempting /v1/forecast should return 403 ProfileIncomplete
        res_fc = client.post("/v1/forecast", json={"readings": GLUCOSE_24})
        assert res_fc.status_code == 403
        assert "ProfileIncomplete" in res_fc.text

def test_under_18_minor_warning_and_confirmation():
    """Users under 18 require explicit minor confirmation; unconfirmed returns 422."""
    with TestClient(app) as client:
        res_login = client.post("/auth/mock/login", json={
            "email": "minor@example.org",
            "name": "Alex Minor",
            "sub": "minor_sub_789"
        })
        csrf_token = res_login.json()["csrf_token"]
        client.headers.update({"X-CSRF-Token": csrf_token})

        # Attempt profile completion for age 16 WITHOUT minor confirmation
        res_fail = client.post("/auth/profile", json={
            "name": "Alex Minor",
            "age": 16,
            "gender": "Other",
            "consent": True,
            "minor_confirmed": False
        })
        assert res_fail.status_code == 422
        assert "MinorConfirmationRequired" in res_fail.text

        # With explicit minor confirmation -> succeeds
        res_ok = client.post("/auth/profile", json={
            "name": "Alex Minor",
            "age": 16,
            "gender": "Other",
            "consent": True,
            "minor_confirmed": True
        })
        assert res_ok.status_code == 200
        assert res_ok.json()["user"]["profile_complete"] is True

        # Now forecast endpoint is unlocked
        res_fc = auth_client = client.post("/v1/forecast", json={"readings": GLUCOSE_24})
        assert res_fc.status_code == 200

def test_logout_clears_session():
    """Logout clears the session cookie and subsequent calls require re-auth."""
    with TestClient(app) as client:
        res_login = client.post("/auth/mock/login", json={
            "email": "logout_test@example.org",
            "name": "Logout User",
            "sub": "logout_sub_999"
        })
        csrf_token = res_login.json()["csrf_token"]
        client.headers.update({"X-CSRF-Token": csrf_token})

        # Logout
        res_out = client.post("/auth/logout")
        assert res_out.status_code == 200

        # /auth/me now returns 401
        res_me = client.get("/auth/me")
        assert res_me.status_code == 401

def test_delete_account_removes_profile():
    """Account deletion permanently removes stored user and invalidates session."""
    with TestClient(app) as client:
        res_login = client.post("/auth/mock/login", json={
            "email": "delete_me@example.org",
            "name": "Delete Tester",
            "sub": "delete_sub_456"
        })
        user_id = res_login.json()["user"]["id"]
        csrf_token = res_login.json()["csrf_token"]
        client.headers.update({"X-CSRF-Token": csrf_token})

        # Complete profile
        client.post("/auth/profile", json={
            "name": "Delete Tester",
            "age": 25,
            "gender": "Prefer not to say",
            "consent": True
        })

        assert db.get_user_by_id(user_id) is not None

        # Delete account
        del_res = client.delete("/auth/me")
        assert del_res.status_code == 200

        # Confirm user is removed from database
        assert db.get_user_by_id(user_id) is None
        # /auth/me returns 401
        assert client.get("/auth/me").status_code == 401
