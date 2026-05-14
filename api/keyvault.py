"""
AES-256-GCM encryption for user-provided API keys.

Storage shape (str): "v1:<base64(nonce)>:<base64(ciphertext)>"
- v1 prefix lets us migrate to a new scheme later without breaking old rows.
- AES-GCM gives us authentication (tampering = decrypt fails).

KEY_VAULT_SECRET must be a base64-encoded 32-byte key. Generate once with:
    python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"

This key MUST match between the API and any other backend service that
needs to read the same row. Keep it out of git.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key() -> bytes:
    raw = os.environ.get("KEY_VAULT_SECRET")
    if not raw:
        raise RuntimeError("KEY_VAULT_SECRET is not set")
    decoded = base64.b64decode(raw)
    if len(decoded) != 32:
        raise RuntimeError("KEY_VAULT_SECRET must decode to exactly 32 bytes")
    return decoded


def encrypt(plaintext: str) -> str:
    aes = AESGCM(_key())
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return "v1:" + base64.b64encode(nonce).decode() + ":" + base64.b64encode(ct).decode()


def decrypt(payload: str) -> str:
    parts = payload.split(":", 2)
    if len(parts) != 3 or parts[0] != "v1":
        raise ValueError("Unsupported key vault payload format.")
    nonce = base64.b64decode(parts[1])
    ct = base64.b64decode(parts[2])
    aes = AESGCM(_key())
    return aes.decrypt(nonce, ct, associated_data=None).decode("utf-8")


def mask(payload: Optional[str]) -> Optional[str]:
    """
    Return a safe, non-decrypting preview for UI ("AIza••••••8tU"). Decrypts
    in-memory only to compute the mask; never returned in plaintext.
    """
    if not payload:
        return None
    try:
        plain = decrypt(payload)
    except Exception:
        return "•••• stored ••••"
    if len(plain) <= 8:
        return "•" * len(plain)
    return plain[:4] + "••••••" + plain[-3:]
