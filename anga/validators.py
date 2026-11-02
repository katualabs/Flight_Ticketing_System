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
MAX_EXTRA_BAGS = 3


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


def _count(form: Mapping, key: str, default: int) -> int | None:
    """A passenger count: blank means the default, anything non-numeric means None."""
    text = clean(form.get(key))
    return parse_int(text) if text else default


def validate_search(form: Mapping, today: date) -> Result:
    """Validate the flight search form."""
    errors: dict[str, str] = {}
    origin = clean(form.get("from")).upper()
    destination = clean(form.get("to")).upper()
    trip_type = clean(form.get("trip")) or "one_way"
    cabin = clean(form.get("cabin")) or "Economy"
    adults = _count(form, "adults", 1)
    children = _count(form, "children", 0)
    infants = _count(form, "infants", 0)

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

    if adults is None or children is None or infants is None:
        errors["adults"] = "Passenger numbers must be whole numbers."
    elif adults < 1 or children < 0 or infants < 0:
        errors["adults"] = "At least one adult must travel."
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


def validate_party(form: Mapping) -> Result:
    """Passenger counts submitted when a booking starts."""
    adults = _count(form, "adults", 1)
    children = _count(form, "children", 0)
    infants = _count(form, "infants", 0)
    errors: dict[str, str] = {}
    if adults is None or children is None or infants is None:
        errors["adults"] = "Passenger numbers must be whole numbers."
    elif adults < 1 or children < 0 or infants < 0:
        errors["adults"] = "At least one adult must travel."
    elif adults + children > MAX_PASSENGERS:
        errors["adults"] = f"You can book up to {MAX_PASSENGERS} seats at a time."
    elif infants > adults:
        errors["infants"] = "Each infant must travel on an adult's lap."
    return {"adults": adults, "children": children, "infants": infants}, errors


def _age_on(birth: date, day: date) -> int:
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def _validate_birth_date(kind: str, value: str, travel_date: date) -> str | None:
    """Children must be 2 to 11 and infants under 2 on the day they fly."""
    birth = parse_date(value)
    if birth is None:
        return "Enter a valid date of birth."
    if birth > travel_date:
        return "The date of birth cannot be after the flight."
    age = _age_on(birth, travel_date)
    if kind == "infant" and age >= 2:
        return "Infants must be under 2 on the day of travel."
    if kind == "child" and not 2 <= age <= 11:
        return "Children must be aged 2 to 11 on the day of travel."
    return None


def validate_passengers(
    form: Mapping, types: list[str], travel_date: date
) -> tuple[list[dict], dict, dict[str, str]]:
    """Per-passenger details and contact details from the wizard's first step."""
    errors: dict[str, str] = {}
    people = []
    for index, kind in enumerate(types):
        name = " ".join(clean(form.get(f"name_{index}")).split())
        id_number = clean(form.get(f"id_{index}"))
        birth = clean(form.get(f"dob_{index}")) if kind != "adult" else ""
        if not is_person_name(name):
            errors[f"name_{index}"] = "Enter the full name as shown on the ID document."
        if not ID_RE.match(id_number):
            errors[f"id_{index}"] = "Enter a valid ID or passport number (5-20 characters)."
        if kind != "adult":
            problem = _validate_birth_date(kind, birth, travel_date)
            if problem:
                errors[f"dob_{index}"] = problem
        people.append({"full_name": name, "id_number": id_number, "date_of_birth": birth or None})

    email = clean(form.get("email")).lower()
    phone = normalise_phone(clean(form.get("phone")))
    if not is_email(email):
        errors["email"] = "Enter a valid email address."
    if not is_phone(phone):
        errors["phone"] = "Enter a valid phone number, for example +254712345678."
    return people, {"email": email, "phone": phone}, errors


def parse_seat_choices(form: Mapping, draft: dict) -> dict[str, dict[str, str]]:
    """Seat picks keyed by segment then passenger index; blank means auto-assign."""
    choices: dict[str, dict[str, str]] = {}
    for seg_index in range(len(draft["segments"])):
        picks = {}
        for pax_index, kind in enumerate(draft["passenger_types"]):
            code = clean(form.get(f"seat_{seg_index}_{pax_index}")).upper()
            if kind != "infant" and code:
                picks[str(pax_index)] = code
        if picks:
            choices[str(seg_index)] = picks
    return choices


def parse_extras(form: Mapping, draft: dict, catalogue: list) -> dict[str, dict[str, int]]:
    """Extras per passenger, ignoring anything that is not in the catalogue."""
    by_type: dict[str, list[str]] = {}
    for extra in catalogue:
        by_type.setdefault(extra["type"], []).append(extra["code"])
    extras: dict[str, dict[str, int]] = {}
    for index, kind in enumerate(draft["passenger_types"]):
        if kind == "infant":
            continue
        chosen: dict[str, int] = {}
        bags = parse_int(form.get(f"bag_{index}"), 0) or 0
        if 0 < bags <= MAX_EXTRA_BAGS:
            chosen[by_type["bag"][0]] = bags
        meal = clean(form.get(f"meal_{index}"))
        if meal in by_type.get("meal", []):
            chosen[meal] = 1
        if form.get(f"priority_{index}"):
            chosen[by_type["priority"][0]] = 1
        if form.get(f"lounge_{index}"):
            chosen[by_type["lounge"][0]] = 1
        if chosen:
            extras[str(index)] = chosen
    return extras


def validate_mpesa_phone(value: str) -> tuple[str, str | None]:
    """Safaricom-style numbers: 07XX, 01XX, or the same with a 254 prefix."""
    phone = normalise_phone(clean(value))
    if re.fullmatch(r"(\+?254|0)[17][0-9]{8}", phone):
        return phone, None
    return phone, "Enter a Kenyan mobile number, for example 0712 345 678."


TEST_CARD_NUMBER = "4242424242424242"


def validate_demo_card(form: Mapping, today: date) -> Result:
    """Accept only the published test number, so no real card can ever be charged.

    Only the last four digits leave this function: the full number and CVC are
    never returned, logged or stored.
    """
    errors: dict[str, str] = {}
    number = re.sub(r"[\s-]", "", clean(form.get("card_number")))
    if number != TEST_CARD_NUMBER:
        errors["card_number"] = "This demo only accepts the test card 4242 4242 4242 4242."
    match = re.fullmatch(r"(0[1-9]|1[0-2])\s*/\s*([0-9]{2})", clean(form.get("card_expiry")))
    if not match:
        errors["card_expiry"] = "Enter the expiry as MM/YY."
    elif (2000 + int(match[2]), int(match[1])) < (today.year, today.month):
        errors["card_expiry"] = "That card has expired."
    if not re.fullmatch(r"[0-9]{3}", clean(form.get("card_cvc"))):
        errors["card_cvc"] = "Enter the 3-digit security code."
    if len(clean(form.get("card_name"))) < 2:
        errors["card_name"] = "Enter the name on the card."
    return {"last4": number[-4:] if not errors else None}, errors


def validate_contact(form: Mapping) -> Result:
    data = {
        "full_name": clean(form.get("full_name")),
        "email": clean(form.get("email")).lower(),
        "subject": clean(form.get("subject")),
        "body": clean(form.get("body")),
    }
    errors: dict[str, str] = {}
    if not 2 <= len(data["full_name"]) <= MAX_NAME:
        errors["full_name"] = "Enter your name."
    if not is_email(data["email"]):
        errors["email"] = "Enter a valid email address."
    if not 3 <= len(data["subject"]) <= 120:
        errors["subject"] = "Enter a subject of 3 to 120 characters."
    if not 10 <= len(data["body"]) <= 4000:
        errors["body"] = "Enter a message of 10 to 4,000 characters."
    return data, errors


def validate_flight_number(value: str) -> str | None:
    number = clean(value).upper().replace(" ", "")
    return number if FLIGHT_NUMBER_RE.match(number) else None


PASSWORD_MIN_LENGTH = 10


def password_problem(password: str) -> str | None:
    """Length matters most, but demo accounts should still model good practice."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Use at least {PASSWORD_MIN_LENGTH} characters."
    if len(password) > 128:
        return "Use at most 128 characters."
    checks = (
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    )
    if not all(checks):
        return "Include upper and lower case letters, a number and a symbol."
    return None


def validate_registration(form: Mapping) -> Result:
    full_name = " ".join(clean(form.get("full_name")).split())
    email = clean(form.get("email")).lower()
    phone = normalise_phone(clean(form.get("phone")))
    password = str(form.get("password") or "")
    errors: dict[str, str] = {}
    if not is_person_name(full_name):
        errors["full_name"] = "Enter your first and last name."
    if not is_email(email):
        errors["email"] = "Enter a valid email address."
    if phone and not is_phone(phone):
        errors["phone"] = "Enter a valid phone number, for example +254712345678."
    problem = password_problem(password)
    if problem:
        errors["password"] = problem
    elif password != form.get("confirm_password"):
        errors["confirm_password"] = "The passwords do not match."
    data = {"full_name": full_name, "email": email, "phone": phone or None, "password": password}
    return data, errors


def validate_profile(form: Mapping) -> Result:
    full_name = " ".join(clean(form.get("full_name")).split())
    phone = normalise_phone(clean(form.get("phone")))
    errors: dict[str, str] = {}
    if not is_person_name(full_name):
        errors["full_name"] = "Enter your first and last name."
    if phone and not is_phone(phone):
        errors["phone"] = "Enter a valid phone number, for example +254712345678."
    return {"full_name": full_name, "phone": phone or None}, errors


def validate_password_change(form: Mapping) -> Result:
    new = str(form.get("password") or "")
    errors: dict[str, str] = {}
    problem = password_problem(new)
    if problem:
        errors["password"] = problem
    elif new != form.get("confirm_password"):
        errors["confirm_password"] = "The passwords do not match."
    return {"current": str(form.get("current_password") or ""), "new": new}, errors


def validate_traveller(form: Mapping) -> Result:
    full_name = " ".join(clean(form.get("full_name")).split())
    id_number = clean(form.get("id_number"))
    birth = clean(form.get("date_of_birth"))
    errors: dict[str, str] = {}
    if not is_person_name(full_name):
        errors["full_name"] = "Enter the full name as shown on the ID document."
    if not ID_RE.match(id_number):
        errors["id_number"] = "Enter a valid ID or passport number (5-20 characters)."
    if birth and parse_date(birth) is None:
        errors["date_of_birth"] = "Enter a valid date."
    return {"full_name": full_name, "id_number": id_number, "date_of_birth": birth or None}, errors
