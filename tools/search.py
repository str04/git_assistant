import requests
from config import GITHUB_API, get_github_headers


def search_repos(token: str, query: str, language: str = "", sort: str = "stars", limit: int = 5):
    q = query
    if language:
        q += f" language:{language}"
    response = requests.get(
        f"{GITHUB_API}/search/repositories",
        params={"q": q, "sort": sort, "per_page": limit},
        headers=get_github_headers(token)
    )
    data = response.json()
    if "items" in data:
        return [{"name": r["full_name"], "url": r["html_url"], "stars": r["stargazers_count"], "description": r["description"]} for r in data["items"]]
    return {"error": data.get("message", "Unknown error")}


def search_code(token: str, query: str, owner: str = "", repo: str = ""):
    q = query
    if owner and repo:
        q += f" repo:{owner}/{repo}"
    elif owner:
        q += f" user:{owner}"
    response = requests.get(
        f"{GITHUB_API}/search/code",
        params={"q": q, "per_page": 5},
        headers=get_github_headers(token)
    )
    data = response.json()
    if "items" in data:
        return [{"file": i["path"], "repo": i["repository"]["full_name"], "url": i["html_url"]} for i in data["items"]]
    return {"error": data.get("message", "Unknown error")}


def get_repo_summary(token: str, owner: str, repo: str):
    headers = get_github_headers(token)
    repo_resp = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=headers).json()
    lang_resp = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/languages", headers=headers).json()
    contrib_resp = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/contributors?per_page=5", headers=headers).json()
    commits_resp = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}/commits?per_page=3", headers=headers).json()
    return {
        "name": repo_resp.get("full_name"),
        "description": repo_resp.get("description"),
        "stars": repo_resp.get("stargazers_count"),
        "forks": repo_resp.get("forks_count"),
        "open_issues": repo_resp.get("open_issues_count"),
        "languages": list(lang_resp.keys()) if isinstance(lang_resp, dict) else [],
        "top_contributors": [c["login"] for c in contrib_resp] if isinstance(contrib_resp, list) else [],
        "recent_commits": [c["commit"]["message"][:60] for c in commits_resp] if isinstance(commits_resp, list) else []
    }


def get_user_profile(token: str, username: str):
    response = requests.get(f"{GITHUB_API}/users/{username}", headers=get_github_headers(token))
    data = response.json()
    if response.status_code == 200:
        return {
            "username": data["login"],
            "name": data.get("name"),
            "bio": data.get("bio"),
            "public_repos": data["public_repos"],
            "followers": data["followers"],
            "url": data["html_url"]
        }
    return {"error": data.get("message", "Unknown error")}
