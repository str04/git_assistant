import sqlite3
import os
import json
import hashlib
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.db")


def get_user_id(github_token: str) -> str:
    """Hash the GitHub token to create a unique private user ID."""
    return hashlib.sha256(github_token.encode()).hexdigest()[:16]


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT NOT NULL,
            title      TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
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


def create_session(user_id: str, title: str = "New Chat") -> int:
    init_db()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, title, now, now)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_all_sessions(user_id: str) -> list:
    """Get ONLY this user's sessions."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, title, updated_at FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "updated_at": r[2][:16].replace("T", " ")} for r in rows]


def update_session_title(session_id: int, user_id: str, title: str):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE chat_sessions SET title = ? WHERE id = ? AND user_id = ?",
        (title, session_id, user_id)
    )
    conn.commit()
    conn.close()


def delete_session(session_id: int, user_id: str):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, user_id))
    conn.commit()
    conn.close()


def save_message(session_id: int, role: str, content: str, tool_calls: list = None):
    init_db()
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO chat_messages (session_id, role, content, tool_calls, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, json.dumps(tool_calls) if tool_calls else None, now)
    )
    conn.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()
    conn.close()


def load_messages(session_id: int) -> list:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT role, content, tool_calls FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [
        {"role": r[0], "content": r[1], "tool_calls": json.loads(r[2]) if r[2] else None}
        for r in rows
    ]


def load_messages_for_agent(session_id: int, limit: int = 4) -> list:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT role, content FROM chat_messages
           WHERE session_id = ? AND role IN ('user', 'assistant')
           ORDER BY created_at DESC LIMIT ?""",
        (session_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def cleanup_old_sessions(user_id: str, days: int = 30):
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM chat_sessions WHERE user_id = ? AND updated_at < ?",
        (user_id, cutoff)
    )
    for r in cursor.fetchall():
        conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (r[0],))
    conn.execute(
        "DELETE FROM chat_sessions WHERE user_id = ? AND updated_at < ?",
        (user_id, cutoff)
    )
    conn.commit()
    conn.close()