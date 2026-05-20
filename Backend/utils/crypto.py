"""utils/crypto.py — Symmetric encryption for PII at rest."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

logger = logging.getLogger(__name__)


def _derive_dev_key(secret: str) -> bytes:
    """SHA-256(secret) -> 32 bytes -> urlsafe-b64 -> Fernet key. Dev only."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _is_valid_fernet_key(key: bytes) -> bool:
    """A Fernet key is exactly 32 bytes URL-safe-base64-encoded."""
    try:
        Fernet(key)
        return True
    except Exception:
        return False


def _load_keys() -> list[bytes]:
    """
    Load Fernet keys in priority order.

    1. PII_ENCRYPTION_KEYS — comma-separated, first is the write key.
    2. PII_ENCRYPTION_KEY  — single key.
    3. SECRET_KEY / JWT_SECRET — derive a key (dev only, warns).

    If the configured PII_ENCRYPTION_KEY is set but isn't a valid Fernet
    key (typically a placeholder leftover from .env.example), we don't
    hard-fail — we log a warning and derive a dev-only key from
    SECRET_KEY/JWT_SECRET. That keeps the dev boot path frictionless.
    """
    multi = os.getenv("PII_ENCRYPTION_KEYS", "").strip()
    if multi:
        keys = [k.strip().encode() for k in multi.split(",") if k.strip()]
        if all(_is_valid_fernet_key(k) for k in keys):
            return keys
        logger.warning(
            "PII_ENCRYPTION_KEYS is set but contains an invalid Fernet key. "
            "Falling back to a derived dev key (set a real key in production)."
        )

    single = os.getenv("PII_ENCRYPTION_KEY", "").strip()
    if single:
        key = single.encode()
        if _is_valid_fernet_key(key):
            return [key]
        logger.warning(
            "PII_ENCRYPTION_KEY is set to '%s...' which is not a valid Fernet key. "
            "Falling back to a derived dev key. Generate a real key with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"",
            single[:8],
        )

    secret = (os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET") or "").strip()
    if secret:
        logger.warning(
            "Using a dev-only PII key derived from SECRET_KEY/JWT_SECRET. "
            "DO NOT use this in production - rotating the secret would orphan all encrypted PII."
        )
        return [_derive_dev_key(secret)]

    raise RuntimeError(
        "No encryption key configured. Set PII_ENCRYPTION_KEY in .env. "
        "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
    )


_keys = _load_keys()
_fernets = [Fernet(k) for k in _keys]
_cipher = MultiFernet(_fernets) if len(_fernets) > 1 else _fernets[0]


def encrypt_pii(plain_text: str) -> str:
    """Encrypt a UTF-8 string. Returns a URL-safe-base64 string for VARCHAR columns."""
    if plain_text is None:
        raise ValueError("encrypt_pii: cannot encrypt None - use encrypt_pii_optional")
    return _cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_pii(stored) -> str:
    """Decrypt a stored ciphertext (str or bytes) back to a UTF-8 string."""
    if stored is None:
        raise ValueError("decrypt_pii: cannot decrypt None - use decrypt_pii_optional")
    if isinstance(stored, str):
        stored = stored.encode("utf-8")
    return _cipher.decrypt(stored).decode("utf-8")


def encrypt_pii_optional(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    return encrypt_pii(value)


def decrypt_pii_optional(stored) -> Optional[str]:
    if stored is None:
        return None
    raw = stored.encode("utf-8") if isinstance(stored, str) else stored
    try:
        return _cipher.decrypt(raw).decode("utf-8")
    except InvalidToken:
        logger.warning("decrypt_pii_optional: not a Fernet token; treating as legacy plain text.")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            logger.error("decrypt_pii_optional: legacy bytes not UTF-8; returning None")
            return None
