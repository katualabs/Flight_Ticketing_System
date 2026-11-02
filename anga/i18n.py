"""English and Swahili UI strings, stored in plain dictionaries.

A dictionary is enough for a two-language site with no plural-heavy copy and
spares the project a compilation step. Missing Swahili falls back to English.
"""

from __future__ import annotations

from flask import has_request_context, session

DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en": "English", "sw": "Kiswahili"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "site.tagline": "Fly the East African skies.",
        "site.demo_notice": "Demo project. Anga Air is fictional; no real bookings or payments.",
        "site.skip": "Skip to main content",
        "nav.book": "Book",
        "nav.about": "About",
        "nav.contact": "Contact",
        "nav.faq": "FAQ",
        "nav.menu": "Menu",
        "footer.company": "Anga Air",
        "footer.help": "Help",
        "footer.legal": "Legal",
        "footer.contact": "Get in touch",
        "footer.terms": "Terms",
        "footer.privacy": "Privacy",
        "footer.rights": "A fictional airline, built as a portfolio project by Cyril Katua.",
        "footer.about_blurb": "Connecting Nairobi with the coast, the lakes and the "
        "capitals of East Africa.",
        "common.search": "Search",
        "common.back": "Back",
        "common.continue": "Continue",
        "common.save": "Save",
        "common.cancel": "Cancel",
        "common.dismiss": "Dismiss",
        "error.not_found_title": "This page has flown off course",
        "error.not_found_body": "We could not find the page you were looking for.",
        "error.forbidden_title": "This area is restricted",
        "error.forbidden_body": "Your account does not have access to this page.",
        "error.bad_request_title": "That request could not be processed",
        "error.server_title": "Something went wrong on our side",
        "error.server_body": "Please try again in a moment.",
        "error.too_large_title": "That upload is too large",
        "error.home": "Return home",
    },
    "sw": {},
}


def current_language() -> str:
    if has_request_context():
        language = session.get("lang", DEFAULT_LANGUAGE)
        if language in LANGUAGES:
            return language
    return DEFAULT_LANGUAGE


def t(key: str, **values) -> str:
    """Translate ``key`` into the session's language, filling ``{placeholders}``."""
    text = STRINGS[current_language()].get(key) or STRINGS[DEFAULT_LANGUAGE].get(key, key)
    return text.format(**values) if values else text
