import os
import json
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent.db")


def _conn():
    # check_same_thread=False helps Streamlit
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = _conn()
    cur = conn.cursor()

    # Settings are user-scoped via (user_id, key)
    # We'll also store global app settings under user_id='__app__'
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        user_id TEXT NOT NULL,
        key     TEXT NOT NULL,
        value   TEXT NOT NULL,
        PRIMARY KEY (user_id, key)
    )
    """)

    # Sessions are user-scoped
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT NOT NULL,
        title      TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Messages are user-scoped
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT NOT NULL,
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


# ──────────────────────────────────────────────────────────────────────
# "Stay logged in" helpers (global app setting)
# ──────────────────────────────────────────────────────────────────────
def set_last_user(user_id: str):
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO settings (user_id, key, value)
        VALUES ('__app__', 'last_user', ?)
        ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value
    """, (user_id,))
    conn.commit()
    conn.close()


def get_last_user() -> str:
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE user_id='__app__' AND key='last_user'")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ""


# ──────────────────────────────────────────────────────────────────────
# Token (per user)
# ──────────────────────────────────────────────────────────────────────
def save_token(user_id: str, token: str):
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO settings (user_id, key, value)
        VALUES (?, 'github_token', ?)
        ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value
    """, (user_id, token))
    conn.commit()
    conn.close()


def load_token(user_id: str) -> str:
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE user_id=? AND key='github_token'", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ""


def clear_token(user_id: str):
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM settings WHERE user_id=? AND key='github_token'", (user_id,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────────────
# Sessions (per user)
# ──────────────────────────────────────────────────────────────────────
def create_session(user_id: str, title: str = "New Chat") -> int:
    init_db()
    now = datetime.now().isoformat()
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (user_id, title, now, now)
    )
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid


def get_all_sessions(user_id: str) -> list:
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, updated_at
        FROM chat_sessions
        WHERE user_id=?
        ORDER BY updated_at DESC
    """, (user_id,))
    rows = cur.fetchall()
    conn.close()

    out = []
    for sid, title, updated_at in rows:
        # UI-friendly time
        ts = (updated_at or "")[:16].replace("T", " ")
        out.append({"id": sid, "title": title, "updated_at": ts})
    return out


def update_session_title(user_id: str, session_id: int, title: str):
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE chat_sessions
        SET title=?
        WHERE user_id=? AND id=?
    """, (title, user_id, session_id))
    conn.commit()
    conn.close()


def delete_session(user_id: str, session_id: int):
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_messages WHERE user_id=? AND session_id=?", (user_id, session_id))
    cur.execute("DELETE FROM chat_sessions WHERE user_id=? AND id=?", (user_id, session_id))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────────────────────────────
# Messages (per user)
# ──────────────────────────────────────────────────────────────────────
def save_message(user_id: str, session_id: int, role: str, content: str, tool_calls: list = None):
    init_db()
    now = datetime.now().isoformat()
    conn = _conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO chat_messages (user_id, session_id, role, content, tool_calls, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        session_id,
        role,
        content,
        json.dumps(tool_calls) if tool_calls else None,
        now
    ))

    cur.execute("""
        UPDATE chat_sessions
        SET updated_at=?
        WHERE user_id=? AND id=?
    """, (now, user_id, session_id))

    conn.commit()
    conn.close()


def load_messages(user_id: str, session_id: int) -> list:
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT role, content, tool_calls
        FROM chat_messages
        WHERE user_id=? AND session_id=?
        ORDER BY created_at ASC
    """, (user_id, session_id))
    rows = cur.fetchall()
    conn.close()

    out = []
    for role, content, tool_calls in rows:
        out.append({
            "role": role,
            "content": content,
            "tool_calls": json.loads(tool_calls) if tool_calls else None
        })
    return out


def load_messages_for_agent(user_id: str, session_id: int, limit: int = 6) -> list:
    """
    Short context window for LLM (last N user/assistant messages).
    """
    init_db()
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT role, content
        FROM chat_messages
        WHERE user_id=? AND session_id=? AND role IN ('user','assistant')
        ORDER BY created_at DESC
        LIMIT ?
    """, (user_id, session_id, limit))
    rows = cur.fetchall()
    conn.close()

    # reverse back to chronological
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


# ──────────────────────────────────────────────────────────────────────
# Cleanup (optionally per-user, but default global)
# ──────────────────────────────────────────────────────────────────────
def cleanup_old_sessions(days: int = 30, user_id: str | None = None):
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    conn = _conn()
    cur = conn.cursor()

    if user_id:
        cur.execute("SELECT id FROM chat_sessions WHERE user_id=? AND updated_at < ?", (user_id, cutoff))
        old_ids = [r[0] for r in cur.fetchall()]
        for sid in old_ids:
            cur.execute("DELETE FROM chat_messages WHERE user_id=? AND session_id=?", (user_id, sid))
            cur.execute("DELETE FROM chat_sessions WHERE user_id=? AND id=?", (user_id, sid))
    else:
        # global cleanup
        cur.execute("SELECT id, user_id FROM chat_sessions WHERE updated_at < ?", (cutoff,))
        rows = cur.fetchall()
        for sid, uid in rows:
            cur.execute("DELETE FROM chat_messages WHERE user_id=? AND session_id=?", (uid, sid))
            cur.execute("DELETE FROM chat_sessions WHERE user_id=? AND id=?", (uid, sid))

    conn.commit()
    conn.close()