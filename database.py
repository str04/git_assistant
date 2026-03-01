import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.db")

def init_db():
    """Create the database and tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Settings table (for token etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Chat sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Chat messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            tool_calls TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
        )
    """)

    conn.commit()
    conn.close()


# ── Token ──────────────────────────────────────────────────────────────
def save_token(token: str):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO settings (key, value)
        VALUES ('github_token', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (token,))
    conn.commit()
    conn.close()

def load_token() -> str:
    init_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'github_token'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""

def clear_token():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM settings WHERE key = 'github_token'")
    conn.commit()
    conn.close()


# ── Chat Sessions ──────────────────────────────────────────────────────
def create_session(title: str = "New Chat") -> int:
    """Create a new chat session and return its ID."""
    init_db()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
        (title, now, now)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def get_all_sessions() -> list:
    """Get all chat sessions ordered by most recent."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, updated_at FROM chat_sessions ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "updated_at": r[2][:16].replace("T", " ")} for r in rows]

def update_session_title(session_id: int, title: str):
    """Update the title of a session."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE chat_sessions SET title = ? WHERE id = ?", (title, session_id))
    conn.commit()
    conn.close()

def delete_session(session_id: int):
    """Delete a session and all its messages."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


# ── Chat Messages ──────────────────────────────────────────────────────
def save_message(session_id: int, role: str, content: str, tool_calls: list = None):
    """Save a message to a session."""
    init_db()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_messages (session_id, role, content, tool_calls, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, json.dumps(tool_calls) if tool_calls else None, now)
    )
    cursor.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()
    conn.close()

def load_messages(session_id: int) -> list:
    """Load all messages for a session (for UI display)."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, tool_calls FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "role": r[0],
            "content": r[1],
            "tool_calls": json.loads(r[2]) if r[2] else None
        }
        for r in rows
    ]

def load_messages_for_agent(session_id: int, limit: int = 4) -> list:
    """Load only the last N messages for agent context."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT role, content FROM chat_messages 
           WHERE session_id = ? AND role IN ('user', 'assistant') 
           ORDER BY created_at DESC LIMIT ?""",
        (session_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    # Reverse so oldest is first (correct order for the agent)
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def cleanup_old_sessions(days: int = 30):
    """Delete sessions older than X days to keep DB light."""
    init_db()
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM chat_sessions WHERE updated_at < ?", (cutoff,))
    old_ids = [r[0] for r in cursor.fetchall()]
    for sid in old_ids:
        cursor.execute("DELETE FROM chat_messages WHERE session_id = ?", (sid,))
        cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (sid,))
    conn.commit()
    conn.close()