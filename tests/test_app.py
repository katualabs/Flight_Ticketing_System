"""App factory, shell and error handling."""

from __future__ import annotations

import pytest

from anga import create_app, security
from anga.config import load_or_create_secret_key


def test_home_responds(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Fly the East African skies." in response.data


def test_demo_notice_is_on_every_page(client):
    for path in ("/", "/about", "/faq", "/terms", "/privacy"):
        page = client.get(path)
        assert page.status_code == 200
        assert b"Anga Air is fictional; no real bookings or payments." in page.data


def test_missing_secret_key_is_generated_once_and_reused(tmp_path):
    instance = tmp_path / "instance"
    first = load_or_create_secret_key(instance)
    assert len(first) >= 32
    assert load_or_create_secret_key(instance) == first


def test_configured_secret_key_is_respected(tmp_path):
    app = create_app(
        "production", {"SECRET_KEY": "k" * 40, "DATABASE_PATH": str(tmp_path / "x.db")}
    )
    assert app.config["SECRET_KEY"] == "k" * 40


def test_testing_config_is_applied(app):
    assert app.config["TESTING"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True


def test_not_found_uses_the_branded_page(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert b"flown off course" in response.data


def test_post_without_csrf_is_rejected(client):
    assert client.post("/book/start", csrf=False).status_code == 400


def test_security_headers_present(client):
    headers = client.get("/").headers
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert "unsafe-inline" not in headers["Content-Security-Policy"]
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"]
    assert headers["Permissions-Policy"]


@pytest.mark.parametrize(
    ("target", "safe"),
    [
        ("/account", True),
        ("/book?x=1", True),
        ("//evil.example", False),
        ("/\\evil.example", False),
        ("https://evil.example", False),
        ("javascript:alert(1)", False),
        ("", False),
        (None, False),
    ],
)
def test_safe_redirects(target, safe):
    assert security.is_safe_redirect(target) is safe


def test_token_bucket_refills_over_time():
    limiter = security.TokenBucketLimiter(rate_per_minute=60, burst=2)
    assert limiter.allow("ip", now=0.0)
    assert limiter.allow("ip", now=0.0)
    assert not limiter.allow("ip", now=0.0)
    assert limiter.allow("ip", now=1.5)
    assert limiter.allow("other", now=0.0)
