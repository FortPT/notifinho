"""Serve a bounded set of packaged WebUI assets with strict browser policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SECURITY_HEADERS = (
    (
        "Content-Security-Policy",
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'",
    ),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
)


@dataclass(frozen=True)
class WebUIResponse:
    status: int
    body: bytes = b""
    content_type: str = ""
    cache_control: str = "no-store"


class WebUIService:
    """Resolve only known packaged assets; never map request paths to disk."""

    def __init__(
        self,
        configuration,
        *,
        root: str | Path | None = None,
        platform_available: bool = True,
    ):
        self.configuration = configuration
        self.platform_available = bool(platform_available)
        self.root = (
            Path(root).resolve()
            if root is not None
            else Path(__file__).resolve().parents[2]
        )
        self.assets = {
            "/": ("src/webui/index.html", "text/html; charset=utf-8", "no-store"),
            "/ui": ("src/webui/index.html", "text/html; charset=utf-8", "no-store"),
            "/ui/": ("src/webui/index.html", "text/html; charset=utf-8", "no-store"),
            "/ui/app.js": (
                "src/webui/app.js",
                "text/javascript; charset=utf-8",
                "no-cache",
            ),
            "/ui/styles.css": (
                "src/webui/styles.css",
                "text/css; charset=utf-8",
                "no-cache",
            ),
            "/ui/icon.png": (
                "assets/icons/notifinho.png",
                "image/png",
                "public, max-age=86400",
            ),
            "/ui/icons/discord.svg": (
                "assets/icons/discord.svg", "image/svg+xml", "public, max-age=86400"
            ),
            "/ui/icons/mqtt.svg": (
                "assets/icons/mqtt.svg", "image/svg+xml", "public, max-age=86400"
            ),
            "/ui/icons/ntfy.svg": (
                "assets/icons/ntfy.svg", "image/svg+xml", "public, max-age=86400"
            ),
        }

    @property
    def enabled(self) -> bool:
        return self.platform_available and all(
            self.configuration.get(section, "enabled", default=True) is True
            for section in ("http", "api", "platform", "webui")
        )

    def response(self, path: str) -> WebUIResponse | None:
        route = str(path or "")
        if route not in self.assets:
            if route.startswith("/ui/"):
                return WebUIResponse(404)
            return None
        if not self.enabled:
            return WebUIResponse(404)
        relative, content_type, cache_control = self.assets[route]
        asset = self.root / relative
        try:
            body = asset.read_bytes()
        except OSError:
            return WebUIResponse(404)
        return WebUIResponse(200, body, content_type, cache_control)
