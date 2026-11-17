import os
import sqlite3
from pathlib import Path
from app.db.database import db

def test_gitignore_protects_env_and_credentials():
    root = Path(__file__).resolve().parent.parent.parent
    gitignore_path = root / ".gitignore"
    assert gitignore_path.exists(), ".gitignore file must exist"
    content = gitignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines()]

    assert any(line == ".env" or line.startswith(".env") for line in lines), ".env must be ignored in .gitignore"

def test_env_example_has_no_secret_values():
    root = Path(__file__).resolve().parent.parent.parent
    example_path = root / ".env.example"
    assert example_path.exists(), ".env.example must exist"
    content = example_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            # Secret keys must have empty values or placeholder names
            if "SECRET" in k or "CLIENT_SECRET" in k:
                assert v == "" or "your_" in v or "replace_" in v, f"Secret value leak in .env.example for {k}"

def test_no_health_data_in_database():
    """Verify that SQLite schema has strictly zero columns for glucose, insulin, or carbs."""
    # Connect directly to SQLite and inspect column names
    db_path = db.db_path
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(users)")
    user_cols = [row[1] for row in cur.fetchall()]
    assert set(user_cols) == {"id", "provider", "provider_sub", "email", "name", "age", "gender", "minor_confirmed", "consent_timestamp", "created_at"}

    cur.execute("PRAGMA table_info(sessions)")
    session_cols = [row[1] for row in cur.fetchall()]
    assert set(session_cols) == {"session_id", "user_id", "csrf_token", "created_at", "expires_at"}

    conn.close()
