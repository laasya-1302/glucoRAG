import sqlite3
import uuid
import secrets
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, NamedTuple, Any, Dict, List
from ..config import settings

class UserRecord(NamedTuple):
    id: str
    provider: str
    provider_sub: str
    email: str
    name: str
    age: Optional[int]
    gender: Optional[str]
    minor_confirmed: bool
    consent_timestamp: Optional[str]
    created_at: str

    @property
    def profile_complete(self) -> bool:
        if not self.name or not self.name.strip():
            return False
        if self.age is None or not (1 <= self.age <= 120):
            return False
        if not self.consent_timestamp:
            return False
        if self.age < 18 and not self.minor_confirmed:
            return False
        return True

class SessionRecord(NamedTuple):
    session_id: str
    user_id: str
    csrf_token: str
    created_at: str
    expires_at: str

class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.DB_PATH
        self._ensure_dir()
        self.init_db()

    def _ensure_dir(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_sub TEXT NOT NULL,
                email TEXT NOT NULL,
                name TEXT NOT NULL,
                age INTEGER,
                gender TEXT,
                minor_confirmed INTEGER DEFAULT 0,
                consent_timestamp TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(provider, provider_sub)
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_predictions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                timestamp TEXT NOT NULL,
                model_id TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                results_json TEXT NOT NULL,
                summary TEXT NOT NULL
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_chat_history (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                model TEXT,
                glucose_context TEXT
            )
            """)
            conn.commit()

    def get_or_create_user(self, provider: str, provider_sub: str, email: str, name: str) -> UserRecord:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE provider = ? AND provider_sub = ?",
                (provider, provider_sub)
            ).fetchone()
            if row:
                return UserRecord(
                    id=row["id"],
                    provider=row["provider"],
                    provider_sub=row["provider_sub"],
                    email=row["email"],
                    name=row["name"],
                    age=row["age"],
                    gender=row["gender"],
                    minor_confirmed=bool(row["minor_confirmed"]),
                    consent_timestamp=row["consent_timestamp"],
                    created_at=row["created_at"]
                )

            new_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO users (id, provider, provider_sub, email, name, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (new_id, provider, provider_sub, email, name, now_iso)
            )
            conn.commit()
            return UserRecord(
                id=new_id,
                provider=provider,
                provider_sub=provider_sub,
                email=email,
                name=name,
                age=None,
                gender=None,
                minor_confirmed=False,
                consent_timestamp=None,
                created_at=now_iso
            )

    def get_user_by_id(self, user_id: str) -> Optional[UserRecord]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            return UserRecord(
                id=row["id"],
                provider=row["provider"],
                provider_sub=row["provider_sub"],
                email=row["email"],
                name=row["name"],
                age=row["age"],
                gender=row["gender"],
                minor_confirmed=bool(row["minor_confirmed"]),
                consent_timestamp=row["consent_timestamp"],
                created_at=row["created_at"]
            )

    def update_user_profile(
        self,
        user_id: str,
        name: str,
        age: int,
        gender: Optional[str],
        consent: bool,
        minor_confirmed: bool = False
    ) -> Optional[UserRecord]:
        now_iso = datetime.now(timezone.utc).isoformat()
        consent_ts = now_iso if consent else None
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET name = ?, age = ?, gender = ?, minor_confirmed = ?, consent_timestamp = coalesce(?, consent_timestamp)
                WHERE id = ?
                """,
                (name.strip(), age, gender, 1 if minor_confirmed else 0, consent_ts, user_id)
            )
            conn.commit()
        return self.get_user_by_id(user_id)

    def delete_user(self, user_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    def create_session(self, user_id: str, max_age_seconds: int = 86400 * 7) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=max_age_seconds)

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, user_id, csrf_token, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, csrf_token, now.isoformat(), expires.isoformat())
            )
            conn.commit()
        return session_id, csrf_token

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        if not session_id:
            return None
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                return None
            
            # Check expiry
            expires_at = datetime.fromisoformat(row["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return None

            return SessionRecord(
                session_id=row["session_id"],
                user_id=row["user_id"],
                csrf_token=row["csrf_token"],
                created_at=row["created_at"],
                expires_at=row["expires_at"]
            )

    def delete_session(self, session_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_user_sessions(self, user_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ══════════════════════════════════════════════════════════════
    # Patient Prediction & Input History
    # ══════════════════════════════════════════════════════════════

    def save_prediction(
        self,
        user_id: Optional[str],
        model_id: str,
        inputs: Dict[str, Any],
        results: Dict[str, Any],
        summary: str
    ) -> Dict[str, Any]:
        pred_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO patient_predictions (id, user_id, timestamp, model_id, inputs_json, results_json, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pred_id,
                    user_id or "patient-default",
                    now_iso,
                    model_id,
                    json.dumps(inputs),
                    json.dumps(results),
                    summary
                )
            )
            conn.commit()

        return {
            "id": pred_id,
            "timestamp": now_iso,
            "model_id": model_id,
            "summary": summary
        }

    def get_patient_predictions(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            if user_id and user_id != "patient-default":
                rows = conn.execute(
                    """
                    SELECT id, user_id, timestamp, model_id, inputs_json, results_json, summary
                    FROM patient_predictions
                    WHERE user_id = ? OR user_id = 'patient-default'
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (user_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, user_id, timestamp, model_id, inputs_json, results_json, summary
                    FROM patient_predictions
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,)
                ).fetchall()

            history = []
            for r in rows:
                try:
                    inputs = json.loads(r["inputs_json"])
                except Exception:
                    inputs = {}
                try:
                    results = json.loads(r["results_json"])
                except Exception:
                    results = {}

                history.append({
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "timestamp": r["timestamp"],
                    "model_id": r["model_id"],
                    "summary": r["summary"],
                    "inputs": inputs,
                    "results": results
                })
            return history

    def clear_patient_predictions(self, user_id: Optional[str] = None) -> bool:
        with self.get_connection() as conn:
            if user_id and user_id != "patient-default":
                cursor = conn.execute(
                    "DELETE FROM patient_predictions WHERE user_id = ? OR user_id = 'patient-default'",
                    (user_id,)
                )
            else:
                cursor = conn.execute("DELETE FROM patient_predictions")
            conn.commit()
            return cursor.rowcount > 0

    # ══════════════════════════════════════════════════════════════
    # Patient Chatbot Conversation History
    # ══════════════════════════════════════════════════════════════

    def save_chat_message(
        self,
        user_id: Optional[str],
        role: str,
        message: str,
        model: Optional[str] = None,
        glucose_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        msg_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        ctx_str = json.dumps(glucose_context) if glucose_context else None

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO patient_chat_history (id, user_id, timestamp, role, message, model, glucose_context)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg_id,
                    user_id or "patient-default",
                    now_iso,
                    role,
                    message,
                    model,
                    ctx_str
                )
            )
            conn.commit()

        return {
            "id": msg_id,
            "role": role,
            "message": message,
            "timestamp": now_iso,
            "model": model
        }

    def get_patient_chat_history(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            if user_id and user_id != "patient-default":
                rows = conn.execute(
                    """
                    SELECT id, user_id, timestamp, role, message, model, glucose_context
                    FROM patient_chat_history
                    WHERE user_id = ? OR user_id = 'patient-default'
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (user_id, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, user_id, timestamp, role, message, model, glucose_context
                    FROM patient_chat_history
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (limit,)
                ).fetchall()

            history = []
            for r in rows:
                history.append({
                    "id": r["id"],
                    "user_id": r["user_id"],
                    "timestamp": r["timestamp"],
                    "role": r["role"],
                    "message": r["message"],
                    "content": r["message"],  # Frontend alias
                    "model": r["model"]
                })
            return history

    def clear_patient_chat_history(self, user_id: Optional[str] = None) -> bool:
        with self.get_connection() as conn:
            if user_id and user_id != "patient-default":
                cursor = conn.execute(
                    "DELETE FROM patient_chat_history WHERE user_id = ? OR user_id = 'patient-default'",
                    (user_id,)
                )
            else:
                cursor = conn.execute("DELETE FROM patient_chat_history")
            conn.commit()
            return cursor.rowcount > 0

db = Database()
