"""
Tiny sanity test for the key vault. Runs without Mongo or FastAPI.

Usage:
    python -m tests.sanity
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    # Generate a one-shot key for the test so we don't depend on the env.
    os.environ["KEY_VAULT_SECRET"] = base64.b64encode(os.urandom(32)).decode()

    from keyvault import encrypt, decrypt, mask  # noqa: E402

    sample = "AIzaSyXXXXXXXXXXXXXXXXXXXXXXXX_8tU"
    encrypted = encrypt(sample)
    assert encrypted.startswith("v1:"), encrypted
    assert sample not in encrypted, "plaintext leaked into payload!"

    decrypted = decrypt(encrypted)
    assert decrypted == sample, decrypted

    masked = mask(encrypted)
    assert masked is not None and "••••••" in masked, masked
    assert sample not in masked, "plaintext leaked into mask!"

    print("ok — encrypt/decrypt round-trip works, mask hides the plaintext.")
    print(f"  encrypted len = {len(encrypted)}")
    print(f"  mask          = {masked}")


if __name__ == "__main__":
    main()
