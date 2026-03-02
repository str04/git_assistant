import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
from groq import Groq

from config import MODEL

from tools.repos import create_repo, delete_repo, list_repos, get_repo, fork_repo
from tools.files import get_file, create_or_update_file, delete_file, list_files, list_commits
from tools.branches import list_branches, create_branch, delete_branch, merge_branches
from tools.pulls import create_pull_request, list_pull_requests, merge_pull_request, close_pull_request, add_pr_comment
from tools.issues import create_issue, list_issues, close_issue, add_issue_comment, add_labels
from tools.search import search_repos, search_code, get_repo_summary, get_user_profile
from tools.file_editor import (
    edit_lines, insert_lines, delete_lines, find_and_replace,
    get_file_preview, append_to_file
)
from tools.pr_review import get_pr_diff, get_pr_review_prompt, post_review_comment
from tools.ai_generator import (
    get_repo_files_content, build_readme_prompt,
    build_test_prompt, detect_language, get_test_file_path
)

# ── Tool definitions ───────────────────────────────────────────────────
TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "list_repos", "description": "List repositories for the authenticated user.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "create_repo", "description": "Create a new GitHub repository under the authenticated user.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "private": {"type": "boolean"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "delete_repo", "description": "Delete a repository. Destructive.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "get_repo", "description": "Get details about a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "fork_repo", "description": "Fork a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},

    {"type": "function", "function": {"name": "list_files", "description": "List files in a repository path.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "get_file", "description": "Get file content.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path"]}}},
    {"type": "function", "function": {"name": "create_or_update_file", "description": "Create or update a file.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "content": {"type": "string"}, "message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "content", "message"]}}},
    {"type": "function", "function": {"name": "delete_file", "description": "Delete a file. Destructive.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "message": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "path", "message"]}}},
    {"type": "function", "function": {"name": "list_commits", "description": "List commits for a repository.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo"]}}},

    {"type": "function", "function": {"name": "list_branches", "description": "List branches.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "create_branch", "description": "Create a new branch.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "new_branch": {"type": "string"}, "from_branch": {"type": "string"}}, "required": ["owner", "repo", "new_branch"]}}},
    {"type": "function", "function": {"name": "delete_branch", "description": "Delete a branch. Destructive.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "branch": {"type": "string"}}, "required": ["owner", "repo", "branch"]}}},
    {"type": "function", "function": {"name": "merge_branches", "description": "Merge branches.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "base": {"type": "string"}, "head": {"type": "string"}}, "required": ["owner", "repo", "base", "head"]}}},

    {"type": "function", "function": {"name": "list_pull_requests", "description": "List PRs.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "state": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "create_pull_request", "description": "Create PR.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "title": {"type": "string"}, "head": {"type": "string"}, "base": {"type": "string"}, "body": {"type": "string"}}, "required": ["owner", "repo", "title", "head", "base"]}}},
    {"type": "function", "function": {"name": "merge_pull_request", "description": "Merge PR. Destructive.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "pull_number": {"type": "integer"}, "merge_method": {"type": "string"}}, "required": ["owner", "repo", "pull_number"]}}},
    {"type": "function", "function": {"name": "close_pull_request", "description": "Close PR.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "pull_number": {"type": "integer"}}, "required": ["owner", "repo", "pull_number"]}}},
    {"type": "function", "function": {"name": "add_pr_comment", "description": "Add PR comment.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "pull_number": {"type": "integer"}, "body": {"type": "string"}}, "required": ["owner", "repo", "pull_number", "body"]}}},

    {"type": "function", "function": {"name": "list_issues", "description": "List issues.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "state": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "create_issue", "description": "Create issue.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, "required": ["owner", "repo", "title"]}}},
    {"type": "function", "function": {"name": "close_issue", "description": "Close issue.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "issue_number": {"type": "integer"}}, "required": ["owner", "repo", "issue_number"]}}},
    {"type": "function", "function": {"name": "add_issue_comment", "description": "Add issue comment.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "issue_number": {"type": "integer"}, "body": {"type": "string"}}, "required": ["owner", "repo", "issue_number", "body"]}}},
    {"type": "function", "function": {"name": "add_labels", "description": "Add labels to issue/PR.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "issue_number": {"type": "integer"}, "labels": {"type": "array", "items": {"type": "string"}}}, "required": ["owner", "repo", "issue_number", "labels"]}}},

    {"type": "function", "function": {"name": "search_repos", "description": "Search repositories.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_code", "description": "Search code.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_repo_summary", "description": "Get repo summary.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}}, "required": ["owner", "repo"]}}},
    {"type": "function", "function": {"name": "get_user_profile", "description": "Get user profile.", "parameters": {"type": "object", "properties": {"username": {"type": "string"}}, "required": ["username"]}}},

    {"type": "function", "function": {"name": "get_file_preview", "description": "Get file preview (first N lines).", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "branch": {"type": "string"}, "lines": {"type": "integer"}}, "required": ["owner", "repo", "path"]}}},
    {"type": "function", "function": {"name": "edit_lines", "description": "Edit specific line range.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}, "new_text": {"type": "string"}, "branch": {"type": "string"}, "message": {"type": "string"}}, "required": ["owner", "repo", "path", "start_line", "end_line", "new_text", "message"]}}},
    {"type": "function", "function": {"name": "insert_lines", "description": "Insert lines at a position.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "line_number": {"type": "integer"}, "text": {"type": "string"}, "branch": {"type": "string"}, "message": {"type": "string"}}, "required": ["owner", "repo", "path", "line_number", "text", "message"]}}},
    {"type": "function", "function": {"name": "delete_lines", "description": "Delete line range.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}, "branch": {"type": "string"}, "message": {"type": "string"}}, "required": ["owner", "repo", "path", "start_line", "end_line", "message"]}}},

    {"type": "function", "function": {"name": "find_and_replace", "description": "Find and replace text in file.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "find": {"type": "string"}, "replace": {"type": "string"}, "branch": {"type": "string"}, "message": {"type": "string"}}, "required": ["owner", "repo", "path", "find", "replace", "message"]}}},
    {"type": "function", "function": {"name": "append_to_file", "description": "Append text to a file.", "parameters": {"type": "object", "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}, "path": {"type": "string"}, "text": {"type": "string"}, "branch": {"type": "string"}, "message": {"type": "string"}}, "required": ["owner", "repo", "path", "text", "message"]}}},

    {"type": "function", "function": {"name": "review_pull_request", "description": "Review PR and optionally post comment.", "parameters": {"type": "object", "properties": {"repo": {"type": "string"}, "pull_number": {"type": "integer"}, "post_comment": {"type": "boolean"}}, "required": ["repo", "pull_number"]}}},
    {"type": "function", "function": {"name": "generate_readme", "description": "Generate README and save to repo.", "parameters": {"type": "object", "properties": {"repo": {"type": "string"}, "branch": {"type": "string"}}, "required": ["repo"]}}},
    {"type": "function", "function": {"name": "generate_tests", "description": "Generate tests for repo and save to repo.", "parameters": {"type": "object", "properties": {"repo": {"type": "string"}, "branch": {"type": "string"}}, "required": ["repo"]}}},
]

def execute_tool(tool_name: str, args: dict, github_token: str, github_username: str, groq_client=None) -> str:
    owner = args.get("owner") or github_username

    try:
        # ---- repos ----
        if tool_name == "list_repos":
            return json.dumps(list_repos(github_token))

        if tool_name == "create_repo":
            return json.dumps(create_repo(github_token, args["name"], args.get("private", False)))

        if tool_name == "delete_repo":
            return json.dumps(delete_repo(github_token, owner, args["repo"]))

        if tool_name == "get_repo":
            return json.dumps(get_repo(github_token, owner, args["repo"]))

        if tool_name == "fork_repo":
            return json.dumps(fork_repo(github_token, owner, args["repo"]))

        # ---- files ----
        if tool_name == "list_files":
            return json.dumps(list_files(github_token, owner, args["repo"], args.get("path", ""), args.get("branch")))

        if tool_name == "get_file":
            return json.dumps(get_file(github_token, owner, args["repo"], args["path"], args.get("branch")))

        if tool_name == "create_or_update_file":
            return json.dumps(create_or_update_file(
                github_token, owner, args["repo"], args["path"], args["content"], args["message"], args.get("branch")
            ))

        if tool_name == "delete_file":
            return json.dumps(delete_file(
                github_token, owner, args["repo"], args["path"], args["message"], args.get("branch")
            ))

        if tool_name == "list_commits":
            return json.dumps(list_commits(github_token, owner, args["repo"], args.get("branch")))

        # ---- branches ----
        if tool_name == "list_branches":
            return json.dumps(list_branches(github_token, owner, args["repo"]))

        if tool_name == "create_branch":
            return json.dumps(create_branch(
                github_token, owner, args["repo"], args["new_branch"], args.get("from_branch", "main")
            ))

        if tool_name == "delete_branch":
            return json.dumps(delete_branch(github_token, owner, args["repo"], args["branch"]))

        if tool_name == "merge_branches":
            return json.dumps(merge_branches(github_token, owner, args["repo"], args["base"], args["head"]))

        # ---- pulls ----
        if tool_name == "list_pull_requests":
            return json.dumps(list_pull_requests(github_token, owner, args["repo"], args.get("state", "open")))

        if tool_name == "create_pull_request":
            return json.dumps(create_pull_request(
                github_token, owner, args["repo"], args["title"], args["head"], args["base"], args.get("body", "")
            ))

        if tool_name == "merge_pull_request":
            return json.dumps(merge_pull_request(
                github_token, owner, args["repo"], args["pull_number"], args.get("merge_method", "merge")
            ))

        if tool_name == "close_pull_request":
            return json.dumps(close_pull_request(github_token, owner, args["repo"], args["pull_number"]))

        if tool_name == "add_pr_comment":
            return json.dumps(add_pr_comment(github_token, owner, args["repo"], args["pull_number"], args["body"]))

        # ---- issues ----
        if tool_name == "list_issues":
            return json.dumps(list_issues(github_token, owner, args["repo"], args.get("state", "open")))

        if tool_name == "create_issue":
            return json.dumps(create_issue(github_token, owner, args["repo"], args["title"], args.get("body", "")))

        if tool_name == "close_issue":
            return json.dumps(close_issue(github_token, owner, args["repo"], args["issue_number"]))

        if tool_name == "add_issue_comment":
            return json.dumps(add_issue_comment(github_token, owner, args["repo"], args["issue_number"], args["body"]))

        if tool_name == "add_labels":
            return json.dumps(add_labels(github_token, owner, args["repo"], args["issue_number"], args["labels"]))

        # ---- search / info ----
        if tool_name == "search_repos":
            return json.dumps(search_repos(github_token, args["query"]))

        if tool_name == "search_code":
            return json.dumps(search_code(github_token, args["query"]))

        if tool_name == "get_repo_summary":
            return json.dumps(get_repo_summary(github_token, owner, args["repo"]))

        if tool_name == "get_user_profile":
            return json.dumps(get_user_profile(github_token, args["username"]))

        # ---- file editor ----
        if tool_name == "get_file_preview":
            return json.dumps(get_file_preview(
                github_token, owner, args["repo"], args["path"], args.get("branch"), args.get("lines", 80)
            ))

        if tool_name == "edit_lines":
            return json.dumps(edit_lines(
                github_token, owner, args["repo"], args["path"],
                args["start_line"], args["end_line"], args["new_text"],
                args.get("branch"), args["message"]
            ))

        if tool_name == "insert_lines":
            return json.dumps(insert_lines(
                github_token, owner, args["repo"], args["path"],
                args["line_number"], args["text"],
                args.get("branch"), args["message"]
            ))

        if tool_name == "delete_lines":
            return json.dumps(delete_lines(
                github_token, owner, args["repo"], args["path"],
                args["start_line"], args["end_line"],
                args.get("branch"), args["message"]
            ))

        if tool_name == "find_and_replace":
            return json.dumps(find_and_replace(
                github_token, owner, args["repo"], args["path"],
                args["find"], args["replace"],
                args.get("branch"), args["message"]
            ))

        if tool_name == "append_to_file":
            return json.dumps(append_to_file(
                github_token, owner, args["repo"], args["path"],
                args["text"], args.get("branch"), args["message"]
            ))

        # ---- AI tools ----
        if tool_name == "generate_readme":
            repo = args["repo"]
            branch = args.get("branch") or "main"
            files = get_repo_files_content(
                github_token, owner, repo, branch=branch, max_files=30, max_chars=120000
            )
            prompt = build_readme_prompt(owner, repo, files)
            if groq_client is None:
                return json.dumps({"error": "LLM client missing"})

            out = groq_client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096
            )
            readme = out.choices[0].message.content or ""
            res = create_or_update_file(
                github_token, owner, repo, "README.md", readme, "Add README.md", branch
            )
            return json.dumps({"readme_content": readme, "save_result": res})

        if tool_name == "generate_tests":
            repo = args["repo"]
            branch = args.get("branch") or "main"
            files = get_repo_files_content(
                github_token, owner, repo, branch=branch, max_files=30, max_chars=120000
            )
            lang = detect_language(files)
            prompt = build_test_prompt(owner, repo, files, lang)

            if groq_client is None:
                return json.dumps({"error": "LLM client missing"})

            out = groq_client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096
            )
            tests = out.choices[0].message.content or ""
            test_path = get_test_file_path(lang)
            res = create_or_update_file(
                github_token, owner, repo, test_path, tests, f"Add tests: {test_path}", branch
            )
            return json.dumps({"tests_content": tests, "test_path": test_path, "save_result": res})

        if tool_name == "review_pull_request":
            repo = args["repo"]
            pull_number = args["pull_number"]
            post_comment_flag = bool(args.get("post_comment", False))

            diff = get_pr_diff(github_token, owner, repo, pull_number)
            prompt = get_pr_review_prompt(owner, repo, pull_number, diff)

            if groq_client is None:
                return json.dumps({"error": "LLM client missing"})

            out = groq_client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096
            )
            review = out.choices[0].message.content or ""
            posted = None
            if post_comment_flag:
                posted = post_review_comment(github_token, owner, repo, pull_number, review)

            return json.dumps({"review_text": review, "posted_comment": posted})

        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


def create_agent_session(groq_api_key: str, github_token: str, github_username: str, history: list = None):
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Set it in config.py or environment variables.")

    client = Groq(api_key=groq_api_key)

    system_prompt = f"""You are a GitHub assistant agent for user: {github_username}

Rules:
- Only do GitHub-related tasks (repos, branches, PRs, issues, files, README, tests).
- If asked anything unrelated to GitHub, respond exactly:
  "I can only help with GitHub-related tasks. Try asking me to create a repo, manage branches, review PRs, generate README, or generate tests!"
- Use "{github_username}" as owner when not specified.
- Execute multi-step GitHub tasks automatically unless destructive.
- For destructive actions, ask for confirmation before calling the tool.
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
                        "content": json.dumps({"error": "Invalid tool arguments JSON."})
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
            return f"❌ Error: {str(e)}", tool_calls_made

    return "❌ Could not complete the request. Please try rephrasing.", tool_calls_made