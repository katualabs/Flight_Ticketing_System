"""Security properties, including ones a template or module could silently regress."""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

import pytest

import anga
from anga import create_app, db
from tests.helpers import future_date, get_fare

PACKAGE = Path(anga.__file__).parent
TEMPLATES = PACKAGE / "templates"
STATIC_JS = PACKAGE / "static" / "js"
ROOT = PACKAGE.parent


# ------------------------------------------------------------------------- CSRF


def state_changing_rules(app):
    return [
        rule
        for rule in app.url_map.iter_rules()
        if {"POST", "PUT", "PATCH", "DELETE"} & set(rule.methods)
    ]


def test_every_state_changing_route_rejects_a_missing_token(client, app):
    rules = state_changing_rules(app)
    assert len(rules) > 25
    for rule in rules:
        path = re.sub(r"<(?:\w+:)?(\w+)>", "1", rule.rule)
        assert client.post(path, csrf=False).status_code == 400, rule.rule


def test_wrong_token_is_rejected_and_header_or_field_works(client, app):
    client.get("/")
    with client.session_transaction() as session:
        session["_csrf"] = "right"
    url = "/preferences/language"
    assert client.post(url, csrf=False, headers={"X-CSRF-Token": "wrong"}).status_code == 400
    assert client.post(url, csrf=False, data={"_csrf": "wrong"}).status_code == 400
    assert client.post(url, csrf=False, headers={"X-CSRF-Token": "right"}).status_code == 302
    assert client.post(url, csrf=False, data={"_csrf": "right"}).status_code == 302


def test_every_post_form_in_a_template_has_a_token():
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for form in re.findall(r"<form\b[^>]*>.*?</form>", text, flags=re.S | re.I):
            if re.search(r'method="post"', form, flags=re.I):
                assert "csrf()" in form or "csrf_token()" in form, f"{path.name}: {form[:80]}"


# ---------------------------------------------------------------- SQL injection


INJECTIONS = ["' OR '1'='1", "'; DROP TABLE bookings; --", '" OR ""="', "AN101' UNION SELECT 1 --"]


@pytest.mark.parametrize("attack", INJECTIONS)
def test_injection_attempts_are_harmless(client, app, attack):
    with app.app_context():
        before = db.fetch_value("SELECT COUNT(*) FROM bookings")
    assert client.get("/search/", query_string={"from": attack, "to": "MBA"}).status_code == 400
    assert client.get("/search/calendar", query_string={"from": attack}).status_code == 200
    assert (
        client.get("/status", query_string={"mode": "number", "number": attack}).status_code == 200
    )
    assert client.get("/api/v1/flights", query_string={"from": attack}).status_code == 400
    assert client.post("/manage/", data={"reference": attack, "email": attack}).status_code == 404
    assert (
        client.post("/account/login", data={"email": attack, "password": attack}).status_code == 401
    )
    assert (
        b"Wanjiru" not in client.post("/manage/", data={"reference": attack, "email": attack}).data
    )
    with app.app_context():
        assert db.fetch_value("SELECT COUNT(*) FROM bookings") == before


@pytest.mark.parametrize("attack", INJECTIONS)
def test_injection_through_admin_search_is_harmless(client, app, attack):
    client.post(
        "/account/login", data={"email": "admin@anga.example", "password": "AngaAdmin#2026"}
    )
    assert client.get("/admin/flights", query_string={"q": attack}).status_code == 200
    assert (
        client.get("/admin/bookings", query_string={"q": attack, "flight": attack}).status_code
        == 200
    )
    assert client.get("/admin/users", query_string={"q": attack}).status_code == 200
    with app.app_context():
        assert db.fetch_value("SELECT COUNT(*) FROM bookings") > 0


def test_repositories_never_interpolate_request_values():
    """f-strings in SQL may only splice constants and clause lists, never parameters."""
    allowed = {
        "FLIGHT_SELECT",
        "FARE_SELECT",
        "SEAT_RECORD_SELECT",
        "WATCH_SELECT",
        "NET_AMOUNT",
        "where",
    }
    for path in (PACKAGE / "repositories").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FormattedValue):
                names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
                # Values such as f"%{query}%" go to params; only those lists are built here.
                assert names <= allowed | {"query", "clauses", "flight_clauses"}, (path.name, names)


# -------------------------------------------------------------------------- XSS


XSS = "<script>alert(1)</script>"


def test_reflected_input_is_escaped(client):
    page = client.get("/search/", query_string={"from": XSS, "to": XSS, "depart": XSS})
    assert XSS.encode() not in page.data
    lookup = client.post("/manage/", data={"reference": XSS, "email": XSS})
    assert XSS.encode() not in lookup.data
    contact = client.post(
        "/contact", data={"full_name": XSS, "email": XSS, "subject": XSS, "body": XSS}
    )
    assert XSS.encode() not in contact.data
    assert b"&lt;script&gt;" in contact.data


def test_stored_input_is_escaped(client, app):
    with app.app_context():
        db.execute("UPDATE bookings SET contact_email = ? WHERE reference = 'ANDEMO01'", (XSS,))
        db.execute("UPDATE booking_passengers SET full_name = ? WHERE id = 1", (XSS,))
    client.post(
        "/account/login", data={"email": "admin@anga.example", "password": "AngaAdmin#2026"}
    )
    for path in ("/admin/bookings/ANDEMO01", "/admin/bookings?q=ANDEMO01", "/manage/ANDEMO01"):
        assert XSS.encode() not in client.get(path).data


def test_no_template_marks_values_safe():
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "|safe" not in text.replace(" ", ""), path.name
        assert "autoescape false" not in text, path.name


# -------------------------------------------------------------------------- CSP


def test_csp_blocks_inline_scripts_and_styles(client):
    policy = client.get("/").headers["Content-Security-Policy"]
    assert "default-src 'self'" in policy
    assert "script-src 'self'" in policy
    assert "style-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy


def test_templates_comply_with_the_csp():
    """Emails render outside the site's CSP, in a sandboxed frame, so they are exempt."""
    for path in TEMPLATES.rglob("*.html"):
        if "emails" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)", text), f"inline script in {path.name}"
        assert not re.search(r"\sstyle\s*=", text), f"style attribute in {path.name}"
        assert not re.search(r"<style\b", text), f"style element in {path.name}"
        assert not re.search(r"\son[a-z]+\s*=", text), f"event handler in {path.name}"


def test_no_external_assets_are_loaded():
    for path in TEMPLATES.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for match in re.findall(r'(?:src|href)="(https?://[^"]+)"', text):
            assert path.name == "footer.html" or "about" in path.name, match
        assert not re.search(r'<(?:img|script|link)[^>]+(?:src|href)="https?:', text), path.name


def test_javascript_never_uses_dangerous_sinks():
    for path in STATIC_JS.glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for sink in ("innerHTML", "outerHTML", "document.write", "eval(", "alert(", "confirm("):
            assert sink not in text, f"{sink} in {path.name}"


# ------------------------------------------------------------------ other headers


@pytest.mark.parametrize("path", ["/account/login", "/book/passengers", "/manage/", "/admin/"])
def test_private_pages_are_never_cached(client, path):
    assert client.get(path).headers["Cache-Control"] == "no-store"


def test_public_pages_stay_cacheable(client):
    assert "no-store" not in client.get("/about").headers.get("Cache-Control", "")


def test_session_cookie_flags(client):
    client.post("/preferences/language", data={"lang": "sw"})
    cookie = client.get_cookie("anga_session")
    assert cookie.http_only is True
    assert cookie.same_site == "Lax"


def test_production_uses_secure_cookies_and_hsts(tmp_path, seeded_template):
    path = tmp_path / "prod.db"
    shutil.copyfile(seeded_template, path)
    app = create_app(
        "production", {"SECRET_KEY": "x" * 40, "DATABASE_PATH": str(path), "AUTO_SEED": False}
    )
    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["DEBUG"] is False
    response = app.test_client().get("/about")
    assert "max-age" in response.headers["Strict-Transport-Security"]


def test_oversized_request_is_refused(client, app):
    app.config["MAX_CONTENT_LENGTH"] = 100
    response = client.post("/contact", data={"body": "x" * 1000})
    assert response.status_code == 413
    assert b"too large" in response.data


def test_unexpected_error_shows_the_branded_page_without_details(app, monkeypatch):
    from anga.blueprints import public

    def explode(*_args, **_kwargs):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(public, "render_template", explode)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.testing = False
    response = app.test_client().get("/about")
    assert response.status_code == 500
    assert b"secret internals" not in response.data
    assert b"Something went wrong" in response.data


def test_lookup_attempts_are_rate_limited(tmp_path, seeded_template):
    path = tmp_path / "limited.db"
    shutil.copyfile(seeded_template, path)
    app = create_app(
        "testing", {"DATABASE_PATH": str(path), "LOOKUP_RATE_PER_MINUTE": 1, "LOOKUP_RATE_BURST": 2}
    )
    client = app.test_client()
    client.get("/manage/")
    with client.session_transaction() as session:
        session["_csrf"] = "token"
    headers = {"X-CSRF-Token": "token"}
    data = {"reference": "ANXXXXXX", "email": "a@example.com"}
    assert client.post("/manage/", data=data, headers=headers).status_code == 404
    assert client.post("/manage/", data=data, headers=headers).status_code == 404
    assert client.post("/manage/", data=data, headers=headers).status_code == 429


# ----------------------------------------------------------------- booking privacy


def test_payment_status_is_private(client, app):
    with app.app_context():
        fare_id = get_fare()["id"]
    client.post("/book/start", data={"outbound_fare": fare_id, "adults": 1, "trip": "one_way"})
    client.post(
        "/book/passengers",
        data={
            "name_0": "Amina Otieno",
            "id_0": "A1234567",
            "email": "amina@example.com",
            "phone": "+254712345678",
        },
    )
    response = client.post("/book/pay", data={"method": "mpesa", "mpesa_phone": "0712345678"})
    payment_ref = response.headers["Location"].rsplit("/", 1)[1]
    stranger = app.test_client()
    assert stranger.get(f"/book/payment-status/{payment_ref}").status_code == 404
    assert stranger.get(f"/book/mpesa/{payment_ref}").status_code == 404


def test_draft_details_never_reach_the_browser_cookie(client, app):
    with app.app_context():
        fare_id = get_fare()["id"]
    client.post("/book/start", data={"outbound_fare": fare_id, "adults": 1, "trip": "one_way"})
    client.post(
        "/book/passengers",
        data={
            "name_0": "Amina Otieno",
            "id_0": "SECRET1234",
            "email": "amina@example.com",
            "phone": "+254712345678",
        },
    )
    with client.session_transaction() as session:
        assert "SECRET1234" not in str(dict(session))


def test_search_results_do_not_leak_passengers(client):
    page = client.get(f"/search/?from=NBO&to=MBA&depart={future_date(1)}&trip=one_way&adults=1")
    assert b"Wanjiru" not in page.data


# ----------------------------------------------------------------- architecture


def _imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
    return found


def test_blueprints_never_touch_the_database_directly():
    for path in (PACKAGE / "blueprints").glob("*.py"):
        imports = _imports(path)
        assert "sqlite3" not in imports, path.name
        assert not any(name.startswith(("anga.repositories", "anga.db")) for name in imports), (
            path.name
        )


def test_repositories_hold_sql_only():
    for path in (PACKAGE / "repositories").glob("*.py"):
        imports = _imports(path)
        assert not any(name.startswith("anga.services") for name in imports), path.name
        assert not any(name.startswith(("flask", "anga.blueprints")) for name in imports), path.name


def test_services_do_not_depend_on_http():
    allowed_flask = {"flask", "flask.current_app", "flask.render_template"}
    for path in (PACKAGE / "services").glob("*.py"):
        imports = _imports(path)
        assert not any(name.startswith("anga.blueprints") for name in imports), path.name
        flask_imports = {name for name in imports if name.startswith("flask")}
        assert flask_imports <= allowed_flask, (path.name, flask_imports)


def test_pricing_is_pure():
    imports = _imports(PACKAGE / "services" / "pricing.py")
    assert not any(name.startswith(("flask", "anga", "sqlite3")) for name in imports)
