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
        "nav.calendar": "Fare calendar",
        "cabin.Economy": "Economy",
        "cabin.Business": "Business",
        "cabin.First": "First",
        "day.Mon": "Mon",
        "day.Tue": "Tue",
        "day.Wed": "Wed",
        "day.Thu": "Thu",
        "day.Fri": "Fri",
        "day.Sat": "Sat",
        "day.Sun": "Sun",
        "fare.bags_0": "Cabin bag only",
        "fare.bags_1": "1 checked bag",
        "fare.bags_2": "2 checked bags",
        "fare.no_changes": "No changes",
        "fare.change_fee": "Change for {fee}",
        "fare.free_changes": "Free changes",
        "fare.no_refund": "No refund",
        "fare.part_refund": "50% refund",
        "fare.full_refund": "Fully refundable",
        "home.title": "Book flights across East Africa",
        "home.eyebrow": "Karibu ndani · Welcome aboard",
        "home.lead": "From Nairobi to the coast, the lakes and the capitals of the region.",
        "home.destinations": "Where to next?",
        "home.destinations_sub": "Live lowest fares from Nairobi over the next 30 days.",
        "home.from_price": "from",
        "home.deals": "Lowest fares this fortnight",
        "home.deals_sub": "The cheapest seats leaving Nairobi in the next 14 days.",
        "home.network": "Our network",
        "home.network_sub": "Twelve airports across four countries, all connected through Nairobi.",
        "home.map_hint": "Hover or tab to a route to see its fare.",
        "home.promo_title": "Karibu! Your first trip costs less",
        "home.promo_body": "Use KARIBU10 for 10% off, or COAST2026 for KSh 1,500 off the coast.",
        "home.why": "Why fly with Anga Air",
        "home.why_flex": "Fares that fit the trip",
        "home.why_flex_body": "Choose Lite, Classic or Flex, and see exactly what each one "
        "includes before you pay.",
        "home.why_miles": "Anga Miles on every trip",
        "home.why_miles_body": "Earn a mile for every KSh 100 you spend, and climb to Silver and "
        "Gold.",
        "home.why_mpesa": "Pay the way you already do",
        "home.why_mpesa_body": "M-Pesa, card or pay later. It is all simulated here, and it "
        "behaves just like the real thing.",
        "search.trip_type": "Trip type",
        "search.one_way": "One way",
        "search.round_trip": "Round trip",
        "search.cabin": "Cabin",
        "search.from": "From",
        "search.to": "To",
        "search.choose_airport": "City or airport",
        "search.swap": "Swap origin and destination",
        "search.depart": "Depart",
        "search.return": "Return",
        "search.adults": "Adults",
        "search.adults_hint": "12+ years",
        "search.children": "Children",
        "search.children_hint": "2–11 years",
        "search.infants": "Infants",
        "search.infants_hint": "Under 2, on lap",
        "search.submit": "Search flights",
        "search.results_title": "Flight results",
        "search.fix_errors": "Please correct the details below to see flights.",
        "search.party_one": "1 seat",
        "search.party": "{seats} seats",
        "search.edit": "Change search",
        "search.filters": "Filter and sort",
        "search.sort_by": "Sort by",
        "search.sort_price": "Lowest price",
        "search.sort_departure": "Departure time",
        "search.sort_duration": "Shortest flight",
        "search.time_of_day": "Time of day",
        "search.any_time": "Any time",
        "search.time_morning": "Morning (before 12:00)",
        "search.time_afternoon": "Afternoon (12:00–17:00)",
        "search.time_evening": "Evening (after 17:00)",
        "search.max_price": "Maximum price (KSh)",
        "search.apply_filters": "Apply filters",
        "search.see_calendar": "See the fare calendar",
        "search.outbound": "Outbound",
        "search.return_flights": "Return",
        "search.direct": "Direct",
        "search.seats_left": "{count} left",
        "search.sold_out": "Sold out",
        "search.none_title": "No flights match this search",
        "search.none_body": "Try a nearby date or clear your filters.",
        "search.none_return_title": "No return flights match",
        "search.none_return_body": "Try another return date or clear your filters.",
        "search.nearby": "Fares on nearby dates",
        "calendar.title": "Fare calendar",
        "calendar.subtitle": "The cheapest fare for every day of the month, at a glance.",
        "calendar.empty_title": "No fares for this month",
        "calendar.empty_body": "We have no flights on this route and month yet. Try another.",
        "calendar.range": "This month: {low} to {high}",
        "calendar.cheaper": "Cheaper",
        "calendar.pricier": "Pricier",
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
