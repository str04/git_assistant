import requests
from config import GITHUB_API, get_github_headers


def create_pull_request(token: str, owner: str, repo: str, title: str, body: str, head: str, base: str = "main"):
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        json={"title": title, "body": body, "head": head, "base": base},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 201:
        return {"success": True, "url": data["html_url"], "number": data["number"]}
    return {"success": False, "error": data.get("message", "Unknown error")}


def list_pull_requests(token: str, owner: str, repo: str, state: str = "open"):
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
        params={"state": state, "per_page": 10},
        headers=get_github_headers(token)
    )
    prs = response.json()
    if isinstance(prs, list):
        return [{"number": pr["number"], "title": pr["title"], "state": pr["state"], "url": pr["html_url"], "author": pr["user"]["login"]} for pr in prs]
    return {"error": prs.get("message", "Unknown error")}


def merge_pull_request(token: str, owner: str, repo: str, pr_number: int, merge_method: str = "merge"):
    response = requests.put(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/merge",
        json={"merge_method": merge_method},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 200:
        return {"success": True, "message": data.get("message", "PR merged")}
    return {"success": False, "error": data.get("message", "Unknown error")}


def close_pull_request(token: str, owner: str, repo: str, pr_number: int):
    response = requests.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
        json={"state": "closed"},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 200:
        return {"success": True, "message": f"PR #{pr_number} closed."}
    return {"success": False, "error": data.get("message", "Unknown error")}


def add_pr_comment(token: str, owner: str, repo: str, pr_number: int, comment: str):
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments",
        json={"body": comment},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 201:
        return {"success": True, "url": data["html_url"]}
    return {"success": False, "error": data.get("message", "Unknown error")}
