"""Language, currency and theme preferences."""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest

from anga import i18n
from anga.services import preferences
from tests.helpers import future_date

TEMPLATES = Path(i18n.__file__).parent / "templates"
DYNAMIC_PREFIXES = {
    "book.step_",
    "book.type_",
    "cabin.",
    "day.",
    "fare.bags_",
    "home.why_",
    "manage.method_",
    "search.sort_",
    "search.time_",
    "book.",
}


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_english_string_has_swahili():
    missing = set(i18n.STRINGS["en"]) - set(i18n.STRINGS["sw"])
    assert not missing, sorted(missing)


def test_no_orphaned_swahili_strings():
    assert not set(i18n.STRINGS["sw"]) - set(i18n.STRINGS["en"])


def test_translations_use_the_same_placeholders():
    for key, english in i18n.STRINGS["en"].items():
        assert placeholders(english) == placeholders(i18n.STRINGS["sw"][key]), key


def test_every_key_used_in_templates_exists():
    for path in TEMPLATES.rglob("*.html"):
        for key in re.findall(r"t\('([a-z_]+\.[A-Za-z_]+)'\)?", path.read_text(encoding="utf-8")):
            if key.endswith("_") or key in DYNAMIC_PREFIXES:
                continue
            assert key in i18n.STRINGS["en"], f"{key} in {path.name}"


def test_unknown_key_falls_back_to_itself():
    assert i18n.t("no.such.key") == "no.such.key"


def test_language_toggle_switches_ui_and_html_lang(client):
    english = client.get("/")
    assert b'lang="en"' in english.data
    assert b"Search flights" in english.data
    response = client.post("/preferences/language", data={"lang": "sw", "next": "/about"})
    assert response.headers["Location"] == "/about"
    swahili = client.get("/")
    assert b'lang="sw"' in swahili.data
    assert b"Tafuta ndege" in swahili.data
    client.post("/preferences/language", data={"lang": "en"})
    assert b"Search flights" in client.get("/").data


def test_unsupported_language_is_ignored(client):
    client.post("/preferences/language", data={"lang": "xx"})
    assert b'lang="en"' in client.get("/").data


def test_preference_redirects_are_local_only(client):
    response = client.post(
        "/preferences/language", data={"lang": "sw", "next": "https://evil.example/"}
    )
    assert response.headers["Location"] == "/"


@pytest.mark.parametrize(
    "path", ["/", "/about", "/faq", "/contact", "/status", "/manage/", "/account/login"]
)
def test_pages_render_in_swahili(client, path):
    client.post("/preferences/language", data={"lang": "sw"})
    assert client.get(path).status_code == 200


def test_currency_toggle_changes_display_only(client, app):
    url = f"/search/?from=NBO&to=MBA&depart={future_date()}&trip=one_way&adults=1"
    assert b"KSh 8," in client.get(url).data or b"KSh 9," in client.get(url).data
    client.post("/preferences/currency", data={"currency": "USD"})
    page = client.get(url)
    assert b"US$ " in page.data
    # The value posted to booking is a fare id, and the data price stays in shillings.
    assert re.search(rb'data-price="\d{4,}"', page.data)


def test_unknown_currency_is_ignored(client):
    client.post("/preferences/currency", data={"currency": "XXX"})
    assert b"US$ " not in client.get("/").data


def test_usd_summary_explains_the_real_charge(client, app):
    from tests.helpers import get_fare

    with app.app_context():
        fare_id = get_fare()["id"]
    client.post("/book/start", data={"outbound_fare": fare_id, "adults": 1, "trip": "one_way"})
    client.post("/preferences/currency", data={"currency": "USD"})
    client.post(
        "/book/passengers",
        data={
            "name_0": "Amina Otieno",
            "id_0": "A1234567",
            "email": "amina@example.com",
            "phone": "+254712345678",
        },
    )
    page = client.get("/book/review")
    assert b"You will be charged KSh" in page.data


def test_usd_rate_reads_the_setting_and_survives_bad_values(seeded):
    from anga.repositories import settings

    assert preferences.usd_rate() == 129
    settings.put("usd_rate", "nonsense")
    assert preferences.usd_rate() == preferences.DEFAULT_USD_RATE
    settings.put("usd_rate", "-5")
    assert preferences.usd_rate() == preferences.DEFAULT_USD_RATE
    settings.put("checkin_open_hours", "nonsense")
    assert preferences.checkin_open_hours() == 48


def test_theme_toggle_is_present_and_loaded_before_paint(client):
    page = client.get("/").data
    assert b"data-theme-toggle" in page
    assert page.index(b"theme-init.js") < page.index(b"</head>")
