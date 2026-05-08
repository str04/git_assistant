"""
Multi-Agent Pipeline for GitHub Agent
======================================
Agents:
  1. Planner Agent    — designs file structure with explicit import map
  2. Code Writer Agent — writes each file with full context + self-review
  3. Test Agent       — writes runnable unit tests
  4. Docs Agent       — generates professional README
"""

import json
import re
from groq import Groq
from config import MODEL, GITHUB_API, get_github_headers
from tools.repos import create_repo
from tools.files import create_or_update_file
import requests


# ── Helpers ─────────────────────────────────────────────────────────────

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
    # Try to extract JSON from markdown fences
    fenced = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


def strip_code_fences(code: str) -> str:
    """Remove markdown code fences from LLM output."""
    code = code.strip()
    fenced = re.search(r'```(?:\w+)?\s*([\s\S]*?)```', code)
    if fenced:
        return fenced.group(1).strip()
    return code


# ── Agent 1: Planner ─────────────────────────────────────────────────────

def planner_agent(client: Groq, user_prompt: str, github_username: str) -> dict:
    system = """You are a senior software architect. Design a minimal, working file structure.

Return ONLY valid JSON:
{
  "repo_name": "short-kebab-case-name",
  "description": "one line description",
  "language": "python|javascript|typescript",
  "entry_point": "main file name e.g. app.py",
  "files": [
    {
      "path": "relative/path/file.ext",
      "description": "what this file does",
      "imports_from": ["other files in this project it imports from"]
    }
  ]
}

STRICT RULES:
- repo_name: lowercase, hyphens only, no spaces
- Max 6 files — keep it focused
- Always include: main entry point, requirements.txt or package.json, .gitignore
- No README (handled separately)
- imports_from: list only files within THIS project, not external libraries
- Every file must have a clear single responsibility
- Return ONLY the JSON object, no extra text"""

    user = f"Build this: {user_prompt}"
    raw = llm(client, system, user, max_tokens=1500)
    return parse_json(raw)


# ── Agent 2: Code Writer ──────────────────────────────────────────────────

def code_writer_agent(client: Groq, file_info: dict, project_plan: dict, existing_files: dict) -> str:
    language = project_plan["language"]
    path = file_info["path"]
    ext = path.split(".")[-1] if "." in path else ""

    # Build full context of already-written files
    context = ""
    if existing_files:
        context = "\n\n=== Already written files (use these exact function names and imports) ===\n"
        for fpath, fcontent in existing_files.items():
            context += f"\n--- {fpath} ---\n{fcontent}\n"

    # Special handling for config/dependency files
    if ext in ("txt", "json", "toml", "cfg", "ini") or path in ("requirements.txt", "package.json", ".gitignore", "Makefile"):
        system = f"""You are an expert {language} developer.
Write the exact content for this configuration/dependency file.
Return ONLY the raw file content — no markdown fences, no explanations."""

        user = f"""Project: {project_plan['description']}
Language: {language}
Entry point: {project_plan.get('entry_point', 'main file')}

Write the complete content for: {path}
Purpose: {file_info['description']}
{context}

IMPORTANT: For requirements.txt include ALL libraries used across the project files above.
For .gitignore include standard ignores for {language}."""
        code = llm(client, system, user, max_tokens=500)
        return strip_code_fences(code)

    # Full code files
    imports_from = file_info.get("imports_from", [])
    imports_note = ""
    if imports_from:
        imports_note = f"\nThis file imports from: {', '.join(imports_from)} — use the exact function/class names defined in those files."

    system = f"""You are an expert {language} developer writing production-quality code.

RULES — follow every one:
1. Write COMPLETE, RUNNABLE code — no placeholders, no TODO comments, no '...'
2. Every function must have a real implementation
3. All imports must match exactly what is defined in the other project files
4. Handle errors properly with try/except or error checking
5. Use correct syntax — the code must run without any errors
6. Return ONLY the raw code — no markdown fences, no explanations"""

    user = f"""Project: {project_plan['description']}
Language: {language}
{imports_note}

Write the complete, working code for: {path}
Purpose: {file_info['description']}
{context}

Return ONLY the raw {language} code. No markdown. No explanations. Must be 100% runnable."""

    code = llm(client, system, user, max_tokens=2500)
    code = strip_code_fences(code)

    # Self-review pass — fix any obvious issues
    code = self_review_agent(client, code, path, language, project_plan, existing_files)
    return code


# ── Agent 2b: Self-Review ─────────────────────────────────────────────────

def self_review_agent(client: Groq, code: str, path: str, language: str, project_plan: dict, existing_files: dict) -> str:
    """Reviews generated code and fixes any issues before pushing."""

    # Build imports reference
    imports_ref = ""
    if existing_files:
        imports_ref = "Other project files:\n"
        for fpath, fcontent in existing_files.items():
            imports_ref += f"\n--- {fpath} ---\n{fcontent[:600]}\n"

    system = f"""You are a strict {language} code reviewer and fixer.
Review the code and fix ANY issues:
- Wrong imports or import paths
- Missing function implementations (no placeholders or TODOs)  
- Syntax errors
- Inconsistent function/variable names vs other files
- Missing error handling
- Incomplete logic

Return the FIXED complete code ONLY — no markdown, no explanations.
If the code is already correct, return it unchanged."""

    user = f"""Fix this {language} code for file: {path}
Project: {project_plan['description']}

Code to review:
{code}

{imports_ref}

Return ONLY the fixed, complete, runnable code."""

    fixed = llm(client, system, user, max_tokens=2500)
    return strip_code_fences(fixed)


# ── Agent 3: Test Writer ──────────────────────────────────────────────────

def test_agent(client: Groq, project_plan: dict, created_files: dict) -> dict:
    language = project_plan["language"]

    framework_map = {
        "python": "pytest",
        "javascript": "jest",
        "typescript": "jest",
        "java": "JUnit",
        "go": "Go testing package"
    }
    framework = framework_map.get(language, "pytest")

    skip_extensions = {".txt", ".json", ".gitignore", ".env", ".md", ".cfg", ".ini", ".toml"}
    source_files = {
        path: content for path, content in created_files.items()
        if not any(path.endswith(ext) for ext in skip_extensions)
        and "test" not in path.lower()
    }

    if not source_files:
        return None

    files_context = "\n\n".join([f"--- {p} ---\n{c}" for p, c in source_files.items()])

    system = f"""You are an expert {language} test engineer writing with {framework}.

RULES:
1. Write REAL tests — not placeholder tests
2. Import correctly from the actual source files
3. Cover: happy path, edge cases, error cases
4. Every test must be runnable — no missing imports, no undefined variables
5. Mock external API calls and database connections
6. Return ONLY the raw test file — no markdown, no explanations"""

    user = f"""Write complete {framework} tests for this project:
{project_plan['description']}

Source files:
{files_context[:4000]}

Return ONLY the runnable test file."""

    content = llm(client, system, user, max_tokens=2500)
    content = strip_code_fences(content)

    test_path_map = {
        "python": "tests/test_main.py",
        "javascript": "tests/main.test.js",
        "typescript": "tests/main.test.ts",
        "java": "src/test/MainTest.java",
        "go": "main_test.go"
    }

    return {"path": test_path_map.get(language, "tests/test_main.py"), "content": content}


# ── Agent 4: Docs Agent ───────────────────────────────────────────────────

def docs_agent(client: Groq, project_plan: dict, created_files: dict, github_username: str) -> str:
    files_summary = "\n".join([f"- `{path}`" for path in created_files.keys()])
    entry = project_plan.get("entry_point", "main file")
    lang = project_plan["language"]

    # Get requirements if available
    reqs = created_files.get("requirements.txt", created_files.get("package.json", ""))[:300]

    system = """You are a technical writer. Write a clean professional README.md.
Include: title with emoji, description, features list, tech stack, installation steps, 
usage with code examples, project structure, and license.
Use proper markdown. Return ONLY the raw markdown."""

    user = f"""Create README for:
Name: {project_plan['repo_name']}
Description: {project_plan['description']}
Language: {lang}
Entry point: {entry}
GitHub: {github_username}

Files:
{files_summary}

Dependencies:
{reqs}

Write a complete professional README.md."""

    return llm(client, system, user, max_tokens=2000)


# ── Main Pipeline ─────────────────────────────────────────────────────────

def run_pipeline(groq_api_key: str, github_token: str, github_username: str, user_prompt: str):
    """
    Generator — yields status update dicts as each step completes.
    Each: {"status": str, "detail": str, "done": bool, "error": bool}
    """
    client = Groq(api_key=groq_api_key)

    # ── Step 1: Plan ───────────────────────────────────────────────────
    yield {"status": "🧠 Planner Agent — analyzing requirements...", "detail": "", "done": False, "error": False}

    try:
        plan = planner_agent(client, user_prompt, github_username)
        repo_name = plan["repo_name"]
        files = plan["files"]
        yield {
            "status": f"✅ Plan ready — `{repo_name}` with {len(files)} files",
            "detail": "\n".join([f"• {f['path']} — {f['description']}" for f in files]),
            "done": True,
            "error": False
        }
    except Exception as e:
        yield {"status": "❌ Planner failed", "detail": str(e), "done": False, "error": True}
        return

    # ── Step 2: Create Repo ────────────────────────────────────────────
    yield {"status": f"🏗️ Creating repository `{repo_name}`...", "detail": "", "done": False, "error": False}

    try:
        result = create_repo(github_token, name=repo_name, description=plan.get("description", ""), private=False, auto_init=False)
        if result.get("success"):
            yield {"status": f"✅ Repo created", "detail": f"https://github.com/{github_username}/{repo_name}", "done": False, "error": False}
        else:
            error_msg = result.get("error", "")
            # If repo already exists, continue using it instead of failing
            if "already exists" in error_msg.lower() or "name already exists" in error_msg.lower():
                yield {"status": f"⚠️ Repo `{repo_name}` already exists — pushing files into it", "detail": "", "done": False, "error": False}
            else:
                # Try with a suffix to make name unique
                import time
                repo_name = f"{repo_name}-{int(time.time()) % 1000}"
                yield {"status": f"⚠️ Name taken — trying `{repo_name}`...", "detail": "", "done": False, "error": False}
                result2 = create_repo(github_token, name=repo_name, description=plan.get("description", ""), private=False, auto_init=False)
                if not result2.get("success"):
                    yield {"status": "❌ Could not create repo", "detail": result2.get("error", error_msg), "done": False, "error": True}
                    return
                yield {"status": f"✅ Repo created as `{repo_name}`", "detail": f"https://github.com/{github_username}/{repo_name}", "done": False, "error": False}
    except Exception as e:
        yield {"status": "❌ Could not create repo", "detail": str(e), "done": False, "error": True}
        return

    # ── Step 3: Write & Push Files ─────────────────────────────────────
    created_files = {}

    # Write requirements.txt / package.json / .gitignore FIRST so code files can reference them
    priority_files = [f for f in files if f["path"] in ("requirements.txt", "package.json", ".gitignore", "Makefile")]
    other_files = [f for f in files if f not in priority_files]
    ordered_files = priority_files + other_files

    for i, file_info in enumerate(ordered_files):
        yield {
            "status": f"✍️ Writing file {i+1}/{len(ordered_files)}: `{file_info['path']}`",
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
                yield {"status": f"✅ Pushed `{file_info['path']}`", "detail": "", "done": False, "error": False}
            else:
                yield {"status": f"⚠️ Could not push `{file_info['path']}`", "detail": result.get("error", ""), "done": False, "error": False}

        except Exception as e:
            yield {"status": f"⚠️ Error on `{file_info['path']}`", "detail": str(e), "done": False, "error": False}

    yield {"status": f"✅ All {len(created_files)} files pushed", "detail": "", "done": True, "error": False}

    # ── Step 4: Tests ──────────────────────────────────────────────────
    yield {"status": "🧪 Test Agent — writing unit tests...", "detail": "", "done": False, "error": False}

    try:
        test_result = test_agent(client, plan, created_files)
        if test_result:
            result = create_or_update_file(
                token=github_token,
                owner=github_username,
                repo=repo_name,
                path=test_result["path"],
                content=test_result["content"],
                message="Add unit tests",
                branch="main"
            )
            if result.get("success"):
                created_files[test_result["path"]] = test_result["content"]
                yield {"status": f"✅ Tests written — `{test_result['path']}`", "detail": "", "done": True, "error": False}
            else:
                yield {"status": "⚠️ Could not push tests", "detail": result.get("error", ""), "done": True, "error": False}
        else:
            yield {"status": "⚠️ No source files to test", "detail": "", "done": True, "error": False}
    except Exception as e:
        yield {"status": "⚠️ Test generation failed", "detail": str(e), "done": True, "error": False}

    # ── Step 5: README ─────────────────────────────────────────────────
    yield {"status": "📄 Docs Agent — generating README...", "detail": "", "done": False, "error": False}

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
            yield {"status": "✅ README generated", "detail": "", "done": True, "error": False}
        else:
            yield {"status": "⚠️ Could not push README", "detail": result.get("error", ""), "done": True, "error": False}
    except Exception as e:
        yield {"status": "⚠️ README generation failed", "detail": str(e), "done": True, "error": False}

    # ── Done ───────────────────────────────────────────────────────────
    yield {
        "status": "🎉 Project complete!",
        "detail": f"https://github.com/{github_username}/{repo_name}",
        "done": True,
        "error": False,
        "repo_url": f"https://github.com/{github_username}/{repo_name}"
    }