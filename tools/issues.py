import requests
from config import GITHUB_API, get_github_headers


def create_issue(token: str, owner: str, repo: str, title: str, body: str = "", labels: list = None):
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
        json={"title": title, "body": body, "labels": labels or []},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 201:
        return {"success": True, "url": data["html_url"], "number": data["number"]}
    return {"success": False, "error": data.get("message", "Unknown error")}


def list_issues(token: str, owner: str, repo: str, state: str = "open"):
    response = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": 15},
        headers=get_github_headers(token)
    )
    issues = response.json()
    if isinstance(issues, list):
        return [{"number": i["number"], "title": i["title"], "state": i["state"], "url": i["html_url"]} for i in issues if "pull_request" not in i]
    return {"error": issues.get("message", "Unknown error")}


def close_issue(token: str, owner: str, repo: str, issue_number: int):
    response = requests.patch(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}",
        json={"state": "closed"},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 200:
        return {"success": True, "message": f"Issue #{issue_number} closed."}
    return {"success": False, "error": data.get("message", "Unknown error")}


def add_issue_comment(token: str, owner: str, repo: str, issue_number: int, comment: str):
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/comments",
        json={"body": comment},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 201:
        return {"success": True, "url": data["html_url"]}
    return {"success": False, "error": data.get("message", "Unknown error")}


def add_labels(token: str, owner: str, repo: str, issue_number: int, labels: list):
    response = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/labels",
        json={"labels": labels},
        headers=get_github_headers(token)
    )
    data = response.json()
    if isinstance(data, list):
        return {"success": True, "labels": [l["name"] for l in data]}
    return {"success": False, "error": data.get("message", "Unknown error")}
