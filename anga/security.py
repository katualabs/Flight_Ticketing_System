"""Cross-cutting protections: CSRF, access control, rate limits and headers."""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable
from functools import wraps
from urllib.parse import urlsplit

from flask import Flask, abort, flash, g, redirect, request, session, url_for

CSRF_SESSION_KEY = "_csrf"
CSRF_FORM_FIELD = "_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
NO_STORE_PREFIXES = ("/account", "/book", "/manage", "/admin")

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)

PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


def csrf_token() -> str:
    """The session's CSRF token, created on first use."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _check_csrf() -> None:
    if request.method in SAFE_METHODS:
        return
    expected = session.get(CSRF_SESSION_KEY, "")
    supplied = request.headers.get(CSRF_HEADER) or request.form.get(CSRF_FORM_FIELD, "")
    if not expected or not secrets.compare_digest(expected, supplied):
        abort(400, description="Your session expired. Please go back and try again.")


def _load_user() -> None:
    from anga.services.accounts import active_user

    user_id = session.get("user_id")
    g.user = active_user(user_id) if user_id else None
    if user_id and g.user is None:
        session.clear()


def _apply_headers(response):
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
    if request.path.startswith(NO_STORE_PREFIXES):
        response.headers["Cache-Control"] = "no-store"
    return response


def is_safe_redirect(target: str | None) -> bool:
    """Only same-site paths may be redirected to, which rules out open redirects."""
    if not target or not target.startswith("/") or target.startswith(("//", "/\\")):
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc and "\\" not in target


def safe_redirect_target(target: str | None, fallback: str) -> str:
    return target if is_safe_redirect(target) else fallback


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            flash("Please log in to continue.", "info")
            return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped


def staff_required(view: Callable) -> Callable:
    """Agents and admins. Anonymous users are sent to log in; customers get a 403."""

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] not in ("agent", "admin"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def admin_required(view: Callable) -> Callable:
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped


class TokenBucketLimiter:
    """In-memory per-key token bucket.

    Per-process is an accepted limit: it stops casual API abuse without adding
    Redis to a SQLite-sized deployment.
    """

    MAX_KEYS = 10_000

    def __init__(self, rate_per_minute: float, burst: int) -> None:
        self.rate = rate_per_minute / 60
        self.burst = burst
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._buckets) > self.MAX_KEYS:
                self._buckets.clear()
            tokens, updated = self._buckets.get(key, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - updated) * self.rate)
            allowed = tokens >= 1
            self._buckets[key] = (tokens - 1 if allowed else tokens, now)
            return allowed


def init_app(app: Flask) -> None:
    app.before_request(_check_csrf)
    app.before_request(_load_user)
    app.after_request(_apply_headers)
    app.jinja_env.globals["csrf_token"] = csrf_token
