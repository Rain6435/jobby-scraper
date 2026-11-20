"""Encrypted credential and Playwright storage_state vault."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import string
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_KEY_FILE = Path.home() / ".config" / "jobby-scraper" / "vault.key"
PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a deterministic 32-byte URL-safe base64 Fernet key from a passphrase."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def load_or_create_master_key(key_file: Path | None = None) -> bytes:
    """Load vault key from APPLY_VAULT_KEY env var or a local 0600 key file."""
    env_key = os.environ.get("APPLY_VAULT_KEY", "").strip()
    if env_key:
        try:
            raw = env_key.encode("utf-8")
            Fernet(raw)
            return raw
        except ValueError:
            return _derive_fernet_key(env_key)

    target = key_file or DEFAULT_KEY_FILE
    if target.is_file():
        return target.read_bytes().strip()

    target.parent.mkdir(parents=True, exist_ok=True)
    new_key = Fernet.generate_key()
    target.write_bytes(new_key)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return new_key


class Vault:
    """Symmetric AES-based (Fernet) vault for passwords, tokens, and browser state."""

    def __init__(self, key: bytes | None = None, key_file: Path | None = None) -> None:
        resolved = key if key is not None else load_or_create_master_key(key_file)
        self._fernet = Fernet(resolved)

    def encrypt(self, plaintext: str) -> str:
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            raw = self._fernet.decrypt(ciphertext.encode("utf-8"))
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt vault payload with current master key") from exc
        return raw.decode("utf-8")


def generate_strong_password(length: int = 20) -> str:
    """Generate a high-entropy password meeting common ATS complexity rules."""
    if length < 12:
        raise ValueError("Password length must be at least 12 characters")
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()-_=+"),
    ]
    rest = [secrets.choice(PASSWORD_ALPHABET) for _ in range(length - len(required))]
    chars = required + rest
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
