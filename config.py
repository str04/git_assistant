import os
from dotenv import load_dotenv

load_dotenv()

# Try .env first, then Streamlit secrets, then empty
def get_secret(key: str) -> str:
    # First try environment variable / .env
    value = os.getenv(key, "")
    if value:
        return value
    # Then try Streamlit secrets (for deployed app)
    try:
        import streamlit as st
        return st.secrets.get(key, "")
    except Exception:
        return ""

GROQ_API_KEY = get_secret("GROQ_API_KEY")
MODEL = "llama-3.3-70b-versatile"  # Free, fast, excellent

GITHUB_API = "https://api.github.com"

def get_github_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }