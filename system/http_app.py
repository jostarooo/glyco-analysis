from __future__ import annotations

import json
import hmac
import re
import traceback
from dataclasses import dataclass
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .auth import AuthError, AuthService, Session
from .jobs import JobError, JobService
from .models import ValidationError
from .samples import SampleProvider


COOKIE_NAME = "glyco_session"
MAX_REQUEST_BYTES = 16 * 1024
JOB_PATH = re.compile(r"^/api/predictions/([0-9a-f]{32})$")


class RuntimePort(Protocol):
    @property
    def state(self) -> str: ...

    @property
    def state_message(self) -> str: ...

    def model_info(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AppContext:
    head: str
    auth: AuthService
    jobs: JobService
    predictor: RuntimePort
    samples: SampleProvider
    index_html: bytes

    def runtime_payload(self) -> dict[str, Any]:
        sample = self.samples.load()
        model = self.predictor.model_info()
        if not model.get("state_message"):
            model["state_message"] = self.predictor.state_message
        return {
            "head": self.head,
            "model": model,
            "sample": sample.to_public_dict() if sample else None,
            "service": {
                "name": "glyco-analysis-system",
                "version": "w3-day1",
                "bind_policy": "local-only",
            },
        }


class GlycoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class GlycoRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "glyco-system/0.1"
    app_context: AppContext

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/healthz":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "model_state": self.app_context.predictor.state,
                        "head": self.app_context.head,
                    },
                )
                return
            if path == "/api/auth/session":
                self._handle_session()
                return
            if path == "/api/runtime":
                session = self._require_session()
                if session is None:
                    return
                self._send_json(HTTPStatus.OK, self.app_context.runtime_payload())
                return
            match = JOB_PATH.fullmatch(path)
            if match:
                session = self._require_session()
                if session is None:
                    return
                try:
                    job = self.app_context.jobs.get(match.group(1), session.username)
                except JobError as error:
                    self._error(HTTPStatus(error.status), error.code, error.message)
                    return
                self._send_json(HTTPStatus.OK, job.to_dict())
                return
            if path in {"/", "/index.html"}:
                self._send_bytes(
                    HTTPStatus.OK,
                    self.app_context.index_html,
                    "text/html; charset=utf-8",
                    cache=False,
                )
                return
            if path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Content-Length", "0")
                self._end_headers()
                return
            self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "请求路径不存在")
        except Exception:
            traceback.print_exc()
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "服务器内部错误",
            )

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            if not self._check_origin():
                return
            if path == "/api/auth/login":
                self._handle_login()
                return
            if path == "/api/auth/logout":
                self._handle_logout()
                return
            if path == "/api/predictions":
                self._handle_submit()
                return
            self._error(HTTPStatus.NOT_FOUND, "NOT_FOUND", "请求路径不存在")
        except Exception:
            traceback.print_exc()
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_ERROR",
                "服务器内部错误",
            )

    def _handle_session(self) -> None:
        session = self._current_session()
        if session is None:
            self._send_json(HTTPStatus.OK, {"authenticated": False})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "authenticated": True,
                "user": {"username": session.username},
                "csrf_token": session.csrf_token,
            },
        )

    def _handle_login(self) -> None:
        payload = self._read_json()
        if payload is None:
            return
        username = payload.get("username")
        password = payload.get("password")
        client_ip = self.client_address[0]
        try:
            self.app_context.auth.authenticate(username, password, client_ip)
        except AuthError as error:
            self._error(HTTPStatus(error.status), error.code, error.message)
            return

        assert isinstance(username, str)
        session = self.app_context.auth.create_session(username)
        self._send_json(
            HTTPStatus.OK,
            {
                "authenticated": True,
                "user": {"username": session.username},
                "csrf_token": session.csrf_token,
            },
            extra_headers=[self._session_cookie(session)],
        )

    def _handle_logout(self) -> None:
        session = self._require_session()
        if session is None:
            return
        if not self._require_csrf(session):
            return
        self.app_context.auth.destroy_session(session.token)
        self._send_json(
            HTTPStatus.OK,
            {"authenticated": False},
            extra_headers=[
                f"{COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
            ],
        )

    def _handle_submit(self) -> None:
        session = self._require_session()
        if session is None:
            return
        if not self._require_csrf(session):
            return
        payload = self._read_json()
        if payload is None:
            return
        protein_id = payload.get("protein_id")
        if protein_id is not None and not isinstance(protein_id, str):
            self._error(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "INVALID_PROTEIN_ID",
                "protein_id 必须是字符串",
            )
            return
        try:
            job = self.app_context.jobs.submit(
                payload.get("sequence"),
                session.username,
                protein_id=protein_id,
            )
        except ValidationError as error:
            self._error(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                error.code,
                error.message,
            )
            return
        except JobError as error:
            self._error(HTTPStatus(error.status), error.code, error.message)
            return
        self._send_json(HTTPStatus.ACCEPTED, job.to_dict())

    def _current_session(self) -> Session | None:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get(COOKIE_NAME)
        token = morsel.value if morsel else None
        return self.app_context.auth.get_session(token)

    def _require_session(self) -> Session | None:
        session = self._current_session()
        if session is None:
            self._error(
                HTTPStatus.UNAUTHORIZED,
                "AUTH_REQUIRED",
                "请先登录",
            )
            return None
        return session

    def _require_csrf(self, session: Session) -> bool:
        token = self.headers.get("X-CSRF-Token", "")
        if not token or not hmac.compare_digest(token, session.csrf_token):
            self._error(
                HTTPStatus.FORBIDDEN,
                "CSRF_REJECTED",
                "请求校验失败，请刷新页面后重试",
            )
            return False
        return True

    def _check_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        allowed = {f"http://{host}", f"https://{host}"}
        if origin not in allowed:
            self._error(
                HTTPStatus.FORBIDDEN,
                "ORIGIN_REJECTED",
                "请求来源不被允许",
            )
            return False
        return True

    def _read_json(self) -> dict[str, Any] | None:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type.lower():
            self._error(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "JSON_REQUIRED",
                "请求体必须是 application/json",
            )
            return None
        length_text = self.headers.get("Content-Length")
        try:
            length = int(length_text or "")
        except ValueError:
            self._error(
                HTTPStatus.LENGTH_REQUIRED,
                "LENGTH_REQUIRED",
                "缺少有效的 Content-Length",
            )
            return None
        if length < 1 or length > MAX_REQUEST_BYTES:
            self._error(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "REQUEST_TOO_LARGE",
                "请求体为空或超过 16 KiB",
            )
            return None
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(
                HTTPStatus.BAD_REQUEST,
                "INVALID_JSON",
                "请求体不是有效 JSON",
            )
            return None
        if not isinstance(payload, dict):
            self._error(
                HTTPStatus.BAD_REQUEST,
                "JSON_OBJECT_REQUIRED",
                "请求体必须是 JSON 对象",
            )
            return None
        return payload

    def _session_cookie(self, session: Session) -> str:
        return (
            f"{COOKIE_NAME}={session.token}; HttpOnly; SameSite=Strict; "
            "Path=/; Max-Age=28800"
        )

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
        *,
        extra_headers: list[str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self._send_bytes(
            status,
            body,
            "application/json; charset=utf-8",
            cache=False,
            extra_headers=extra_headers,
        )

    def _send_bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        *,
        cache: bool,
        extra_headers: list[str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if not cache:
            self.send_header("Cache-Control", "no-store")
        for header in extra_headers or []:
            self.send_header("Set-Cookie", header)
        self._end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(
            status,
            {"error": {"code": code, "message": message}},
        )

    def _end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'",
        )
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def load_index_html(repo_root: Path) -> bytes:
    path = repo_root / "system" / "static" / "index.html"
    if not path.is_file():
        raise FileNotFoundError(f"System UI not found: {path}")
    return path.read_bytes()


def make_server(
    context: AppContext,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> GlycoHTTPServer:
    class BoundHandler(GlycoRequestHandler):
        app_context = context

    return GlycoHTTPServer((host, port), BoundHandler)
