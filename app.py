import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import base64
import streamlit as st
import requests
import extra_streamlit_components as stx
from agent import create_agent_session, chat_with_agent
from config import GROQ_API_KEY, get_github_headers, GITHUB_API
from tools.files import create_or_update_file
from database import (
    get_user_id,
    create_session, get_all_sessions, delete_session, update_session_title,
    save_message, load_messages, load_messages_for_agent, cleanup_old_sessions
)

# ── Page Config ────────────────────────────────────────────────────────
st.set_page_config(page_title="GitHub Agent", page_icon="🐙", layout="wide")

st.markdown("""
<style>
.tool-call {
    background: #1a1a2e;
    border-left: 3px solid #4ade80;
    padding: 6px 12px;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.82em;
    color: #e2e8f0;
    margin: 3px 0;
}
.tool-name { color: #4ade80; font-weight: bold; }
.connected-badge {
    background: #16a34a;
    color: white;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.8em;
    font-weight: bold;
}
.session-time { font-size: 0.75em; color: #888; }
</style>
""", unsafe_allow_html=True)


# ── Cookie Manager ─────────────────────────────────────────────────────
cookie_manager = stx.CookieManager()


# ── Session State Init ─────────────────────────────────────────────────
for key, default in [
    ("chat_session", None),
    ("github_username", ""),
    ("github_token", ""),
    ("user_id", ""),
    ("connected", False),
    ("current_session_id", None),
    ("chat_history", []),
    ("auto_connect_tried", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def verify_github_token(token: str):
    resp = requests.get(f"{GITHUB_API}/user", headers=get_github_headers(token))
    if resp.status_code == 200:
        return resp.json()["login"], None
    return None, resp.json().get("message", "Invalid token")


def load_session(session_id: int):
    history_for_agent = load_messages_for_agent(session_id)
    session = create_agent_session(
        GROQ_API_KEY,
        st.session_state.github_token,
        st.session_state.github_username,
        history=history_for_agent
    )
    st.session_state.chat_session = session
    st.session_state.current_session_id = session_id
    st.session_state.chat_history = load_messages(session_id)


def start_new_session():
    session_id = create_session(st.session_state.user_id, "New Chat")
    session = create_agent_session(
        GROQ_API_KEY,
        st.session_state.github_token,
        st.session_state.github_username
    )
    st.session_state.chat_session = session
    st.session_state.current_session_id = session_id
    st.session_state.chat_history = []


def do_connect(token: str):
    """Verify token and set up session. Returns (True, None) or (False, error)."""
    username, error = verify_github_token(token)
    if not username:
        return False, error
    user_id = get_user_id(token)
    st.session_state.github_token = token
    st.session_state.user_id = user_id
    st.session_state.github_username = username
    st.session_state.connected = True
    cleanup_old_sessions(user_id, days=30)
    sessions = get_all_sessions(user_id)
    if sessions:
        load_session(sessions[0]["id"])
    else:
        start_new_session()
    return True, None


# ── Auto-connect from cookie ───────────────────────────────────────────
if not st.session_state.connected and not st.session_state.auto_connect_tried:
    st.session_state.auto_connect_tried = True
    try:
        saved_token = cookie_manager.get("gh_token")
        if saved_token:
            success, _ = do_connect(saved_token)
            if not success:
                cookie_manager.delete("gh_token")
            else:
                st.rerun()
    except Exception:
        pass

# ── Header ─────────────────────────────────────────────────────────────
st.markdown("# 🐙 GitHub Agent")
st.caption("Manage your GitHub workflow through natural conversation — powered by Groq AI (free)")
st.divider()

# ── Login Page ─────────────────────────────────────────────────────────
if not st.session_state.connected:
    st.markdown("### 🔑 Connect Your GitHub Account")
    st.info("Enter your GitHub token once — you won't need to enter it again.")
    st.markdown("**GitHub Personal Access Token** ([create one here](https://github.com/settings/tokens))")
    github_token = st.text_input("GitHub Token", type="password", placeholder="ghp_...", label_visibility="collapsed")
    st.caption("Needs scopes: `repo`, `delete_repo`, `read:user`")

    if st.button("🚀 Connect & Start", type="primary", use_container_width=True):
        if not GROQ_API_KEY:
            st.error("⚠️ GROQ_API_KEY not configured.")
        elif not github_token:
            st.error("Please enter your GitHub token.")
        else:
            with st.spinner("Verifying..."):
                success, error = do_connect(github_token)
                if success:
                    # Save in browser cookie for 30 days
                    cookie_manager.set("gh_token", github_token, max_age=30*24*60*60)
                    st.success(f"✅ Connected as **{st.session_state.github_username}**!")
                    st.rerun()
                else:
                    st.error(f"❌ Invalid token: {error}")

else:
    # ── Sidebar ────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f'<span class="connected-badge">✓ {st.session_state.github_username}</span>', unsafe_allow_html=True)
        st.markdown("---")

        if st.button("✏️ New Chat", use_container_width=True, type="primary"):
            start_new_session()
            st.rerun()

        # ── File Upload ────────────────────────────────────────────────
        with st.expander("📁 Upload files to GitHub"):
            uploaded_files = st.file_uploader(
                "Pick files", type=None, accept_multiple_files=True,
                key="file_uploader", label_visibility="collapsed"
            )
            upload_repo = st.text_input("Repo", placeholder="my-repo", key="upload_repo")
            upload_folder = st.text_input("Folder in repo (optional)", placeholder="src/  or  leave empty for root", key="upload_folder")
            upload_branch = st.text_input("Branch", value="main", key="upload_branch")
            upload_message = st.text_input("Commit message", placeholder="Add files", key="upload_message")

            if st.button("⬆️ Upload", use_container_width=True, key="upload_btn"):
                if not uploaded_files:
                    st.error("Select at least one file.")
                elif not upload_repo:
                    st.error("Enter repo name.")
                else:
                    repo = upload_repo.strip()
                    branch = upload_branch.strip() or "main"
                    folder = upload_folder.strip().rstrip("/")
                    uploaded_names = []
                    failed_names = []
                    progress = st.progress(0, text="Uploading...")

                    for i, f in enumerate(uploaded_files):
                        try:
                            file_bytes = f.read()
                            try:
                                file_content = file_bytes.decode("utf-8")
                            except UnicodeDecodeError:
                                file_content = base64.b64encode(file_bytes).decode("utf-8")

                            final_path = f"{folder}/{f.name}" if folder else f.name
                            commit_msg = upload_message.strip() or f"Add {f.name} via GitHub Agent"

                            result = create_or_update_file(
                                token=st.session_state.github_token,
                                owner=st.session_state.github_username,
                                repo=repo, path=final_path,
                                content=file_content, message=commit_msg, branch=branch
                            )

                            if result.get("success"):
                                uploaded_names.append(final_path)
                            else:
                                failed_names.append(f"{f.name}: {result.get('error', 'Unknown error')}")
                        except Exception as e:
                            failed_names.append(f"{f.name}: {str(e)}")

                        progress.progress((i + 1) / len(uploaded_files), text=f"Uploading {f.name}...")

                    progress.empty()

                    if uploaded_names:
                        st.success(f"✅ Uploaded {len(uploaded_names)} file(s) to `{repo}`!")
                        for name in uploaded_names:
                            st.caption(f"• {name}")

                        files_list = ", ".join([f"`{n}`" for n in uploaded_names])
                        notice = f"I just uploaded {len(uploaded_names)} file(s) to repo `{repo}` on branch `{branch}`: {files_list}"
                        agent_ack = f"Got it! {len(uploaded_names)} file(s) are now in `{repo}` on branch `{branch}`. You can ask me to edit, review, or do anything with them."

                        st.session_state.chat_session["messages"].append({"role": "user", "content": notice})
                        st.session_state.chat_session["messages"].append({"role": "assistant", "content": agent_ack})
                        save_message(st.session_state.current_session_id, "user", notice)
                        save_message(st.session_state.current_session_id, "assistant", agent_ack)
                        st.session_state.chat_history.append({"role": "user", "content": notice})
                        st.session_state.chat_history.append({"role": "assistant", "content": agent_ack})
                        st.rerun()

                    if failed_names:
                        for err in failed_names:
                            st.error(f"❌ {err}")

        st.markdown("---")

        # ── Chat History ───────────────────────────────────────────────
        st.markdown("### 🕓 Chat History")
        all_sessions = get_all_sessions(st.session_state.user_id)

        if not all_sessions:
            st.caption("No past chats yet.")
        else:
            for s in all_sessions:
                is_active = s["id"] == st.session_state.current_session_id
                col1, col2 = st.columns([4, 1])
                with col1:
                    label = f"{'▶ ' if is_active else ''}{s['title']}"
                    if st.button(label, key=f"sess_{s['id']}", use_container_width=True):
                        load_session(s["id"])
                        st.rerun()
                    st.markdown(f'<div class="session-time">{s["updated_at"]}</div>', unsafe_allow_html=True)
                with col2:
                    if st.button("🗑", key=f"del_{s['id']}"):
                        delete_session(s["id"], st.session_state.user_id)
                        if s["id"] == st.session_state.current_session_id:
                            start_new_session()
                        st.rerun()

        st.markdown("---")
        st.markdown("### 💡 Try these")
        examples = [
            "List my repos",
            "Create a repo called test-project",
            "Create a branch called feature/login in test-project",
            "Add a README to test-project",
            "Open an issue titled 'Fix bug' in test-project",
            "Search trending Python AI repos",
        ]
        for ex in examples:
            if st.button(ex, use_container_width=True, key=f"ex_{ex}"):
                st.session_state.prefill = ex

        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            try:
                cookie_manager.delete("gh_token")
            except Exception:
                pass
            for k in ["chat_session", "chat_history", "github_username", "github_token",
                      "user_id", "connected", "current_session_id", "auto_connect_tried"]:
                st.session_state[k] = None if k in ["chat_session", "current_session_id"] else \
                    ([] if k == "chat_history" else ("" if k in ["github_username", "github_token", "user_id"] else False))
            st.rerun()

    # ── Chat Area ──────────────────────────────────────────────────────
    for entry in st.session_state.chat_history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])
            if entry.get("tool_calls"):
                with st.expander(f"🔧 {len(entry['tool_calls'])} action(s) performed", expanded=False):
                    for tc in entry["tool_calls"]:
                        st.markdown(
                            f'<div class="tool-call"><span class="tool-name">{tc["tool"]}</span>({tc["input"]})</div>',
                            unsafe_allow_html=True
                        )

    # ── Chat Input ─────────────────────────────────────────────────────
    prefill = st.session_state.pop("prefill", None)
    user_input = st.chat_input("Tell me what to do on GitHub...")
    if prefill and not user_input:
        user_input = prefill

    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)

        save_message(st.session_state.current_session_id, "user", user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        if len(st.session_state.chat_history) == 1:
            title = user_input[:40] + ("..." if len(user_input) > 40 else "")
            update_session_title(st.session_state.current_session_id, st.session_state.user_id, title)

        with st.chat_message("assistant"):
            with st.spinner("Working on it..."):
                try:
                    response_text, tool_calls = chat_with_agent(st.session_state.chat_session, user_input)
                except Exception as e:
                    response_text = f"❌ Error: {str(e)}"
                    tool_calls = []

            st.markdown(response_text)
            if tool_calls:
                with st.expander(f"🔧 {len(tool_calls)} action(s) performed", expanded=False):
                    for tc in tool_calls:
                        st.markdown(
                            f'<div class="tool-call"><span class="tool-name">{tc["tool"]}</span>({tc["input"]})</div>',
                            unsafe_allow_html=True
                        )

        save_message(st.session_state.current_session_id, "assistant", response_text, tool_calls or None)
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response_text,
            "tool_calls": tool_calls
        })