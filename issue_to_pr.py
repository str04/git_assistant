"""
Issue → Code → PR Pipeline
============================
Takes a GitHub issue → understands what needs to be done
→ reads existing code for context → writes the code changes
→ pushes to a new branch → opens a PR linked to the issue

Usage:
    from issue_to_pr import run_issue_to_pr
    for update in run_issue_to_pr(groq_api_key, github_token, github_username, repo, issue_number):
        print(update)
"""

import json
import re
import requests
import base64
from groq import Groq
from config import MODEL, GITHUB_API, get_github_headers
from tools.files import create_or_update_file
from tools.branches import create_branch
from tools.pulls import create_pull_request


def llm(client: Groq, system: str, user: str, max_tokens: int = 3000) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        max_tokens=max_tokens,
        temperature=0.2
    )
    return resp.choices[0].message.content.strip()


def parse_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    return json.loads(text)


def get_issue(token: str, owner: str, repo: str, issue_number: int) -> dict:
    """Fetch issue details from GitHub."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}"
    resp = requests.get(url, headers=get_github_headers(token))
    if resp.status_code == 200:
        data = resp.json()
        return {
            "number": data["number"],
            "title": data["title"],
            "body": data.get("body", ""),
            "labels": [l["name"] for l in data.get("labels", [])],
            "url": data["html_url"]
        }
    return {}


def get_repo_files(token: str, owner: str, repo: str, path: str = "") -> list:
    """Get list of all code files in repo."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    resp = requests.get(url, headers=get_github_headers(token))
    if resp.status_code != 200:
        return []
    files = []
    for item in resp.json():
        if item["type"] == "file":
            files.append(item["path"])
        elif item["type"] == "dir" and path == "":
            files.extend(get_repo_files(token, owner, repo, item["path"]))
    return files


def get_file_content(token: str, owner: str, repo: str, path: str) -> str:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    resp = requests.get(url, headers=get_github_headers(token))
    if resp.status_code == 200:
        data = resp.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    return ""


def plan_implementation(client: Groq, issue: dict, file_list: list) -> dict:
    """
    Given the issue, plan what files need to be created/modified.
    Returns:
    {
      "branch_name": "feature/issue-42-add-login",
      "summary": "What needs to be done",
      "files_to_read": ["existing files to read for context"],
      "files_to_change": [
        {"path": "src/auth.py", "action": "create|modify", "description": "what to do"}
      ]
    }
    """
    files_str = "\n".join(file_list) if file_list else "No existing files"

    system = """You are a senior software engineer. Given a GitHub issue and the repo's file list,
plan exactly what code changes need to be made to resolve the issue.

Return ONLY a JSON object:
{
  "branch_name": "feature/issue-{number}-short-description",
  "summary": "One paragraph explaining what you will implement",
  "files_to_read": ["list of existing files to read for context, max 3"],
  "files_to_change": [
    {
      "path": "path/to/file.py",
      "action": "create or modify",
      "description": "exactly what to add/change in this file"
    }
  ]
}

Rules:
- branch_name must be lowercase with hyphens
- files_to_change should be 1-4 files max
- Only include files_to_read if they exist in the repo file list
- Return ONLY JSON, no markdown"""

    user = f"""GitHub Issue #{issue['number']}: {issue['title']}

Description:
{issue.get('body', 'No description provided')}

Labels: {', '.join(issue.get('labels', [])) or 'none'}

Existing files in repo:
{files_str[:2000]}"""

    raw = llm(client, system, user, max_tokens=1500)
    return parse_json(raw)


def write_code(client: Groq, issue: dict, file_info: dict, context_files: dict) -> str:
    """Write the actual code for a file based on the issue requirements."""
    context = ""
    if context_files:
        context = "\n\nExisting code for context:\n"
        for path, content in context_files.items():
            context += f"\n--- {path} ---\n{content[:800]}\n"

    action = file_info.get("action", "create")

    system = f"""You are an expert developer. Write complete, working, production-quality code.
Return ONLY the raw file content — no explanations, no markdown fences.
The code must directly implement what the GitHub issue asks for."""

    user = f"""GitHub Issue #{issue['number']}: {issue['title']}
{issue.get('body', '')}

Task: {action.upper()} the file `{file_info['path']}`
What to do: {file_info['description']}
{context}

Write the complete {'new' if action == 'create' else 'updated'} file content:"""

    return llm(client, system, user, max_tokens=2500)


def run_issue_to_pr(groq_api_key: str, github_token: str, github_username: str,
                    repo: str, issue_number: int, base_branch: str = "main"):
    """
    Generator — yields status updates as pipeline runs.
    Each: {"status": str, "detail": str, "done": bool, "error": bool}
    """
    client = Groq(api_key=groq_api_key)

    # ── Step 1: Fetch Issue ────────────────────────────────────────────
    yield {"status": f"📋 Fetching issue #{issue_number}...", "detail": "", "done": False, "error": False}

    try:
        issue = get_issue(github_token, github_username, repo, issue_number)
        if not issue:
            yield {"status": f"❌ Issue #{issue_number} not found in `{repo}`", "detail": "", "done": False, "error": True}
            return
        yield {
            "status": f"Issue found: \"{issue['title']}\"",
            "detail": issue.get("body", "")[:150] + "..." if len(issue.get("body", "")) > 150 else issue.get("body", ""),
            "done": False,
            "error": False
        }
    except Exception as e:
        yield {"status": "❌ Could not fetch issue", "detail": str(e), "done": False, "error": True}
        return

    # ── Step 2: Scan Repo ──────────────────────────────────────────────
    yield {"status": "🔍 Scanning repository...", "detail": "", "done": False, "error": False}

    try:
        file_list = get_repo_files(github_token, github_username, repo)
        yield {"status": f"Found {len(file_list)} files", "detail": "", "done": False, "error": False}
    except Exception as e:
        file_list = []
        yield {"status": "⚠️ Could not scan repo files, continuing anyway", "detail": str(e), "done": False, "error": False}

    # ── Step 3: Plan Implementation ────────────────────────────────────
    yield {"status": "🧠 Planning implementation...", "detail": "", "done": False, "error": False}

    try:
        plan = plan_implementation(client, issue, file_list)
        branch_name = plan.get("branch_name", f"feature/issue-{issue_number}")
        files_to_change = plan.get("files_to_change", [])
        files_to_read = plan.get("files_to_read", [])

        yield {
            "status": f"Plan ready — {len(files_to_change)} file(s) to {'create/modify'}",
            "detail": plan.get("summary", ""),
            "done": False,
            "error": False
        }
        for f in files_to_change:
            yield {
                "status": f"  • {f['action'].upper()}: `{f['path']}`",
                "detail": f["description"],
                "done": False,
                "error": False
            }
    except Exception as e:
        yield {"status": "❌ Could not create implementation plan", "detail": str(e), "done": False, "error": True}
        return

    # ── Step 4: Read context files ─────────────────────────────────────
    context_files = {}
    for path in files_to_read:
        if path in file_list:
            content = get_file_content(github_token, github_username, repo, path)
            if content:
                context_files[path] = content

    # ── Step 5: Create Branch ──────────────────────────────────────────
    yield {"status": f"🌿 Creating branch `{branch_name}`...", "detail": "", "done": False, "error": False}

    try:
        result = create_branch(
            github_token,
            owner=github_username,
            repo=repo,
            branch_name=branch_name,
            from_branch=base_branch
        )
        if not result.get("success"):
            yield {"status": "⚠️ Branch may already exist, continuing...", "detail": "", "done": False, "error": False}
    except Exception as e:
        yield {"status": "⚠️ Branch creation issue, continuing...", "detail": str(e), "done": False, "error": False}

    # ── Step 6: Write & Push Code ──────────────────────────────────────
    pushed_files = []

    for file_info in files_to_change:
        yield {"status": f"✍️ Writing `{file_info['path']}`...", "detail": file_info["description"], "done": False, "error": False}

        try:
            code = write_code(client, issue, file_info, context_files)

            result = create_or_update_file(
                token=github_token,
                owner=github_username,
                repo=repo,
                path=file_info["path"],
                content=code,
                message=f"feat: resolve issue #{issue_number} - {file_info['description'][:60]}",
                branch=branch_name
            )

            if result.get("success"):
                pushed_files.append(file_info["path"])
                context_files[file_info["path"]] = code  # add to context for next files
                yield {"status": f"✅ Pushed `{file_info['path']}`", "detail": "", "done": False, "error": False}
            else:
                yield {"status": f"⚠️ Could not push `{file_info['path']}`", "detail": result.get("error", ""), "done": False, "error": False}

        except Exception as e:
            yield {"status": f"⚠️ Error writing `{file_info['path']}`", "detail": str(e), "done": False, "error": False}

    if not pushed_files:
        yield {"status": "❌ No files were pushed", "detail": "", "done": True, "error": True}
        return

    # ── Step 7: Open PR ────────────────────────────────────────────────
    yield {"status": "📬 Opening Pull Request...", "detail": "", "done": False, "error": False}

    files_list = "\n".join([f"- `{f}`" for f in pushed_files])
    pr_body = f"""## 🤖 Resolves #{issue_number}: {issue['title']}

{plan.get('summary', '')}

### Files Changed
{files_list}

### Implementation Notes
This PR was automatically generated by GitHub Agent based on the issue description.

Closes #{issue_number}

---
*Auto-generated by GitHub Agent 🐙*"""

    try:
        result = create_pull_request(
            token=github_token,
            owner=github_username,
            repo=repo,
            title=f"feat: resolve #{issue_number} - {issue['title'][:60]}",
            body=pr_body,
            head=branch_name,
            base=base_branch
        )

        if result.get("success"):
            pr_url = result.get("url", f"https://github.com/{github_username}/{repo}/pulls")
            yield {
                "status": "✅ PR opened successfully!",
                "detail": pr_url,
                "done": True,
                "error": False,
                "pr_url": pr_url
            }
        else:
            yield {"status": "⚠️ Code pushed but PR failed", "detail": result.get("error", ""), "done": True, "error": False}

    except Exception as e:
        yield {"status": "⚠️ Code pushed but PR failed", "detail": str(e), "done": True, "error": False}