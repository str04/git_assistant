import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import base64
import streamlit as st
import requests
import extra_streamlit_components as stx
from agent import create_agent_session, chat_with_agent, chat_with_agent_streaming
from multi_agent import run_pipeline
from bug_fixer import run_bug_fixer
from issue_to_pr import run_issue_to_pr
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
.dashboard-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 16px;
    margin: 6px 0;
}
.dashboard-card:hover { border-color: #4ade80; }
.stat-number { font-size: 2em; font-weight: bold; color: #4ade80; }
.stat-label { font-size: 0.85em; color: #94a3b8; }
.pr-open { color: #4ade80; }
.pr-closed { color: #f87171; }
.issue-open { color: #fb923c; }
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
    ("show_dashboard", True),
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


# ── Dashboard Helper ───────────────────────────────────────────────────
def fetch_dashboard_data(token: str, username: str) -> dict:
    """Fetch repos, PRs, and issues for the dashboard."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"repos": [], "open_prs": [], "open_issues": []}

    try:
        # Get repos
        resp = requests.get(f"{GITHUB_API}/user/repos?sort=updated&per_page=6", headers=headers)
        if resp.status_code == 200:
            data["repos"] = resp.json()
    except Exception:
        pass

    try:
        # Get open PRs across all repos
        resp = requests.get(f"{GITHUB_API}/search/issues?q=author:{username}+type:pr+state:open&per_page=5", headers=headers)
        if resp.status_code == 200:
            data["open_prs"] = resp.json().get("items", [])
    except Exception:
        pass

    try:
        # Get open issues assigned to user
        resp = requests.get(f"{GITHUB_API}/search/issues?q=assignee:{username}+type:issue+state:open&per_page=5", headers=headers)
        if resp.status_code == 200:
            data["open_issues"] = resp.json().get("items", [])
    except Exception:
        pass

    return data


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

    # ── Main Area: Two Tabs ────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["🏠 Dashboard", "💬 Chat", "🚀 Build Project", "🐛 Bug Fixer", "🎯 Issue → PR"])

    # ── Tab 1: Dashboard ──────────────────────────────────────────────
    with tab1:
        st.markdown("### 🏠 Your GitHub Dashboard")

        if st.button("🔄 Refresh", key="refresh_dashboard"):
            if "dashboard_data" in st.session_state:
                del st.session_state["dashboard_data"]

        if "dashboard_data" not in st.session_state:
            with st.spinner("Loading your GitHub data..."):
                st.session_state["dashboard_data"] = fetch_dashboard_data(
                    st.session_state.github_token,
                    st.session_state.github_username
                )

        dash = st.session_state["dashboard_data"]
        repos = dash.get("repos", [])
        open_prs = dash.get("open_prs", [])
        open_issues = dash.get("open_issues", [])

        # Stats row
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="dashboard-card"><div class="stat-number">{len(repos)}</div><div class="stat-label">Recent Repos</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="dashboard-card"><div class="stat-number pr-open">{len(open_prs)}</div><div class="stat-label">Open Pull Requests</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="dashboard-card"><div class="stat-number issue-open">{len(open_issues)}</div><div class="stat-label">Open Issues</div></div>', unsafe_allow_html=True)

        st.markdown("---")

        # Repos + PRs side by side
        col_repos, col_activity = st.columns([1, 1])

        with col_repos:
            st.markdown("#### 📁 Recent Repositories")
            if repos:
                for repo in repos:
                    lang = repo.get("language") or "Unknown"
                    stars = repo.get("stargazers_count", 0)
                    is_private = "🔒" if repo.get("private") else "🌐"
                    st.markdown(
                        f'<div class="dashboard-card">' +
                        f'<strong>{is_private} <a href="{repo["html_url"]}" target="_blank" style="color:#4ade80;text-decoration:none;">{repo["name"]}</a></strong><br>' +
                        f'<span style="color:#94a3b8;font-size:0.8em;">{lang} • ⭐ {stars}</span>' +
                        f'<br><span style="color:#64748b;font-size:0.75em;">{repo.get("description","") or ""}</span>' +
                        '</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.caption("No repos found")

        with col_activity:
            st.markdown("#### 🔀 Your Open PRs")
            if open_prs:
                for pr in open_prs:
                    repo_name = pr["repository_url"].split("/")[-1]
                    st.markdown(
                        f'<div class="dashboard-card">' +
                        f'<strong><a href="{pr["html_url"]}" target="_blank" style="color:#4ade80;text-decoration:none;">#{pr["number"]} {pr["title"][:50]}</a></strong><br>' +
                        f'<span style="color:#94a3b8;font-size:0.8em;">{repo_name}</span>' +
                        '</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.caption("No open PRs 🎉")

            st.markdown("#### 🐛 Assigned Issues")
            if open_issues:
                for issue in open_issues:
                    repo_name = issue["repository_url"].split("/")[-1]
                    st.markdown(
                        f'<div class="dashboard-card">' +
                        f'<strong><a href="{issue["html_url"]}" target="_blank" style="color:#fb923c;text-decoration:none;">#{issue["number"]} {issue["title"][:50]}</a></strong><br>' +
                        f'<span style="color:#94a3b8;font-size:0.8em;">{repo_name}</span>' +
                        '</div>',
                        unsafe_allow_html=True
                    )
            else:
                st.caption("No assigned issues 🎉")

    # ── Tab 2: Chat ────────────────────────────────────────────────────
    with tab2:
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
                tool_calls = []
                response_text = ""

                # Show tool activity above the streaming text
                tool_placeholder = st.empty()
                text_placeholder = st.empty()
                active_tools = []

                try:
                    for chunk in chat_with_agent_streaming(st.session_state.chat_session, user_input):

                        if chunk["type"] == "tool":
                            # Show which tool is being called
                            active_tools.append(chunk["tool"])
                            tool_placeholder.info(f"🔧 Running: {', '.join(active_tools)}...")
                            tool_calls.append({"tool": chunk["tool"], "input": chunk["input"]})

                        elif chunk["type"] == "text":
                            # Stream text word by word
                            response_text += chunk["content"]
                            text_placeholder.markdown(response_text + "▌")

                        elif chunk["type"] == "done":
                            # Final render — remove cursor
                            tool_placeholder.empty()
                            text_placeholder.markdown(response_text)
                            tool_calls = chunk["tool_calls"]

                        elif chunk["type"] == "error":
                            response_text = chunk["content"]
                            text_placeholder.markdown(response_text)

                except Exception as e:
                    response_text = f"❌ Error: {str(e)}"
                    text_placeholder.markdown(response_text)

                # Show tool calls summary
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

    # ── Tab 3: Multi-Agent Pipeline ────────────────────────────────────
    with tab3:
        st.markdown("### 🚀 Build a Full Project Automatically")
        st.caption("Describe your project in plain English — 4 AI agents will plan, code, test, and document it, then push everything to GitHub.")

        st.info(
            "🧠 **Planner Agent** → designs file structure  \n"
            "🏗️ **Repo Agent** → creates repo and writes all code  \n"
            "🧪 **Test Agent** → writes unit tests  \n"
            "📄 **Docs Agent** → generates README"
        )

        pipeline_examples = [
            "A FastAPI backend with CRUD endpoints for a todo list app",
            "A Python web scraper that extracts article titles from news websites",
            "A simple Express.js REST API with user authentication",
            "A Python CLI tool that converts CSV files to JSON",
        ]
        selected_example = st.selectbox(
            "Pick an example or write your own below:",
            [""] + pipeline_examples,
            key="pipeline_example"
        )
        project_prompt = st.text_area(
            "Describe your project",
            value=selected_example,
            placeholder="e.g. A Flask REST API with endpoints for user authentication and a SQLite database",
            height=100,
            key="project_prompt"
        )

        if st.button("▶ Run Pipeline", type="primary", use_container_width=True, key="run_pipeline"):
            prompt = project_prompt.strip()
            if not prompt:
                st.error("Please describe your project first.")
            else:
                st.markdown("---")
                st.markdown("#### 🤖 Agents Working...")
                final_url = None
                for update in run_pipeline(
                    GROQ_API_KEY,
                    st.session_state.github_token,
                    st.session_state.github_username,
                    prompt
                ):
                    if update["error"]:
                        st.error(f"**{update['agent']}** — {update['status']}")
                        if update["detail"]:
                            st.caption(update["detail"])
                    elif update["done"]:
                        st.success(f"**{update['agent']}** — {update['status']}")
                        if update["detail"]:
                            st.caption(update["detail"])
                    else:
                        st.info(f"**{update['agent']}** — {update['status']}")
                        if update["detail"]:
                            st.caption(update["detail"])
                    if "repo_url" in update:
                        final_url = update["repo_url"]

                if final_url:
                    st.balloons()
                    st.markdown(f"### ✅ Project ready!")
                    st.markdown(f"[🔗 View on GitHub]({final_url})")

    # ── Tab 4: Bug Fixer ───────────────────────────────────────────────
    with tab4:
        st.markdown("### 🐛 Auto Bug Fixer")
        st.caption("Paste your error message — the agent finds the bug, fixes it, and opens a PR automatically.")

        bf_repo = st.text_input("Repository name", placeholder="my-repo", key="bf_repo")
        bf_branch = st.text_input("Branch", value="main", key="bf_branch")
        bf_error = st.text_area(
            "Paste your error message or traceback",
            placeholder="""Traceback (most recent call last):
  File "app.py", line 42, in get_user
    return db.query(User).filter_by(id=user_id).first()
AttributeError: 'NoneType' object has no attribute 'query'""",
            height=200,
            key="bf_error"
        )

        if st.button("🔧 Fix Bug Automatically", type="primary", use_container_width=True, key="run_bug_fixer"):
            if not bf_repo.strip():
                st.error("Please enter the repository name.")
            elif not bf_error.strip():
                st.error("Please paste your error message.")
            else:
                st.markdown("---")
                st.markdown("#### 🤖 Bug Fixer Working...")
                pr_url = None

                for update in run_bug_fixer(
                    GROQ_API_KEY,
                    st.session_state.github_token,
                    st.session_state.github_username,
                    bf_repo.strip(),
                    bf_error.strip(),
                    bf_branch.strip() or "main"
                ):
                    if update["error"]:
                        st.error(update["status"])
                        if update["detail"]:
                            st.caption(update["detail"])
                    elif update["done"]:
                        st.success(update["status"])
                        if update["detail"]:
                            st.caption(update["detail"])
                    else:
                        st.info(update["status"])
                        if update["detail"]:
                            st.caption(update["detail"])

                    if "pr_url" in update:
                        pr_url = update["pr_url"]

                if pr_url:
                    st.balloons()
                    st.markdown(f"### ✅ Bug Fixed!")
                    st.markdown(f"[🔗 View Pull Request]({pr_url})")

    # ── Tab 5: Issue → PR Pipeline ────────────────────────────────────
    with tab5:
        st.markdown("### 🎯 Issue → Code → PR Pipeline")
        st.caption("Pick a GitHub issue — the agent reads it, writes the code, and opens a PR automatically.")

        st.info(
            "📋 **Reads the issue** → understands what to build  \n"
            "🧠 **Plans the implementation** → decides which files to create/modify  \n"
            "✍️ **Writes the code** → implements the feature  \n"
            "📬 **Opens a PR** → linked to the issue, ready to review"
        )

        col1, col2 = st.columns([2, 1])
        with col1:
            itp_repo = st.text_input("Repository name", placeholder="my-repo", key="itp_repo")
        with col2:
            itp_issue = st.number_input("Issue number", min_value=1, step=1, key="itp_issue")

        itp_branch = st.text_input("Base branch", value="main", key="itp_branch")

        if st.button("🚀 Implement Issue", type="primary", use_container_width=True, key="run_itp"):
            if not itp_repo.strip():
                st.error("Please enter the repository name.")
            else:
                st.markdown("---")
                st.markdown("#### 🤖 Pipeline Running...")
                pr_url = None

                for update in run_issue_to_pr(
                    GROQ_API_KEY,
                    st.session_state.github_token,
                    st.session_state.github_username,
                    itp_repo.strip(),
                    int(itp_issue),
                    itp_branch.strip() or "main"
                ):
                    if update["error"]:
                        st.error(update["status"])
                        if update["detail"]:
                            st.caption(update["detail"])
                    elif update["done"]:
                        st.success(update["status"])
                        if update["detail"]:
                            st.caption(update["detail"])
                    else:
                        st.info(update["status"])
                        if update["detail"]:
                            st.caption(update["detail"])

                    if "pr_url" in update:
                        pr_url = update["pr_url"]

                if pr_url:
                    st.balloons()
                    st.markdown(f"### ✅ Done!")
                    st.markdown(f"[🔗 View Pull Request]({pr_url})")