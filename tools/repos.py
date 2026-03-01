import requests
from config import GITHUB_API, get_github_headers


def create_repo(token: str, name: str, description: str = "", private: bool = False, auto_init: bool = True):
    response = requests.post(
        f"{GITHUB_API}/user/repos",
        json={"name": name, "description": description, "private": private, "auto_init": auto_init},
        headers=get_github_headers(token)
    )
    data = response.json()
    if response.status_code == 201:
        return {"success": True, "url": data["html_url"], "full_name": data["full_name"]}
    return {"success": False, "error": data.get("message", "Unknown error")}


def delete_repo(token: str, owner: str, repo: str):
    response = requests.delete(f"{GITHUB_API}/repos/{owner}/{repo}", headers=get_github_headers(token))
    if response.status_code == 204:
        return {"success": True, "message": f"Repo {owner}/{repo} deleted."}
    return {"success": False, "error": response.json().get("message", "Unknown error")}


def list_repos(token: str, username: str = ""):
    url = f"{GITHUB_API}/user/repos?per_page=20&sort=updated" if not username else f"{GITHUB_API}/users/{username}/repos?per_page=20&sort=updated"
    response = requests.get(url, headers=get_github_headers(token))
    repos = response.json()
    if isinstance(repos, list):
        return [{"name": r["name"], "url": r["html_url"], "private": r["private"], "description": r["description"]} for r in repos]
    return {"error": repos.get("message", "Unknown error")}


def get_repo(token: str, owner: str, repo: str):
    response = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=get_github_headers(token))
    data = response.json()
    if response.status_code == 200:
        return {
            "name": data["full_name"],
            "description": data["description"],
            "stars": data["stargazers_count"],
            "forks": data["forks_count"],
            "language": data["language"],
            "url": data["html_url"],
            "open_issues": data["open_issues_count"]
        }
    return {"error": data.get("message", "Unknown error")}


def fork_repo(token: str, owner: str, repo: str):
    response = requests.post(f"{GITHUB_API}/repos/{owner}/{repo}/forks", headers=get_github_headers(token))
    data = response.json()
    if response.status_code in [202, 200]:
        return {"success": True, "url": data["html_url"]}
    return {"success": False, "error": data.get("message", "Unknown error")}


def get_authenticated_user(token: str):
    response = requests.get(f"{GITHUB_API}/user", headers=get_github_headers(token))
    data = response.json()
    if response.status_code == 200:
        return {"login": data["login"], "name": data.get("name"), "url": data["html_url"]}
    return {"error": data.get("message", "Unknown error")}
