import requests
import base64
from config import GITHUB_API, get_github_headers


def get_file(token: str, owner: str, repo: str, path: str, branch: str = "main"):
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        params={"ref": branch},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 200:
        content = base64.b64decode(data["content"]).decode("utf-8")
        return {"success": True, "content": content, "sha": data["sha"]}
    return {"success": False, "error": data.get("message", "File not found")}


def create_or_update_file(token: str, owner: str, repo: str, path: str, content: str, message: str, branch: str = "main"):
    encoded = base64.b64encode(content.encode()).decode()
    existing = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        params={"ref": branch},
        headers=get_github_headers(token)
    )
    payload = {"message": message, "content": encoded, "branch": branch}
    if existing.status_code == 200:
        payload["sha"] = existing.json()["sha"]
    response = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        json=payload,
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code in [200, 201]:
        return {"success": True, "url": data["content"]["html_url"]}
    return {"success": False, "error": data.get("message", "Unknown error")}


def delete_file(token: str, owner: str, repo: str, path: str, message: str, branch: str = "main"):
    existing = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        params={"ref": branch},
        headers=get_github_headers(token)
    )
    if existing.status_code != 200:
        return {"success": False, "error": "File not found"}
    sha = existing.json()["sha"]
    response = requests.delete(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        json={"message": message, "sha": sha, "branch": branch},
        headers=get_github_headers(token)
    )
    if response.status_code == 200:
        return {"success": True, "message": f"{path} deleted."}
    return {"success": False, "error": response.json().get("message", "Unknown error")}


def list_files(token: str, owner: str, repo: str, path: str = "", branch: str = "main"):
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
        params={"ref": branch},
        headers=get_github_headers(token)
    )
    data = response.json()
    if isinstance(data, list):
        return [{"name": f["name"], "type": f["type"], "path": f["path"]} for f in data]
    return {"error": data.get("message", "Unknown error")}


def list_commits(token: str, owner: str, repo: str, branch: str = "main", limit: int = 10):
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits",
        params={"sha": branch, "per_page": limit},
        headers=get_github_headers(token)
    )
    commits = response.json()
    if isinstance(commits, list):
        return [{"sha": c["sha"][:7], "message": c["commit"]["message"], "author": c["commit"]["author"]["name"]} for c in commits]
    return {"error": commits.get("message", "Unknown error")}
