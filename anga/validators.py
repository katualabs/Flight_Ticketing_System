"""Input validation. Pure functions returning ``(clean_data, errors)``.

Nothing here touches Flask or the database, so every rule is easy to test, and
blueprints can pass the same dict back to a template to redisplay the form.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime

Result = tuple[dict, dict[str, str]]

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$")
PHONE_RE = re.compile(r"^\+?[0-9]{9,15}$")
NAME_RE = re.compile(r"^[^\W\d_][^\W\d_ .'\-]*(?:[ .'\-]+[^\W\d_]+)*\.?$")
ID_RE = re.compile(r"^[A-Za-z0-9\-]{5,20}$")
AIRPORT_RE = re.compile(r"^[A-Z]{3}$")
FLIGHT_NUMBER_RE = re.compile(r"^AN[0-9]{1,4}$")
REFERENCE_RE = re.compile(r"^[A-Z0-9]{8}$")
TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
MONTH_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
PROMO_RE = re.compile(r"^[A-Z0-9]{3,20}$")

CABINS = ("Economy", "Business", "First")
FAMILIES = ("Lite", "Classic", "Flex")
SORTS = ("price", "departure", "duration")
TIMES_OF_DAY = ("morning", "afternoon", "evening")
MAX_PASSENGERS = 9
MAX_NAME = 100


def clean(value: object) -> str:
    return str(value if value is not None else "").strip()


def is_email(value: str) -> bool:
    return len(value) <= 254 and bool(EMAIL_RE.match(value))


def normalise_phone(value: str) -> str:
    return re.sub(r"[\s\-()]", "", value)


def is_phone(value: str) -> bool:
    return bool(PHONE_RE.match(normalise_phone(value)))


def is_person_name(value: str) -> bool:
    return 2 <= len(value) <= MAX_NAME and bool(NAME_RE.match(value)) and " " in value


def parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def parse_int(value: object, default: int | None = None) -> int | None:
    try:
        return int(clean(value))
    except ValueError:
        return default


def validate_search(form: Mapping, today: date) -> Result:
    """Validate the flight search form."""
    errors: dict[str, str] = {}
    origin = clean(form.get("from")).upper()
    destination = clean(form.get("to")).upper()
    trip_type = clean(form.get("trip")) or "one_way"
    cabin = clean(form.get("cabin")) or "Economy"
    adults = parse_int(form.get("adults"), 1)
    children = parse_int(form.get("children"), 0)
    infants = parse_int(form.get("infants"), 0)

    if not AIRPORT_RE.match(origin):
        errors["from"] = "Choose where you are flying from."
    if not AIRPORT_RE.match(destination):
        errors["to"] = "Choose where you are flying to."
    if "from" not in errors and origin == destination:
        errors["to"] = "Origin and destination must be different."
    if trip_type not in ("one_way", "round_trip"):
        errors["trip"] = "Choose one-way or round trip."
    if cabin not in CABINS:
        errors["cabin"] = "Choose a valid cabin."

    depart = parse_date(clean(form.get("depart")))
    if depart is None:
        errors["depart"] = "Choose a departure date."
    elif depart < today:
        errors["depart"] = "The departure date cannot be in the past."

    return_date = None
    if trip_type == "round_trip":
        return_date = parse_date(clean(form.get("return")))
        if return_date is None:
            errors["return"] = "Choose a return date."
        elif depart and return_date < depart:
            errors["return"] = "The return date cannot be before departure."

    if adults is None or adults < 1:
        errors["adults"] = "At least one adult must travel."
    elif children is None or infants is None or children < 0 or infants < 0:
        errors["adults"] = "Passenger numbers must be whole numbers."
    elif adults + children > MAX_PASSENGERS:
        errors["adults"] = f"You can book up to {MAX_PASSENGERS} seats at a time."
    elif infants > adults:
        errors["infants"] = "Each infant must travel on an adult's lap."

    data = {
        "from": origin,
        "to": destination,
        "trip": trip_type,
        "cabin": cabin,
        "depart": depart,
        "return": return_date,
        "adults": adults,
        "children": children,
        "infants": infants,
    }
    return data, errors


def validate_filters(args: Mapping) -> dict:
    """Result filters are optional, so bad values are ignored rather than reported."""
    sort = clean(args.get("sort"))
    time_of_day = clean(args.get("time"))
    max_price = parse_int(args.get("max_price"))
    return {
        "sort": sort if sort in SORTS else "price",
        "time": time_of_day if time_of_day in TIMES_OF_DAY else "",
        "max_price": max_price if max_price and max_price > 0 else None,
    }


def validate_month(value: str, today: date) -> date:
    """First day of the requested month, defaulting to the current one."""
    text = clean(value)
    if MONTH_RE.match(text):
        return date(int(text[:4]), int(text[5:7]), 1)
    return today.replace(day=1)
