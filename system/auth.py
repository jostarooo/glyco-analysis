from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Callable


PBKDF2_ITERATIONS = 260_000
DEMO_USERNAME = "demo"
DEMO_PASSWORD_HASH = (
    "pbkdf2_sha256$260000$ebr-aP1VSnrASwDv5a45MA$"
    "qstC4w0Y2PctKLT2s1udZOdmbCI6C8nMAZxRYz5_uHo"
)


class AuthError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Session:
    token: str
    username: str
    csrf_token: str
    expires_at: datetime


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(
    password: str,
    *,
    iterations: int = PBKDF2_ITERATIONS,
    salt: bytes | None = None,
) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return f"pbkdf2_sha256${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthService:
    def __init__(
        self,
        username: str,
        password_hash: str,
        *,
        session_ttl: timedelta = timedelta(hours=8),
        failure_window: timedelta = timedelta(minutes=5),
        lockout: timedelta = timedelta(minutes=1),
        max_failures: int = 5,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        if not username:
            raise ValueError("username must not be empty")
        if not password_hash:
            raise ValueError("password_hash must not be empty")
        self.username = username
        self.password_hash = password_hash
        self.session_ttl = session_ttl
        self.failure_window = failure_window
        self.lockout = lockout
        self.max_failures = max_failures
        self._clock = clock
        self._sessions: dict[str, Session] = {}
        self._failures: dict[tuple[str, str], list[datetime]] = {}
        self._locked_until: dict[tuple[str, str], datetime] = {}
        self._lock = Lock()

    @classmethod
    def with_password(
        cls,
        username: str,
        password: str,
        **kwargs: object,
    ) -> "AuthService":
        return cls(username, hash_password(password), **kwargs)  # type: ignore[arg-type]

    def authenticate(self, username: object, password: object, client_ip: str) -> None:
        if not isinstance(username, str) or not isinstance(password, str):
            raise AuthError("INVALID_CREDENTIALS", "用户名或密码错误")

        key = (client_ip, username)
        now = self._clock()
        with self._lock:
            locked_until = self._locked_until.get(key)
            if locked_until and now < locked_until:
                raise AuthError(
                    "LOGIN_LOCKED",
                    "登录失败次数过多，请稍后重试",
                    status=429,
                )
            if locked_until:
                self._locked_until.pop(key, None)
                self._failures.pop(key, None)

        username_valid = hmac.compare_digest(username, self.username)
        password_valid = verify_password(password, self.password_hash)
        valid = username_valid and password_valid
        if valid:
            with self._lock:
                self._failures.pop(key, None)
                self._locked_until.pop(key, None)
            return

        with self._lock:
            cutoff = now - self.failure_window
            attempts = [
                timestamp
                for timestamp in self._failures.get(key, [])
                if timestamp >= cutoff
            ]
            attempts.append(now)
            self._failures[key] = attempts
            if len(attempts) >= self.max_failures:
                self._locked_until[key] = now + self.lockout
                raise AuthError(
                    "LOGIN_LOCKED",
                    "登录失败次数过多，请稍后重试",
                    status=429,
                )
        raise AuthError("INVALID_CREDENTIALS", "用户名或密码错误")

    def create_session(self, username: str) -> Session:
        if not hmac.compare_digest(username, self.username):
            raise AuthError("INVALID_CREDENTIALS", "用户名或密码错误")
        now = self._clock()
        session = Session(
            token=secrets.token_urlsafe(32),
            username=username,
            csrf_token=secrets.token_urlsafe(24),
            expires_at=now + self.session_ttl,
        )
        with self._lock:
            self._prune_sessions_locked(now)
            self._sessions[session.token] = session
        return session

    def get_session(self, token: str | None) -> Session | None:
        if not token:
            return None
        now = self._clock()
        with self._lock:
            self._prune_sessions_locked(now)
            return self._sessions.get(token)

    def destroy_session(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def _prune_sessions_locked(self, now: datetime) -> None:
        expired = [
            token
            for token, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for token in expired:
            self._sessions.pop(token, None)
