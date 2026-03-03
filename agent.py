import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import requests
from groq import Groq
from config import GROQ_API_KEY, MODEL, GITHUB_API, get_github_headers
from tools.repos import create_repo, delete_repo, list_repos, get_repo, fork_repo, get_authenticated_user
from tools.files import get_file, create_or_update_file, delete_file, list_files, list_commits
from tools.branches import list_branches, create_branch, delete_branch, merge_branches
from tools.pulls import create_pull_request, list_pull_requests, merge_pull_request, close_pull_request, add_pr_comment
from tools.issues import create_issue, list_issues, close_issue, add_issue_comment, add_labels
from tools.search import search_repos, search_code, get_repo_summary, get_user_profile
from tools.file_editor import edit_lines, insert_lines, delete_lines, find_and_replace, get_file_preview, append_to_file
from tools.pr_review import get_pr_diff, get_pr_review_prompt, post_review_comment
from tools.ai_generator import (
    get_repo_files_content, build_readme_prompt,
    build_test_prompt, detect_language, get_test_file_path
)

# ── Tool definitions ───────────────────────────────────────────────────
TOOL_DEFINITIONS = [
    # ── Repos ──────────────────────────────────────────────────────────
    {"type": "function", "function": {"name": "create_repo", "description": "Create a new GitHub repository.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "private": {"type": "string", "enum": ["true", "false"]}, "auto_init": {"type": "string", "enum": ["true", "false"]}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "delete_repo", "description": "Delete a GitHub repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "list_repos", "description": "List repositories for the authenticated user or a given username.", "parameters": {"type": "object", "properties": {"username": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_repo", "description": "Get details about a specific repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "fork_repo", "description": "Fork a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},

    # ── Files ──────────────────────────────────────────────────────────
    {"type": "function", "function": {"name": "get_file", "description": "Read the full contents of a file in a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path"]}}},
    {"type": "function", "function": {"name": "create_or_update_file", "description": "Create or fully overwrite a file in a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "content": {"type": "string"}, "message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "content", "message"]}}},
    {"type": "function", "function": {"name": "delete_file", "description": "Delete a file from a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "message"]}}},
    {"type": "function", "function": {"name": "list_files", "description": "List files in a directory of a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "list_commits", "description": "List recent commits on a branch.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "branch": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["owner", "repo"]}}},

    # ── Smart File Editor ──────────────────────────────────────────────
    {"type": "function", "function": {"name": "get_file_preview", "description": "Preview specific lines of a file without loading the whole thing.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path"]}}},
    {"type": "function", "function": {"name": "edit_lines", "description": "Edit/replace specific lines in a file.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}, "new_content": {"type": "string"}, "commit_message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "start_line", "end_line", "new_content", "commit_message"]}}},
    {"type": "function", "function": {"name": "insert_lines", "description": "Insert new lines after a specific line number in a file.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "after_line": {"type": "integer"}, "new_content": {"type": "string"}, "commit_message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "after_line", "new_content", "commit_message"]}}},
    {"type": "function", "function": {"name": "delete_lines", "description": "Delete specific lines from a file.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}, "commit_message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "start_line", "end_line", "commit_message"]}}},
    {"type": "function", "function": {"name": "find_and_replace", "description": "Find and replace text in a file.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "find_text": {"type": "string"}, "replace_text": {"type": "string"}, "commit_message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "find_text", "replace_text", "commit_message"]}}},
    {"type": "function", "function": {"name": "append_to_file", "description": "Append content to the end of a file.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "content_to_append": {"type": "string"}, "commit_message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "content_to_append", "commit_message"]}}},

    # ── Branches ───────────────────────────────────────────────────────
    {"type": "function", "function": {"name": "list_branches", "description": "List all branches in a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "create_branch", "description": "Create a new branch.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "branch_name": {"type": "string"}, "from_branch": {"type": "string"}}, "required": ["owner", "repo", "branch_name"]}}},
    {"type": "function", "function": {"name": "delete_branch", "description": "Delete a branch.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "branch_name": {"type": "string"}}, "required": ["owner", "repo", "branch_name"]}}},
    {"type": "function", "function": {"name": "merge_branches", "description": "Merge one branch into another.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "base": {"type": "string"}, "head": {"type": "string"}, "commit_message": {"type": "string"}}, "required": ["owner", "repo", "base", "head"]}}},

    # ── Pull Requests ──────────────────────────────────────────────────
    {"type": "function", "function": {"name": "create_pull_request", "description": "Create a pull request.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}, "head": {"type": "string"}, "base": {"type": "string"}}, "required": ["owner", "repo", "title", "body", "head"]}}},
    {"type": "function", "function": {"name": "list_pull_requests", "description": "List pull requests in a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "state": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "merge_pull_request", "description": "Merge a pull request.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "pr_number": {"type": "integer"}, "merge_method": {"type": "string"}}, "required": ["owner", "repo", "pr_number"]}}},
    {"type": "function", "function": {"name": "close_pull_request", "description": "Close a pull request without merging.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "pr_number": {"type": "integer"}}, "required": ["owner", "repo", "pr_number"]}}},
    {"type": "function", "function": {"name": "add_pr_comment", "description": "Add a comment to a pull request.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "pr_number": {"type": "integer"}, "comment": {"type": "string"}}, "required": ["owner", "repo", "pr_number", "comment"]}}},

    # ── PR Review (AI) ─────────────────────────────────────────────────
    {"type": "function", "function": {"name": "review_pull_request", "description": "AI-powered code review of a pull request. Reads the diff, identifies bugs, security issues, missing tests, and auto-generates a PR description.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "pr_number": {"type": "integer"}, "post_as_comment": {"type": "boolean"}}, "required": ["owner", "repo", "pr_number"]}}},

    # ── AI Generators ──────────────────────────────────────────────────
    {"type": "function", "function": {"name": "generate_readme", "description": "AI-powered README generator. Reads ALL files in a repo and generates a professional complete README.md. Always saves to repo automatically.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "generate_tests", "description": "AI-powered unit test generator. Reads a code file and generates comprehensive unit tests for all functions.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "file_path": {"type": "string"}, "save_to_repo": {"type": "boolean"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "file_path"]}}},

    # ── Issues ─────────────────────────────────────────────────────────
    {"type": "function", "function": {"name": "create_issue", "description": "Create a new issue.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}, "labels": {"type": "array", "items": {"type": "string"}}}, "required": ["owner", "repo", "title"]}}},
    {"type": "function", "function": {"name": "list_issues", "description": "List issues in a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "state": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "close_issue", "description": "Close an issue.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "issue_number": {"type": "integer"}}, "required": ["owner", "repo", "issue_number"]}}},
    {"type": "function", "function": {"name": "add_issue_comment", "description": "Add a comment to an issue.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "issue_number": {"type": "integer"}, "comment": {"type": "string"}}, "required": ["owner", "repo", "issue_number", "comment"]}}},
    {"type": "function", "function": {"name": "add_labels", "description": "Add labels to an issue.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "issue_number": {"type": "integer"}, "labels": {"type": "array", "items": {"type": "string"}}}, "required": ["owner", "repo", "issue_number", "labels"]}}},

    # ── Search ─────────────────────────────────────────────────────────
    {"type": "function", "function": {"name": "search_repos", "description": "Search GitHub repositories.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "language": {"type": "string"}, "sort": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_code", "description": "Search for code on GitHub.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_repo_summary", "description": "Get a detailed summary of a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "get_user_profile", "description": "Get a GitHub user's profile.", "parameters": {"type": "object", "properties": {"username": {"type": "string"}}, "required": ["username"]}}},
]


def execute_tool(tool_name: str, tool_args: dict, github_token: str, github_username: str, groq_client=None) -> str:
    try:
        # ── PR Review ──────────────────────────────────────────────────
        if tool_name == "review_pull_request":
            owner = tool_args.get("owner", github_username)
            repo = tool_args["repo"]
            pr_number = tool_args["pr_number"]
            post_as_comment = tool_args.get("post_as_comment", False)

            diff_data = get_pr_diff(github_token, owner, repo, pr_number)
            if not diff_data["success"]:
                return json.dumps({"error": diff_data["error"]})
            if not diff_data["diff"]:
                return json.dumps({"error": "No reviewable code changes found in this PR."})

            review_prompt = get_pr_review_prompt(diff_data)
            review_response = groq_client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert code reviewer. Be concise, specific, and actionable."},
                    {"role": "user", "content": review_prompt}
                ],
                max_tokens=1500
            )
            review_text = review_response.choices[0].message.content

            comment_url = None
            if post_as_comment:
                comment_result = post_review_comment(github_token, owner, repo, pr_number, review_text)
                if comment_result["success"]:
                    comment_url = comment_result["comment_url"]

            return json.dumps({
                "success": True,
                "pr_title": diff_data["pr_title"],
                "pr_url": diff_data["pr_url"],
                "files_reviewed": diff_data["reviewable_files"],
                "review": review_text,
                "comment_url": comment_url
            })

        # ── README Generator ───────────────────────────────────────────
        elif tool_name == "generate_readme":
            owner = tool_args.get("owner", github_username)
            repo = tool_args["repo"]

            # Read ALL repo files
            files_data = get_repo_files_content(github_token, owner, repo)
            if not files_data["success"]:
                return json.dumps({"error": files_data["error"]})
            if not files_data["files"]:
                return json.dumps({"error": "No files found in this repo to analyze."})

            # Generate README with AI
            readme_prompt = build_readme_prompt(owner, repo, files_data)
            readme_response = groq_client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional technical writer. Generate complete, accurate, detailed README files based on actual code. Cover ALL files in the repo."},
                    {"role": "user", "content": readme_prompt}
                ],
                max_tokens=3000
            )
            readme_content = readme_response.choices[0].message.content

            # Always save to repo automatically
            saved_url = None
            save_result = create_or_update_file(
                github_token, owner, repo,
                "README.md", readme_content,
                "Generate professional README.md with AI", "main"
            )
            if save_result.get("success"):
                saved_url = save_result.get("url")

            # Return the full README content so agent displays it
            return json.dumps({
                "success": True,
                "files_analyzed": len(files_data["files"]),
                "files_list": [f["path"] for f in files_data["files"]],
                "readme_content": readme_content,  # agent will display this
                "saved_url": saved_url
            })

        # ── Test Generator ─────────────────────────────────────────────
        elif tool_name == "generate_tests":
            owner = tool_args.get("owner", github_username)
            repo = tool_args["repo"]
            file_path = tool_args["file_path"]
            save_to_repo = tool_args.get("save_to_repo", False)
            branch = tool_args.get("branch", "main")

            file_result = get_file(github_token, owner, repo, file_path, branch)
            if not file_result.get("success"):
                return json.dumps({"error": f"Could not read {file_path}: {file_result.get('error')}"})

            file_content = file_result.get("content", "")
            language = detect_language(file_path)
            test_file_path = get_test_file_path(file_path, language)

            test_prompt = build_test_prompt(file_path, file_content, language)
            test_response = groq_client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert software engineer specializing in writing comprehensive unit tests. Generate only code, no explanations."},
                    {"role": "user", "content": test_prompt}
                ],
                max_tokens=2000
            )
            test_content = test_response.choices[0].message.content

            # Clean up markdown code blocks if present
            if "```" in test_content:
                lines = test_content.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                test_content = "\n".join(lines)

            saved_url = None
            if save_to_repo:
                result = create_or_update_file(
                    github_token, owner, repo,
                    test_file_path, test_content,
                    f"Generate unit tests for {file_path}", branch
                )
                if result.get("success"):
                    saved_url = result.get("url")

            return json.dumps({
                "success": True,
                "test_file": test_file_path,
                "language": language,
                "tests": test_content,
                "saved_url": saved_url
            })

        # ── All other tools ────────────────────────────────────────────
        # Fix: Groq returns booleans as strings "true"/"false" — convert them
        for key in ["private", "auto_init"]:
            if key in tool_args and isinstance(tool_args[key], str):
                tool_args[key] = tool_args[key].lower() == "true"

        TOOL_MAP = {
            "create_repo": lambda: create_repo(github_token, **tool_args),
            "delete_repo": lambda: delete_repo(github_token, **tool_args),
            "list_repos": lambda: list_repos(github_token, tool_args.get("username", github_username)),
            "get_repo": lambda: get_repo(github_token, **tool_args),
            "fork_repo": lambda: fork_repo(github_token, **tool_args),
            "get_file": lambda: get_file(github_token, **tool_args),
            "create_or_update_file": lambda: create_or_update_file(github_token, **tool_args),
            "delete_file": lambda: delete_file(github_token, **tool_args),
            "list_files": lambda: list_files(github_token, **tool_args),
            "list_commits": lambda: list_commits(github_token, **tool_args),
            "get_file_preview": lambda: get_file_preview(github_token, **tool_args),
            "edit_lines": lambda: edit_lines(github_token, **tool_args),
            "insert_lines": lambda: insert_lines(github_token, **tool_args),
            "delete_lines": lambda: delete_lines(github_token, **tool_args),
            "find_and_replace": lambda: find_and_replace(github_token, **tool_args),
            "append_to_file": lambda: append_to_file(github_token, **tool_args),
            "list_branches": lambda: list_branches(github_token, **tool_args),
            "create_branch": lambda: create_branch(github_token, **tool_args),
            "delete_branch": lambda: delete_branch(github_token, **tool_args),
            "merge_branches": lambda: merge_branches(github_token, **tool_args),
            "create_pull_request": lambda: create_pull_request(github_token, **tool_args),
            "list_pull_requests": lambda: list_pull_requests(github_token, **tool_args),
            "merge_pull_request": lambda: merge_pull_request(github_token, **tool_args),
            "close_pull_request": lambda: close_pull_request(github_token, **tool_args),
            "add_pr_comment": lambda: add_pr_comment(github_token, **tool_args),
            "create_issue": lambda: create_issue(github_token, **tool_args),
            "list_issues": lambda: list_issues(github_token, **tool_args),
            "close_issue": lambda: close_issue(github_token, **tool_args),
            "add_issue_comment": lambda: add_issue_comment(github_token, **tool_args),
            "add_labels": lambda: add_labels(github_token, **tool_args),
            "search_repos": lambda: search_repos(github_token, **tool_args),
            "search_code": lambda: search_code(github_token, **tool_args),
            "get_repo_summary": lambda: get_repo_summary(github_token, **tool_args),
            "get_user_profile": lambda: get_user_profile(github_token, **tool_args),
        }
        if tool_name in TOOL_MAP:
            return json.dumps(TOOL_MAP[tool_name]())
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


def create_agent_session(groq_api_key: str, github_token: str, github_username: str, history: list = None):
    client = Groq(api_key=groq_api_key)

    system_prompt = f"""You are a GitHub assistant agent for user: {github_username}

Guidelines:
- Use "{github_username}" as owner when not specified.
- Remember everything created in this conversation.
- Execute multi-step tasks automatically without asking for confirmation unless destructive.
- For action confirmations keep responses SHORT — one line + link.
- For content generation (README, docs, code, tests) write FULL detailed content.
- When someone asks for a repo link, just return https://github.com/{github_username}/REPONAME directly without calling any tool.
- When editing files use smart tools: find_and_replace, edit_lines, append_to_file. Only use create_or_update_file to rewrite entire files.
- Use get_file_preview before editing large files.
- For PR reviews use review_pull_request tool and display the full review text.
- For generating README use generate_readme tool. After it runs, display the FULL readme_content field from the result in your response. Then say it was saved to the repo.
- For generating tests use generate_tests tool and display the full tests content.
- ONLY answer GitHub related questions. If asked anything unrelated to GitHub say: "I can only help with GitHub-related tasks. Try asking me to create a repo, manage branches, review PRs, generate README, or generate tests!"
- If something fails, explain why and suggest what to do.
"""

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)

    return {
        "client": client,
        "github_token": github_token,
        "github_username": github_username,
        "messages": messages
    }


def chat_with_agent(session: dict, user_message: str) -> tuple[str, list]:
    client = session["client"]
    github_token = session["github_token"]
    github_username = session["github_username"]
    messages = session["messages"]

    messages.append({"role": "user", "content": user_message})
    tool_calls_made = []
    max_iterations = 10

    for _ in range(max_iterations):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                max_tokens=4096
            )

            message = response.choices[0].message
            assistant_msg = {"role": "assistant", "content": message.content or ""}
            if message.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in message.tool_calls
                ]
            messages.append(assistant_msg)

            if not message.tool_calls:
                return message.content or "✅ Done.", tool_calls_made

            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps({"error": "Invalid arguments. Please try again."})
                    })
                    continue

                tool_calls_made.append({"tool": tool_name, "input": tool_args})
                result = execute_tool(tool_name, tool_args, github_token, github_username, groq_client=client)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result
                })

        except Exception as e:
            error_msg = str(e)
            if "tool_use_failed" in error_msg:
                if messages and messages[-1].get("role") == "assistant":
                    messages.pop()
                if messages and messages[-1].get("role") == "user":
                    messages[-1] = {"role": "user", "content": f"Please do this carefully: {user_message}"}
                continue
            return f"❌ Error: {error_msg}", tool_calls_made

    return "❌ Could not complete the request. Please try rephrasing.", tool_calls_made