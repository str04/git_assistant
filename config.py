import os
from dotenv import load_dotenv

load_dotenv()

def get_secret(key: str) -> str:
    value = os.getenv(key, "")
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(key, "")
    except Exception:
        return ""

GROQ_API_KEY  = get_secret("GROQ_API_KEY")
ENCRYPT_KEY   = get_secret("ENCRYPT_KEY")   # 32-byte Fernet key for cookie encryption
MODEL         = "llama-3.3-70b-versatile"
GITHUB_API    = "https://api.github.com"

def get_github_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }