import requests
from config import GITHUB_API, get_github_headers


def list_branches(token: str, owner: str, repo: str):
    response = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/branches", headers=get_github_headers(token))
    branches = response.json()
    if isinstance(branches, list):
        return [b["name"] for b in branches]
    return {"error": branches.get("message", "Unknown error")}


def create_branch(token: str, owner: str, repo: str, branch_name: str, from_branch: str = "main"):
    ref_response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{from_branch}",
        headers=get_github_headers(token)
    )
    if ref_response.status_code != 200:
        return {"success": False, "error": f"Source branch '{from_branch}' not found"}
    sha = ref_response.json()["object"]["sha"]
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
        json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 201:
        return {"success": True, "branch": branch_name, "from": from_branch}
    return {"success": False, "error": data.get("message", "Unknown error")}


def delete_branch(token: str, owner: str, repo: str, branch_name: str):
    response = requests.delete(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/refs/heads/{branch_name}",
        headers=get_github_headers(token)
    )
    if response.status_code == 204:
        return {"success": True, "message": f"Branch '{branch_name}' deleted."}
    return {"success": False, "error": response.json().get("message", "Unknown error")}


def merge_branches(token: str, owner: str, repo: str, base: str, head: str, commit_message: str = ""):
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/merges",
        json={"base": base, "head": head, "commit_message": commit_message or f"Merge {head} into {base}"},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code in [201, 204]:
        return {"success": True, "message": f"Merged {head} into {base}"}
    return {"success": False, "error": data.get("message", "Unknown error")}
