import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import requests

from agent import create_agent_session, chat_with_agent
from config import GROQ_API_KEY, get_github_headers, GITHUB_API
from tools.files import create_or_update_file

from database import (
    save_token, load_token, clear_token,
    create_session, get_all_sessions, delete_session, update_session_title,
    save_message, load_messages, load_messages_for_agent,
    cleanup_old_sessions,
    set_last_user, get_last_user,
)

cleanup_old_sessions(days=30)

# ── Page Config ────────────────────────────────────────────────────────
st.set_page_config(page_title="GitHub Agent", page_icon="🐙", layout="wide")

st.markdown("""
<style>
.tool-call {
    background: #1a1a2e;
    border-left: 3px solid #4ade80;
    padding: 6px 12px;
    border-radius: 6px;
    font-family: monospace;
    font-size: 0.82em;
    color: #e2e8f0;
    margin: 6px 0;
}
.tool-name { color: #4ade80; font-weight: bold; }
.connected-badge {
    background: #16a34a;
    color: white;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.8em;
    font-weight: 700;
    display: inline-block;
}
.session-time {
    font-size: 0.75em;
    color: #94a3b8;
    margin-top: 2px;
}
.small-note {
    font-size: 0.8em;
    color: #94a3b8;
}
</style>
""", unsafe_allow_html=True)

# ── Session State init ─────────────────────────────────────────────────
defaults = {
    "connected": False,
    "github_username": "",
    "user_id": "",
    "current_session_id": None,
    "chat_history": [],
    "chat_session": None,
    "selected_user_for_login": "",
    "pending_prompt": None,     # from "Try these" buttons
    "auto_login_tried": False,  # prevents rerun loops
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ────────────────────────────────────────────────────────────
def verify_github_token(token: str):
    """Return (username, error_message)."""
    try:
        resp = requests.get(
            f"{GITHUB_API}/user",
            headers=get_github_headers(token),
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json().get("login"), None
        msg = resp.json().get("message", "Invalid token")
        return None, msg
    except Exception as e:
        return None, str(e)

def is_github_related(text: str) -> bool:
    t = (text or "").lower()
    keywords = [
        "github", "repo", "repository", "branch", "commit", "pr", "pull request",
        "issue", "merge", "fork", "readme", "tag", "release", "workflow", "actions",
        "code", "file", "diff", "ci", "cd"
    ]
    return any(k in t for k in keywords)

def ensure_connected_session():
    user_id = st.session_state.user_id
    if not user_id:
        return

    token = load_token(user_id)
    if not token:
        return

    history_for_agent = []
    if st.session_state.current_session_id:
        history_for_agent = load_messages_for_agent(user_id, st.session_state.current_session_id)

    st.session_state.chat_session = create_agent_session(
        GROQ_API_KEY,
        token,
        st.session_state.github_username,
        history=history_for_agent
    )

def load_session(session_id: int):
    user_id = st.session_state.user_id
    token = load_token(user_id)
    history_for_agent = load_messages_for_agent(user_id, session_id)

    st.session_state.chat_session = create_agent_session(
        GROQ_API_KEY,
        token,
        st.session_state.github_username,
        history=history_for_agent
    )
    st.session_state.current_session_id = session_id
    st.session_state.chat_history = load_messages(user_id, session_id)

def start_new_session():
    user_id = st.session_state.user_id
    token = load_token(user_id)

    session_id = create_session(user_id, "New Chat")
    st.session_state.chat_session = create_agent_session(
        GROQ_API_KEY,
        token,
        st.session_state.github_username
    )
    st.session_state.current_session_id = session_id
    st.session_state.chat_history = []

def finish_login(username: str):
    """
    Common login handler.
    - sets user/session state
    - sets last user (auto-login next time)
    - loads latest session or starts new
    """
    st.session_state.github_username = username
    st.session_state.user_id = username
    st.session_state.connected = True

    set_last_user(username)

    sessions = get_all_sessions(username)
    if sessions:
        load_session(sessions[0]["id"])
    else:
        start_new_session()

def logout(also_forget_token: bool = False):
    if also_forget_token and st.session_state.user_id:
        clear_token(st.session_state.user_id)

    st.session_state.connected = False
    st.session_state.github_username = ""
    st.session_state.user_id = ""
    st.session_state.current_session_id = None
    st.session_state.chat_history = []
    st.session_state.chat_session = None
    st.session_state.selected_user_for_login = ""
    st.session_state.pending_prompt = None
    st.session_state.auto_login_tried = False
    st.rerun()

# ── Auto-login (keep user logged in) ───────────────────────────────────
if not st.session_state.connected and not st.session_state.auto_login_tried:
    st.session_state.auto_login_tried = True

    last_user = get_last_user()
    if last_user:
        token = load_token(last_user)
        if token:
            username, err = verify_github_token(token)
            if username:
                finish_login(username)
                st.rerun()
            # if token invalid -> do nothing; user can login manually

# ── Sidebar ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🐙 GitHub Agent")

    if not st.session_state.connected:
        st.markdown("### 🔑 Sign in (separate users)")

        # If last user exists, show "Continue as ..."
        last_user = get_last_user()
        if last_user:
            col1, col2 = st.columns([0.65, 0.35])
            with col1:
                st.caption(f"Last signed-in: **{last_user}**")
            with col2:
                if st.button("Continue", use_container_width=True):
                    token = load_token(last_user)
                    username, err = verify_github_token(token) if token else (None, "No token")
                    if username:
                        finish_login(username)
                        st.rerun()
                    else:
                        st.error(f"Can't auto-login: {err}")

        remember_me = st.checkbox("Keep me signed in on this device", value=True)

        typed_user = st.text_input(
            "GitHub username",
            value=st.session_state.selected_user_for_login,
            placeholder="e.g. dev-user123",
        ).strip()
        st.session_state.selected_user_for_login = typed_user

        saved_for_user = load_token(typed_user) if typed_user else ""

        if typed_user and saved_for_user:
            st.success("Saved token found for this username.")
            if st.button("✅ Connect using saved token", use_container_width=True):
                username, error = verify_github_token(saved_for_user)
                if username:
                    finish_login(username)
                    if remember_me:
                        set_last_user(username)
                    st.rerun()
                else:
                    st.error(f"Token invalid/expired: {error}")
                    st.info("Paste a new token below to replace it.")

        st.markdown("**Or paste token to connect / replace token**")
        token_input = st.text_input("GitHub Personal Access Token", type="password", placeholder="ghp_...")

        if st.button("🔌 Connect", use_container_width=True):
            if not token_input.strip():
                st.error("Please enter a token.")
            else:
                username, error = verify_github_token(token_input.strip())
                if username:
                    save_token(username, token_input.strip())
                    finish_login(username)
                    if remember_me:
                        set_last_user(username)
                    st.rerun()
                else:
                    st.error(f"Invalid token: {error}")

        st.divider()
        st.caption("Each GitHub username has its own chat history & saved token (no mixing).")

    else:
        st.markdown(f'<span class="connected-badge">✓ {st.session_state.github_username}</span>', unsafe_allow_html=True)

        colA, colB = st.columns(2)
        with colA:
            if st.button("➕ New Chat", use_container_width=True):
                start_new_session()
                st.rerun()
        with colB:
            if st.button("🚪 Logout", use_container_width=True):
                logout(also_forget_token=False)

        if st.button("🧹 Logout + forget token", use_container_width=True):
            logout(also_forget_token=True)

        st.divider()

        # ── Try these ───────────────────────────────────────────────
        st.markdown("### 💡 Try these")
        examples = [
            ("List my repos", "list my repos"),
            ("Create a repo", "create a repo called demo-repo"),
            ("List branches", "list branches in repo demo-repo"),
            ("Create branch", "create a branch called feature/login in demo-repo"),
            ("Generate README", "generate a README for repo demo-repo"),
            ("Open an issue", "open an issue titled 'Fix bug' in demo-repo"),
            ("Search trending AI repos", "search trending python ai repos"),
        ]
        for label, text in examples:
            if st.button(label, use_container_width=True):
                st.session_state.pending_prompt = text
                st.rerun()

        st.divider()

        # ── Sessions (user-scoped) ─────────────────────────────────
        st.markdown("### 🕘 Chat History")
        sessions = get_all_sessions(st.session_state.user_id)

        if not sessions:
            st.caption("No chats yet.")
        else:
            for s in sessions:
                is_active = (s["id"] == st.session_state.current_session_id)
                cols = st.columns([0.80, 0.20])
                with cols[0]:
                    label = f"**{s['title']}**" if is_active else s["title"]
                    if st.button(label, key=f"sess_{s['id']}", use_container_width=True):
                        load_session(s["id"])
                        st.rerun()
                    st.markdown(f"<div class='session-time'>{s['updated_at']}</div>", unsafe_allow_html=True)
                with cols[1]:
                    if st.button("🗑️", key=f"del_{s['id']}"):
                        delete_session(st.session_state.user_id, s["id"])
                        if s["id"] == st.session_state.current_session_id:
                            start_new_session()
                        st.rerun()

        st.divider()

        # ── Upload files to GitHub ─────────────────────────────────
        with st.expander("📁 Upload files to GitHub"):
            upload_repo = st.text_input("Repo name", placeholder="demo-repo")
            upload_branch = st.text_input("Branch (optional)", placeholder="main")
            upload_folder = st.text_input("Folder path (optional)", placeholder="src/utils")
            files = st.file_uploader("Select files", accept_multiple_files=True)

            if st.button("Upload", use_container_width=True):
                if not files:
                    st.error("Select at least one file.")
                elif not upload_repo.strip():
                    st.error("Enter repo name.")
                else:
                    token = load_token(st.session_state.user_id)
                    repo = upload_repo.strip()
                    branch = upload_branch.strip() or "main"
                    folder = upload_folder.strip().rstrip("/")

                    uploaded_names, failed_names = [], []
                    progress = st.progress(0)
                    for i, f in enumerate(files, start=1):
                        try:
                            content = f.read().decode("utf-8", errors="ignore")
                            path = f"{folder}/{f.name}" if folder else f.name
                            res = create_or_update_file(
                                token,
                                st.session_state.github_username,
                                repo,
                                path,
                                content,
                                f"Upload {path}",
                                branch
                            )
                            if isinstance(res, dict) and res.get("error"):
                                failed_names.append(f.name)
                            else:
                                uploaded_names.append(f.name)
                        except Exception:
                            failed_names.append(f.name)
                        progress.progress(i / len(files))

                    if uploaded_names:
                        st.success(f"Uploaded: {', '.join(uploaded_names)}")
                    if failed_names:
                        st.error(f"Failed: {', '.join(failed_names)}")

# ── Main UI ────────────────────────────────────────────────────────────
st.title("🐙 GitHub Agent")
st.caption("Manage your GitHub workflow through natural conversation — powered by Groq AI (free)")
st.divider()

if not st.session_state.connected:
    st.info("Connect your GitHub account from the left sidebar to start.")
    st.stop()

if st.session_state.chat_session is None:
    ensure_connected_session()

# Render chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tool_calls"):
            with st.expander(f"🛠 {len(msg['tool_calls'])} action(s) performed"):
                for tc in msg["tool_calls"]:
                    st.markdown(
                        f"<div class='tool-call'><span class='tool-name'>{tc['tool']}</span> → {tc.get('input', {})}</div>",
                        unsafe_allow_html=True
                    )

# Chat input + "Try these"
prompt = st.chat_input("Tell me what to do on GitHub...")
if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt
    st.session_state.pending_prompt = None

if prompt:
    user_id = st.session_state.user_id
    session_id = st.session_state.current_session_id

    save_message(user_id, session_id, "user", prompt)
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    # Hard block non-GitHub topics
    if not is_github_related(prompt):
        answer = (
            "I can only help with GitHub-related tasks. "
            "Try: list repos, create repo, branches, files, PRs, issues, README/tests."
        )
        tool_calls = []

        with st.chat_message("assistant"):
            st.markdown(answer)

        save_message(user_id, session_id, "assistant", answer, tool_calls=tool_calls)
        st.session_state.chat_history.append({"role": "assistant", "content": answer, "tool_calls": tool_calls})
        st.rerun()

    # Run agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer, tool_calls = chat_with_agent(st.session_state.chat_session, prompt)
            st.markdown(answer)

            if tool_calls:
                with st.expander(f"🛠 {len(tool_calls)} action(s) performed"):
                    for tc in tool_calls:
                        st.markdown(
                            f"<div class='tool-call'><span class='tool-name'>{tc['tool']}</span> → {tc.get('input', {})}</div>",
                            unsafe_allow_html=True
                        )

    save_message(user_id, session_id, "assistant", answer, tool_calls=tool_calls)
    st.session_state.chat_history.append({"role": "assistant", "content": answer, "tool_calls": tool_calls})

    if session_id and prompt and len(st.session_state.chat_history) <= 2:
        title = prompt.strip()[:40]
        update_session_title(user_id, session_id, title)

    st.rerun()