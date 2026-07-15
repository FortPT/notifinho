"""Token, password-hash, and rate-limit foundations for the local API."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
import threading
import time

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    sources: frozenset[str]
    rate_limit_per_minute: int

    def allows(self, source: str) -> bool:
        normalized = str(source or "").casefold()
        return self.role == "admin" or "*" in self.sources or normalized in self.sources


def hash_token(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def hash_password(password: str, salt: bytes | None = None, iterations: int = 600_000) -> str:
    """Return a portable PBKDF2 record for the v2.0 local-login layer."""

    if len(str(password)) < 12:
        raise ValueError("password must contain at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        str(password).encode("utf-8"),
        salt,
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, record: str) -> bool:
    try:
        algorithm, iterations, salt, expected = str(record).split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            str(password).encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations),
        ).hex()
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(digest, expected)


class TokenAuthenticator:
    def __init__(self, configuration):
        self.configuration = configuration

    def authenticate(
        self,
        supplied: str,
        source: str = "",
        require_admin: bool = False,
    ) -> Principal | None:
        candidate = str(supplied or "")
        tokens = self.configuration.get("api", "tokens", default={}) or {}
        if not candidate or not isinstance(tokens, dict):
            return None
        candidate_hash = hash_token(candidate)
        for name, settings in tokens.items():
            if not isinstance(settings, dict) or settings.get("enabled", True) is not True:
                continue
            expected_hash = self._expected_hash(settings)
            if not expected_hash or not hmac.compare_digest(candidate_hash, expected_hash):
                continue
            role = str(settings.get("role") or "application").casefold()
            sources = settings.get("sources") or []
            if isinstance(sources, str):
                sources = [sources]
            principal = Principal(
                name=str(name)[:128],
                role=role,
                sources=frozenset(str(item).casefold() for item in sources),
                rate_limit_per_minute=max(
                    1,
                    min(int(settings.get("rate_limit_per_minute", 60)), 10_000),
                ),
            )
            if require_admin and principal.role != "admin":
                return None
            if source and not principal.allows(source):
                return None
            return principal
        return None

    @staticmethod
    def _expected_hash(settings: dict) -> str:
        configured_hash = str(settings.get("token_sha256") or "").strip().casefold()
        if len(configured_hash) == 64 and all(ch in "0123456789abcdef" for ch in configured_hash):
            return configured_hash
        value = ""
        env_name = str(settings.get("token_env") or "").strip()
        file_name = str(settings.get("token_file") or "").strip()
        if env_name:
            value = os.environ.get(env_name, "")
        elif file_name:
            path = Path(file_name)
            try:
                flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(path, flags)
                with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                    details = os.fstat(stream.fileno())
                    if stat.S_ISREG(details.st_mode) and details.st_mode & 0o077 == 0:
                        value = stream.read(4097).strip()
                        if len(value) > 4096:
                            value = ""
            except OSError:
                value = ""
        return hash_token(value) if value else ""


class RateLimiter:
    """Small fixed-window limiter scoped to token identity and client address."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._entries: dict[tuple[str, str], tuple[int, float]] = {}
        self._lock = threading.Lock()

    def allow(self, principal: Principal, client: str) -> bool:
        key = (principal.name, str(client))
        now = self.clock()
        with self._lock:
            self._entries = {
                item: state
                for item, state in self._entries.items()
                if now - state[1] < 120
            }
            count, started = self._entries.get(key, (0, now))
            if now - started >= 60:
                count, started = 0, now
            if count >= principal.rate_limit_per_minute:
                self._entries[key] = (count, started)
                return False
            self._entries[key] = (count + 1, started)
            return True
