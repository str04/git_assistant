"""
security.py
============
Handles all security concerns:
- Token encryption/decryption for browser cookies
- Auto-generates encryption key if not set (for local dev)
- Secure user ID generation
"""

import os
import base64
import hashlib
import secrets


def get_or_create_fernet():
    """
    Get the Fernet encryption object.
    Uses ENCRYPT_KEY from secrets/env.
    Falls back to a session-level key for local dev (tokens won't persist across restarts).
    """
    try:
        from cryptography.fernet import Fernet
        from config import ENCRYPT_KEY

        if ENCRYPT_KEY:
            # Pad/hash the key to exactly 32 bytes then base64 encode for Fernet
            key_bytes = hashlib.sha256(ENCRYPT_KEY.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            return Fernet(fernet_key)
        else:
            # No key configured — generate one for this session
            # Tokens will work but won't survive app restarts
            if not hasattr(get_or_create_fernet, "_session_key"):
                get_or_create_fernet._session_key = Fernet.generate_key()
            return Fernet(get_or_create_fernet._session_key)

    except ImportError:
        return None


def encrypt_token(token: str) -> str:
    """
    Encrypt a GitHub token for safe storage in browser cookie.
    Returns base64-encoded encrypted string.
    Falls back to plain token if cryptography not installed.
    """
    f = get_or_create_fernet()
    if f is None or not token:
        return token
    try:
        encrypted = f.encrypt(token.encode())
        return encrypted.decode()
    except Exception:
        return token


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a token from browser cookie.
    Returns empty string if decryption fails (token invalid/expired).
    """
    if not encrypted_token:
        return ""

    f = get_or_create_fernet()
    if f is None:
        return encrypted_token

    try:
        decrypted = f.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except Exception:
        # Decryption failed — token tampered with or from old key
        return ""


def get_user_id(github_token: str) -> str:
    """
    Create a secure, consistent user ID from a GitHub token.
    Uses SHA-256 — same token always produces same ID,
    but ID cannot be reversed to get the token.
    """
    return hashlib.sha256(github_token.encode()).hexdigest()[:16]


def is_token_format_valid(token: str) -> bool:
    """
    Quick sanity check on token format before hitting GitHub API.
    GitHub tokens start with ghp_, gho_, ghs_, ghr_, or github_pat_
    """
    if not token:
        return False
    valid_prefixes = ("ghp_", "gho_", "ghs_", "ghr_", "github_pat_")
    return any(token.startswith(p) for p in valid_prefixes)