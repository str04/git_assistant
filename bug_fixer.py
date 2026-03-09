"""
Bug Fixer Agent
================
Takes an error message + repo info → finds the file causing the bug
→ understands the fix → applies it directly to GitHub → opens a PR

Usage:
    from bug_fixer import run_bug_fixer
    for update in run_bug_fixer(groq_api_key, github_token, github_username, repo, error_message):
        print(update)
"""

import json
import requests
import base64
from groq import Groq
from config import MODEL, GITHUB_API, get_github_headers
from tools.files import get_file, create_or_update_file, list_files
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


def get_repo_file_list(token: str, owner: str, repo: str, path: str = "") -> list:
    """Recursively get all files in a repo (max depth 2 to avoid rate limits)."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    resp = requests.get(url, headers=get_github_headers(token))
    if resp.status_code != 200:
        return []
    items = resp.json()
    files = []
    for item in items:
        if item["type"] == "file":
            files.append(item["path"])
        elif item["type"] == "dir" and path == "":
            # Only go one level deep into dirs
            files.extend(get_repo_file_list(token, owner, repo, item["path"]))
    return files


def get_file_content(token: str, owner: str, repo: str, path: str) -> str:
    """Fetch raw file content from GitHub."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    resp = requests.get(url, headers=get_github_headers(token))
    if resp.status_code == 200:
        data = resp.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    return ""


def identify_buggy_files(client: Groq, error_message: str, file_list: list) -> list:
    """Ask the LLM which files are likely causing the error."""
    files_str = "\n".join(file_list)
    system = """You are an expert debugger. Given an error message and a list of files in a repo,
identify which files are most likely causing the error.
Return ONLY a JSON array of file paths (max 3 files), most likely first.
Example: ["src/main.py", "utils/helper.py"]
Return ONLY the JSON array, nothing else."""

    user = f"""Error message:
{error_message}

Files in repo:
{files_str}

Which files are most likely causing this error?"""

    raw = llm(client, system, user, max_tokens=500)
    raw = raw.strip()
    if raw.startswith("["):
        return json.loads(raw)
    # fallback — try to extract array
    import re
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return []


def analyze_and_fix(client: Groq, error_message: str, file_path: str, file_content: str) -> dict:
    """Analyze the bug and return the fixed file content."""
    system = """You are an expert software engineer and debugger.
Given an error message and a file's content, fix the bug.

Return ONLY a JSON object with this exact structure:
{
  "has_bug": true or false,
  "explanation": "brief explanation of what was wrong",
  "fix_summary": "one line description of the fix",
  "fixed_content": "complete fixed file content here"
}

Rules:
- If the file doesn't contain the bug, set has_bug to false
- fixed_content must be the COMPLETE file, not just the changed lines
- Keep all existing functionality intact
- Return ONLY the JSON, no markdown fences"""

    user = f"""Error message:
{error_message}

File: {file_path}
Content:
{file_content[:4000]}"""

    raw = llm(client, system, user, max_tokens=3000)
    try:
        return parse_json(raw)
    except Exception:
        return {"has_bug": False, "explanation": "Could not analyze", "fix_summary": "", "fixed_content": file_content}


def run_bug_fixer(groq_api_key: str, github_token: str, github_username: str, repo: str, error_message: str, branch: str = "main"):
    """
    Generator that yields status updates as the bug fixer runs.
    Each update: {"status": str, "detail": str, "done": bool, "error": bool}
    """
    client = Groq(api_key=groq_api_key)

    # ── Step 1: Get repo files ─────────────────────────────────────────
    yield {"status": "🔍 Scanning repository files...", "detail": "", "done": False, "error": False}

    try:
        file_list = get_repo_file_list(github_token, github_username, repo)
        # Filter to only code files
        code_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rb', '.php', '.cpp', '.c', '.cs'}
        code_files = [f for f in file_list if any(f.endswith(ext) for ext in code_extensions)]

        if not code_files:
            yield {"status": "❌ No code files found in repo", "detail": f"Repo: {repo}", "done": False, "error": True}
            return

        yield {"status": f"Found {len(code_files)} code files", "detail": "", "done": False, "error": False}
    except Exception as e:
        yield {"status": "❌ Could not read repo files", "detail": str(e), "done": False, "error": True}
        return

    # ── Step 2: Identify buggy files ───────────────────────────────────
    yield {"status": "🧠 Analyzing error to find the buggy file(s)...", "detail": "", "done": False, "error": False}

    try:
        buggy_files = identify_buggy_files(client, error_message, code_files)
        if not buggy_files:
            yield {"status": "❌ Could not identify which files contain the bug", "detail": "Try providing more specific error details", "done": False, "error": True}
            return

        yield {"status": f"Suspected files: {', '.join(buggy_files)}", "detail": "", "done": False, "error": False}
    except Exception as e:
        yield {"status": "❌ Error during analysis", "detail": str(e), "done": False, "error": True}
        return

    # ── Step 3: Read and fix each suspected file ───────────────────────
    fixes_applied = []

    for file_path in buggy_files:
        yield {"status": f"🔧 Analyzing `{file_path}`...", "detail": "", "done": False, "error": False}

        try:
            content = get_file_content(github_token, github_username, repo, file_path)
            if not content:
                yield {"status": f"⚠️ Could not read `{file_path}`", "detail": "", "done": False, "error": False}
                continue

            result = analyze_and_fix(client, error_message, file_path, content)

            if result.get("has_bug") and result.get("fixed_content"):
                yield {
                    "status": f"🐛 Bug found in `{file_path}`!",
                    "detail": result.get("explanation", ""),
                    "done": False,
                    "error": False
                }
                fixes_applied.append({
                    "file": file_path,
                    "fix_summary": result.get("fix_summary", "Fix applied"),
                    "fixed_content": result["fixed_content"],
                    "explanation": result.get("explanation", "")
                })
            else:
                yield {"status": f"✅ `{file_path}` looks clean", "detail": "", "done": False, "error": False}

        except Exception as e:
            yield {"status": f"⚠️ Error analyzing `{file_path}`", "detail": str(e), "done": False, "error": False}

    if not fixes_applied:
        yield {"status": "🤔 No bugs found in suspected files", "detail": "The error might be in a config file or external dependency", "done": True, "error": False}
        return

    # ── Step 4: Create a fix branch ────────────────────────────────────
    fix_branch = f"fix/auto-bug-fix"
    yield {"status": f"🌿 Creating branch `{fix_branch}`...", "detail": "", "done": False, "error": False}

    try:
        result = create_branch(github_token, owner=github_username, repo=repo, branch_name=fix_branch, from_branch=branch)
        if not result.get("success"):
            # Branch might already exist, continue anyway
            pass
    except Exception:
        pass

    # ── Step 5: Push fixes ─────────────────────────────────────────────
    pushed = []
    for fix in fixes_applied:
        yield {"status": f"⬆️ Pushing fix for `{fix['file']}`...", "detail": fix["fix_summary"], "done": False, "error": False}
        try:
            result = create_or_update_file(
                token=github_token,
                owner=github_username,
                repo=repo,
                path=fix["file"],
                content=fix["fixed_content"],
                message=f"fix: {fix['fix_summary']}",
                branch=fix_branch
            )
            if result.get("success"):
                pushed.append(fix["file"])
            else:
                yield {"status": f"⚠️ Could not push fix for `{fix['file']}`", "detail": result.get("error", ""), "done": False, "error": False}
        except Exception as e:
            yield {"status": f"⚠️ Push failed for `{fix['file']}`", "detail": str(e), "done": False, "error": False}

    if not pushed:
        yield {"status": "❌ Could not push any fixes", "detail": "", "done": True, "error": True}
        return

    # ── Step 6: Open PR ────────────────────────────────────────────────
    yield {"status": "📬 Opening Pull Request...", "detail": "", "done": False, "error": False}

    fixes_summary = "\n".join([f"- `{f['file']}`: {f['fix_summary']}" for f in fixes_applied if f['file'] in pushed])
    pr_body = f"""## 🤖 Auto Bug Fix

**Error fixed:**
```
{error_message[:500]}
```

**Files changed:**
{fixes_summary}

**How it was fixed:**
{fixes_applied[0].get('explanation', 'Bug identified and fixed automatically.')}

---
*This PR was automatically generated by GitHub Agent Bug Fixer* 🐙
"""

    try:
        result = create_pull_request(
            token=github_token,
            owner=github_username,
            repo=repo,
            title=f"🐛 Auto-fix: {fixes_applied[0].get('fix_summary', 'Bug fix')}",
            body=pr_body,
            head=fix_branch,
            base=branch
        )
        if result.get("success"):
            pr_url = result.get("url", f"https://github.com/{github_username}/{repo}/pulls")
            yield {
                "status": "✅ Bug fixed! PR opened.",
                "detail": pr_url,
                "done": True,
                "error": False,
                "pr_url": pr_url
            }
        else:
            yield {"status": "⚠️ Fixes pushed but could not open PR", "detail": result.get("error", ""), "done": True, "error": False}
    except Exception as e:
        yield {"status": "⚠️ Fixes pushed but PR failed", "detail": str(e), "done": True, "error": False}