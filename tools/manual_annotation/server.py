"""Loopback-only HTTP application for direct source geometry review."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import secrets
import threading
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .imaging import SourceRaster, sha256_file
from .workspace import ReviewWorkspace, WorkspaceError


MAX_REQUEST_BYTES = 1_000_000
STATIC_TYPES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


class RasterCache:
    def __init__(self, workspace: ReviewWorkspace):
        self.workspace = workspace
        self._lock = threading.RLock()
        self._identity: str | None = None
        self._raster: SourceRaster | None = None
        self._levels: list[list[float]] | None = None

    def get(self, identity: str) -> tuple[SourceRaster, list[list[float]]]:
        sha = self.workspace.resolve_identity(identity)
        with self._lock:
            if self._identity == sha and self._raster is not None and self._levels is not None:
                return self._raster, self._levels
            self.close()
            record = self.workspace.load_record(sha)
            source = self.workspace.resolve_repository_path(record["source"]["relative_path"])
            if sha256_file(source) != sha:
                raise WorkspaceError("source TIFF changed after annotation preparation")
            raster = SourceRaster(source)
            levels = record["diagnostics"].get("render_levels")
            if not isinstance(levels, list) or len(levels) != 3:
                _, levels = raster.analysis_rgb8()
            self._identity = sha
            self._raster = raster
            self._levels = levels
            return raster, levels

    def close(self) -> None:
        if self._raster is not None:
            self._raster.close()
        self._identity = None
        self._raster = None
        self._levels = None

    def native_tile(
        self,
        identity: str,
        *,
        center_x: float,
        center_y: float,
        side: int,
    ) -> tuple[bytes, dict[str, int]]:
        with self._lock:
            raster, levels = self.get(identity)
            return raster.native_tile_png(
                center_x=center_x,
                center_y=center_y,
                side=side,
                levels=levels,
            )


class AnnotationServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        workspace: ReviewWorkspace,
        token: str,
    ):
        super().__init__(address, AnnotationRequestHandler)
        self.workspace = workspace
        self.token = token
        self.web_root = Path(__file__).resolve().parent / "web"
        self.raster_cache = RasterCache(workspace)

    def server_close(self) -> None:
        self.raster_cache.close()
        super().server_close()


class AnnotationRequestHandler(BaseHTTPRequestHandler):
    server: AnnotationServer

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _split(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urlsplit(self.path)
        return unquote(parsed.path), parse_qs(parsed.query, keep_blank_values=True)

    def _authorized(self, query: dict[str, list[str]]) -> bool:
        supplied = self.headers.get("X-X5-Token")
        if supplied is None:
            supplied = query.get("token", [None])[0]
        return isinstance(supplied, str) and secrets.compare_digest(
            supplied,
            self.server.token,
        )

    def _write_allowed(self, query: dict[str, list[str]]) -> bool:
        if not self._authorized(query) or self.headers.get("X-X5-Write") != "1":
            return False
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return origin is None or origin == f"http://{host}"

    def _send(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, value: Any) -> None:
        self._send(
            status,
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"error": message})

    def _body_json(self) -> dict[str, Any]:
        if self.headers.get_content_type() != "application/json":
            raise WorkspaceError("request Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "")
        except ValueError as error:
            raise WorkspaceError("request Content-Length is invalid") from error
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise WorkspaceError("request body size is invalid")
        try:
            value = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as error:
            raise WorkspaceError("request body is invalid JSON") from error
        if not isinstance(value, dict):
            raise WorkspaceError("request body must be a JSON object")
        return value

    def do_GET(self) -> None:
        path, query = self._split()
        if path in STATIC_TYPES:
            filename, content_type = STATIC_TYPES[path]
            static_path = self.server.web_root / filename
            if not static_path.is_file():
                self._error(HTTPStatus.NOT_FOUND, "web asset is missing")
                return
            self._send(HTTPStatus.OK, static_path.read_bytes(), content_type)
            return
        if not self._authorized(query):
            self._error(HTTPStatus.UNAUTHORIZED, "local annotation token is required")
            return
        try:
            if path == "/api/index":
                self._json(HTTPStatus.OK, self.server.workspace.index())
                return
            if path.startswith("/api/record/"):
                identity = path.removeprefix("/api/record/")
                self._json(
                    HTTPStatus.OK,
                    self.server.workspace.load_record(identity, client=True),
                )
                return
            if path.startswith("/api/preview/"):
                identity = path.removeprefix("/api/preview/")
                sha = self.server.workspace.resolve_identity(identity)
                preview = self.server.workspace.preview_path(sha)
                if not preview.is_file():
                    raise WorkspaceError("bounded preview is not prepared")
                record = self.server.workspace.load_record(sha)
                if sha256_file(preview) != record["diagnostics"].get(
                    "preview_jpeg_sha256"
                ):
                    raise WorkspaceError("bounded preview SHA-256 mismatch")
                self._send(HTTPStatus.OK, preview.read_bytes(), "image/jpeg")
                return
            if path.startswith("/api/tile/"):
                identity = path.removeprefix("/api/tile/")
                try:
                    x = float(query.get("x", [""])[0])
                    y = float(query.get("y", [""])[0])
                    side = int(query.get("side", ["512"])[0])
                except ValueError as error:
                    raise WorkspaceError("native tile coordinates are invalid") from error
                if not math.isfinite(x) or not math.isfinite(y):
                    raise WorkspaceError("native tile coordinates must be finite")
                payload, extent = self.server.raster_cache.native_tile(
                    identity,
                    center_x=x,
                    center_y=y,
                    side=side,
                )
                self._send(
                    HTTPStatus.OK,
                    payload,
                    "image/png",
                    headers={
                        "X-X5-Tile-Left": str(extent["left"]),
                        "X-X5-Tile-Top": str(extent["top"]),
                        "X-X5-Tile-Width": str(extent["width"]),
                        "X-X5-Tile-Height": str(extent["height"]),
                    },
                )
                return
            self._error(HTTPStatus.NOT_FOUND, "unknown local annotation endpoint")
        except WorkspaceError as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))
        except Exception as error:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def _write_request(self) -> None:
        path, query = self._split()
        if not self._write_allowed(query):
            self._error(HTTPStatus.FORBIDDEN, "write request failed local-origin protection")
            return
        try:
            payload = self._body_json()
            if path.startswith("/api/geometry/") and self.command == "PATCH":
                identity = path.removeprefix("/api/geometry/")
                result = self.server.workspace.update_geometry(identity, payload)
            elif path.startswith("/api/review/") and self.command == "POST":
                identity = path.removeprefix("/api/review/")
                if set(payload) != {"expected_revision", "task_id", "reviewed"}:
                    raise WorkspaceError("task review request has unexpected fields")
                result = self.server.workspace.set_task_reviewed(
                    identity,
                    expected_revision=payload["expected_revision"],
                    task_id=payload["task_id"],
                    reviewed=payload["reviewed"],
                )
            elif path.startswith("/api/confirm/") and self.command == "POST":
                identity = path.removeprefix("/api/confirm/")
                if set(payload) != {"expected_revision", "checklist"}:
                    raise WorkspaceError("confirmation request has unexpected fields")
                result = self.server.workspace.confirm(
                    identity,
                    expected_revision=payload["expected_revision"],
                    checklist=payload["checklist"],
                )
            else:
                self._error(HTTPStatus.NOT_FOUND, "unknown local annotation endpoint")
                return
            self._json(HTTPStatus.OK, result)
        except (WorkspaceError, KeyError, TypeError) as error:
            self._error(HTTPStatus.CONFLICT, str(error))
        except Exception as error:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def do_PATCH(self) -> None:
        self._write_request()

    def do_POST(self) -> None:
        self._write_request()


def create_server(
    workspace: ReviewWorkspace,
    *,
    port: int = 0,
    token: str | None = None,
) -> AnnotationServer:
    if not 0 <= port <= 65535:
        raise WorkspaceError("server port must be 0..65535")
    return AnnotationServer(
        ("127.0.0.1", port),
        workspace,
        token or secrets.token_urlsafe(32),
    )
