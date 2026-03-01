import requests
import base64
from config import GITHUB_API, get_github_headers


def get_file_content(token: str, owner: str, repo: str, path: str, branch: str = "main") -> dict:
    """Get file content and metadata."""
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        params={"ref": branch},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 200:
        content = base64.b64decode(data["content"]).decode("utf-8")
        return {"success": True, "content": content, "sha": data["sha"], "lines": content.splitlines()}
    return {"success": False, "error": data.get("message", "File not found")}


def edit_lines(token: str, owner: str, repo: str, path: str,
               start_line: int, end_line: int, new_content: str,
               commit_message: str, branch: str = "main") -> dict:
    """
    Edit specific lines in a file.
    start_line and end_line are 1-indexed.
    new_content replaces lines from start_line to end_line.
    """
    # Get current file
    file_data = get_file_content(token, owner, repo, path, branch)
    if not file_data["success"]:
        return {"success": False, "error": file_data["error"]}

    lines = file_data["lines"]
    total_lines = len(lines)

    # Validate line numbers
    if start_line < 1 or start_line > total_lines:
        return {"success": False, "error": f"start_line {start_line} is out of range (file has {total_lines} lines)"}
    if end_line < start_line or end_line > total_lines:
        end_line = min(end_line, total_lines)

    # Replace the lines
    new_lines = new_content.splitlines()
    updated = lines[:start_line - 1] + new_lines + lines[end_line:]
    updated_content = "\n".join(updated)

    # Commit back
    encoded = base64.b64encode(updated_content.encode()).decode()
    response = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        json={"message": commit_message, "content": encoded, "sha": file_data["sha"], "branch": branch},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code in [200, 201]:
        return {
            "success": True,
            "message": f"Edited lines {start_line}-{end_line} in {path}",
            "url": data["content"]["html_url"],
            "lines_changed": len(new_lines)
        }
    return {"success": False, "error": data.get("message", "Unknown error")}


def insert_lines(token: str, owner: str, repo: str, path: str,
                 after_line: int, new_content: str,
                 commit_message: str, branch: str = "main") -> dict:
    """
    Insert new lines after a specific line number.
    after_line=0 inserts at the top of the file.
    """
    file_data = get_file_content(token, owner, repo, path, branch)
    if not file_data["success"]:
        return {"success": False, "error": file_data["error"]}

    lines = file_data["lines"]
    new_lines = new_content.splitlines()
    updated = lines[:after_line] + new_lines + lines[after_line:]
    updated_content = "\n".join(updated)

    encoded = base64.b64encode(updated_content.encode()).decode()
    response = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        json={"message": commit_message, "content": encoded, "sha": file_data["sha"], "branch": branch},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code in [200, 201]:
        return {
            "success": True,
            "message": f"Inserted {len(new_lines)} lines after line {after_line} in {path}",
            "url": data["content"]["html_url"]
        }
    return {"success": False, "error": data.get("message", "Unknown error")}


def delete_lines(token: str, owner: str, repo: str, path: str,
                 start_line: int, end_line: int,
                 commit_message: str, branch: str = "main") -> dict:
    """Delete specific lines from a file."""
    file_data = get_file_content(token, owner, repo, path, branch)
    if not file_data["success"]:
        return {"success": False, "error": file_data["error"]}

    lines = file_data["lines"]
    updated = lines[:start_line - 1] + lines[end_line:]
    updated_content = "\n".join(updated)

    encoded = base64.b64encode(updated_content.encode()).decode()
    response = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        json={"message": commit_message, "content": encoded, "sha": file_data["sha"], "branch": branch},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code in [200, 201]:
        return {
            "success": True,
            "message": f"Deleted lines {start_line}-{end_line} from {path}",
            "url": data["content"]["html_url"]
        }
    return {"success": False, "error": data.get("message", "Unknown error")}


def find_and_replace(token: str, owner: str, repo: str, path: str,
                     find_text: str, replace_text: str,
                     commit_message: str, branch: str = "main") -> dict:
    """
    Find and replace text in a file.
    Replaces ALL occurrences.
    """
    file_data = get_file_content(token, owner, repo, path, branch)
    if not file_data["success"]:
        return {"success": False, "error": file_data["error"]}

    content = file_data["content"]
    count = content.count(find_text)

    if count == 0:
        return {"success": False, "error": f"Text '{find_text}' not found in {path}"}

    updated_content = content.replace(find_text, replace_text)
    encoded = base64.b64encode(updated_content.encode()).decode()

    response = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        json={"message": commit_message, "content": encoded, "sha": file_data["sha"], "branch": branch},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code in [200, 201]:
        return {
            "success": True,
            "message": f"Replaced {count} occurrence(s) of '{find_text}' with '{replace_text}' in {path}",
            "url": data["content"]["html_url"],
            "replacements": count
        }
    return {"success": False, "error": data.get("message", "Unknown error")}


def get_file_preview(token: str, owner: str, repo: str, path: str,
                     start_line: int = 1, end_line: int = 50,
                     branch: str = "main") -> dict:
    """
    Get a preview of specific lines from a file.
    Useful for viewing large files without loading everything.
    """
    file_data = get_file_content(token, owner, repo, path, branch)
    if not file_data["success"]:
        return {"success": False, "error": file_data["error"]}

    lines = file_data["lines"]
    total = len(lines)
    end_line = min(end_line, total)
    preview_lines = lines[start_line - 1:end_line]

    # Add line numbers for clarity
    numbered = [f"{i+start_line}: {line}" for i, line in enumerate(preview_lines)]

    return {
        "success": True,
        "preview": "\n".join(numbered),
        "total_lines": total,
        "showing": f"lines {start_line}-{end_line} of {total}"
    }


def append_to_file(token: str, owner: str, repo: str, path: str,
                   content_to_append: str, commit_message: str,
                   branch: str = "main") -> dict:
    """Append content to the end of a file."""
    file_data = get_file_content(token, owner, repo, path, branch)
    if not file_data["success"]:
        return {"success": False, "error": file_data["error"]}

    updated_content = file_data["content"].rstrip("\n") + "\n" + content_to_append
    encoded = base64.b64encode(updated_content.encode()).decode()

    response = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        json={"message": commit_message, "content": encoded, "sha": file_data["sha"], "branch": branch},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code in [200, 201]:
        return {
            "success": True,
            "message": f"Appended content to {path}",
            "url": data["content"]["html_url"]
        }
    return {"success": False, "error": data.get("message", "Unknown error")}