"""
Multi-Agent Pipeline for GitHub Agent
======================================
Agents:
  1. Planner Agent   — understands requirements, designs file structure
  2. Repo Setup Agent — creates repo, folders, and all files on GitHub
  3. Test Agent      — reads created code and writes unit tests
  4. Docs Agent      — generates a professional README

Usage:
  from multi_agent import run_pipeline
  for update in run_pipeline(groq_api_key, github_token, github_username, user_prompt):
      print(update)  # stream status updates to UI
"""

import json
from groq import Groq
from config import MODEL, GITHUB_API, get_github_headers
from tools.repos import create_repo
from tools.files import create_or_update_file
import requests

# ── Helpers ────────────────────────────────────────────────────────────

def llm(client: Groq, system: str, user: str, max_tokens: int = 3000) -> str:
    """Simple single-turn LLM call — returns text."""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        max_tokens=max_tokens,
        temperature=0.3
    )
    return resp.choices[0].message.content.strip()


def parse_json(text: str) -> dict:
    """Safely parse JSON from LLM output — strips markdown fences."""
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def get_file_content(token: str, owner: str, repo: str, path: str) -> str:
    """Fetch a file's content from GitHub."""
    import base64
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    resp = requests.get(url, headers=get_github_headers(token))
    if resp.status_code == 200:
        return base64.b64decode(resp.json()["content"]).decode("utf-8", errors="ignore")
    return ""


# ── Agent 1: Planner ───────────────────────────────────────────────────

def planner_agent(client: Groq, user_prompt: str, github_username: str) -> dict:
    """
    Takes user requirement and returns a full project plan:
    {
      "repo_name": "flask-rest-api",
      "description": "A REST API built with Flask",
      "language": "python",
      "files": [
        {"path": "app.py", "description": "Main Flask application with routes"},
        {"path": "requirements.txt", "description": "Python dependencies"},
        ...
      ]
    }
    """
    system = """You are a senior software architect. Given a project requirement, 
you design a clean, minimal file structure for a real working project.

Return ONLY a JSON object with this exact structure:
{
  "repo_name": "short-kebab-case-name",
  "description": "one line description",
  "language": "python|javascript|typescript|java|go",
  "files": [
    {"path": "relative/path/file.ext", "description": "what this file contains and does"}
  ]
}

Rules:
- repo_name must be lowercase with hyphens only, no spaces
- Include 4-8 files max — keep it focused and real
- Always include a requirements.txt or package.json
- Always include a main entry point file
- Always include a .gitignore
- Paths use forward slashes
- No README (that's handled separately)
"""

    user = f"Project requirement: {user_prompt}\nGitHub username: {github_username}"
    raw = llm(client, system, user)
    return parse_json(raw)


# ── Agent 2: Code Writer ───────────────────────────────────────────────

def code_writer_agent(client: Groq, file_info: dict, project_plan: dict, existing_files: dict) -> str:
    """
    Given a file's path and description, writes the actual code for it.
    Also receives already-written files for context.
    """
    context = ""
    if existing_files:
        context = "\n\nAlready written files for context:\n"
        for path, content in existing_files.items():
            context += f"\n--- {path} ---\n{content[:500]}\n"

    system = f"""You are an expert {project_plan['language']} developer.
Write complete, working, production-quality code for the file requested.
Return ONLY the raw file content — no explanations, no markdown fences, no comments about what you're doing.
The code must actually work and be consistent with the other files in the project."""

    user = f"""Project: {project_plan['description']}
Language: {project_plan['language']}

Write the complete content for this file:
Path: {file_info['path']}
Purpose: {file_info['description']}
{context}"""

    return llm(client, system, user, max_tokens=2000)


# ── Agent 3: Test Writer ───────────────────────────────────────────────

def test_agent(client: Groq, project_plan: dict, created_files: dict) -> dict:
    """
    Reads all created source files and writes unit tests.
    Returns {"path": "tests/test_main.py", "content": "..."}
    """
    language = project_plan["language"]

    framework_map = {
        "python": "pytest",
        "javascript": "jest",
        "typescript": "jest",
        "java": "JUnit",
        "go": "Go testing package"
    }
    framework = framework_map.get(language, "appropriate testing framework")

    # Pick main source files (skip config, requirements, gitignore)
    skip_extensions = {".txt", ".json", ".gitignore", ".env", ".md", ".cfg", ".ini", ".toml"}
    source_files = {
        path: content for path, content in created_files.items()
        if not any(path.endswith(ext) for ext in skip_extensions)
        and not path.startswith("test")
    }

    if not source_files:
        return None

    files_context = "\n\n".join([f"--- {p} ---\n{c}" for p, c in source_files.items()])

    system = f"""You are an expert {language} test engineer.
Write comprehensive unit tests using {framework}.
Cover: normal cases, edge cases, and error cases.
Return ONLY the raw test file content — no markdown, no explanations."""

    user = f"""Write unit tests for this {language} project.

Project: {project_plan['description']}

Source files:
{files_context[:3000]}"""

    content = llm(client, system, user, max_tokens=2000)

    # Determine test file path
    test_path_map = {
        "python": "tests/test_main.py",
        "javascript": "tests/main.test.js",
        "typescript": "tests/main.test.ts",
        "java": "src/test/MainTest.java",
        "go": "main_test.go"
    }
    test_path = test_path_map.get(language, "tests/test_main.py")

    return {"path": test_path, "content": content}


# ── Agent 4: Docs Agent ────────────────────────────────────────────────

def docs_agent(client: Groq, project_plan: dict, created_files: dict, github_username: str) -> str:
    """Generates a professional README.md for the project."""

    files_summary = "\n".join([f"- {path}" for path in created_files.keys()])
    main_file = next(iter(created_files.values()), "")[:1000]

    system = """You are a technical writer. Write a clean, professional README.md.
Include: title, description, features, tech stack, installation, usage, project structure, license.
Use proper markdown formatting with emojis for section headers.
Return ONLY the raw markdown content."""

    user = f"""Create a README for this project:

Name: {project_plan['repo_name']}
Description: {project_plan['description']}
Language: {project_plan['language']}
GitHub username: {github_username}

Files in project:
{files_summary}

Main file preview:
{main_file}"""

    return llm(client, system, user, max_tokens=2000)


# ── Main Pipeline ──────────────────────────────────────────────────────

def run_pipeline(groq_api_key: str, github_token: str, github_username: str, user_prompt: str):
    """
    Run the full multi-agent pipeline.
    This is a generator — yields status update dicts as each step completes.

    Each update: {"agent": str, "status": str, "detail": str, "done": bool, "error": bool}
    """
    client = Groq(api_key=groq_api_key)

    # ── Agent 1: Plan ──────────────────────────────────────────────────
    yield {"agent": "🧠 Planner Agent", "status": "Analyzing your requirements...", "detail": "", "done": False, "error": False}

    try:
        plan = planner_agent(client, user_prompt, github_username)
    except Exception as e:
        yield {"agent": "🧠 Planner Agent", "status": "Failed to create plan", "detail": str(e), "done": False, "error": True}
        return

    repo_name = plan["repo_name"]
    files = plan["files"]
    yield {
        "agent": "🧠 Planner Agent",
        "status": f"Plan ready! Creating `{repo_name}` with {len(files)} files",
        "detail": "\n".join([f"• {f['path']}" for f in files]),
        "done": True,
        "error": False
    }

    # ── Agent 2: Create Repo ───────────────────────────────────────────
    yield {"agent": "🏗️ Repo Setup Agent", "status": f"Creating repository `{repo_name}`...", "detail": "", "done": False, "error": False}

    try:
        result = create_repo(github_token, name=repo_name, description=plan.get("description", ""), private=False, auto_init=False)
        if not result.get("success"):
            raise Exception(result.get("error", "Failed to create repo"))
    except Exception as e:
        yield {"agent": "🏗️ Repo Setup Agent", "status": "Failed to create repo", "detail": str(e), "done": False, "error": True}
        return

    yield {"agent": "🏗️ Repo Setup Agent", "status": f"Repo created ✅", "detail": f"https://github.com/{github_username}/{repo_name}", "done": False, "error": False}

    # ── Agent 2: Write & Push Files ────────────────────────────────────
    created_files = {}

    for i, file_info in enumerate(files):
        yield {
            "agent": "🏗️ Repo Setup Agent",
            "status": f"Writing file {i+1}/{len(files)}: `{file_info['path']}`",
            "detail": file_info["description"],
            "done": False,
            "error": False
        }

        try:
            content = code_writer_agent(client, file_info, plan, created_files)
            result = create_or_update_file(
                token=github_token,
                owner=github_username,
                repo=repo_name,
                path=file_info["path"],
                content=content,
                message=f"Add {file_info['path']}",
                branch="main"
            )
            if result.get("success"):
                created_files[file_info["path"]] = content
            else:
                yield {"agent": "🏗️ Repo Setup Agent", "status": f"⚠️ Could not push `{file_info['path']}`", "detail": result.get("error", ""), "done": False, "error": False}
        except Exception as e:
            yield {"agent": "🏗️ Repo Setup Agent", "status": f"⚠️ Error on `{file_info['path']}`", "detail": str(e), "done": False, "error": False}

    yield {"agent": "🏗️ Repo Setup Agent", "status": f"All files pushed ✅", "detail": f"{len(created_files)} files created", "done": True, "error": False}

    # ── Agent 3: Tests ─────────────────────────────────────────────────
    yield {"agent": "🧪 Test Agent", "status": "Writing unit tests...", "detail": "", "done": False, "error": False}

    try:
        test_result = test_agent(client, plan, created_files)
        if test_result:
            result = create_or_update_file(
                token=github_token,
                owner=github_username,
                repo=repo_name,
                path=test_result["path"],
                content=test_result["content"],
                message=f"Add unit tests",
                branch="main"
            )
            if result.get("success"):
                created_files[test_result["path"]] = test_result["content"]
                yield {"agent": "🧪 Test Agent", "status": "Unit tests written ✅", "detail": f"Saved to `{test_result['path']}`", "done": True, "error": False}
            else:
                yield {"agent": "🧪 Test Agent", "status": "⚠️ Could not push tests", "detail": result.get("error", ""), "done": True, "error": False}
        else:
            yield {"agent": "🧪 Test Agent", "status": "⚠️ No source files to test", "detail": "", "done": True, "error": False}
    except Exception as e:
        yield {"agent": "🧪 Test Agent", "status": "⚠️ Test generation failed", "detail": str(e), "done": True, "error": False}

    # ── Agent 4: README ────────────────────────────────────────────────
    yield {"agent": "📄 Docs Agent", "status": "Generating README...", "detail": "", "done": False, "error": False}

    try:
        readme = docs_agent(client, plan, created_files, github_username)
        result = create_or_update_file(
            token=github_token,
            owner=github_username,
            repo=repo_name,
            path="README.md",
            content=readme,
            message="Add README",
            branch="main"
        )
        if result.get("success"):
            yield {"agent": "📄 Docs Agent", "status": "README generated ✅", "detail": "Saved to repo", "done": True, "error": False}
        else:
            yield {"agent": "📄 Docs Agent", "status": "⚠️ Could not push README", "detail": result.get("error", ""), "done": True, "error": False}
    except Exception as e:
        yield {"agent": "📄 Docs Agent", "status": "⚠️ Docs generation failed", "detail": str(e), "done": True, "error": False}

    # ── Final ──────────────────────────────────────────────────────────
    yield {
        "agent": "✅ Pipeline Complete",
        "status": f"Your project is live on GitHub!",
        "detail": f"https://github.com/{github_username}/{repo_name}",
        "done": True,
        "error": False,
        "repo_url": f"https://github.com/{github_username}/{repo_name}"
    }
