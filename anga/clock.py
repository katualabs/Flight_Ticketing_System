"""The one place the app asks what time it is.

Every rule that depends on time (check-in windows, hold expiry, the rolling
schedule) goes through here so tests can freeze the clock. Times are naive and
expressed in "network time" (East Africa Time, UTC+3), the airline's operating
clock. Flight times are stored in the local time of their airport, and the few
airports outside EAT are converted using the offsets below.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

NETWORK_OFFSET_MINUTES = 180

# Fixed offsets are correct here: none of the network's countries observe DST,
# and this avoids requiring tzdata on Windows.
TIMEZONE_OFFSETS = {
    "Africa/Nairobi": 180,
    "Africa/Dar_es_Salaam": 180,
    "Africa/Kampala": 180,
    "Africa/Kigali": 120,
}

_frozen: datetime | None = None


def freeze(moment: datetime | None) -> None:
    """Pin the clock to ``moment``; pass None to resume real time."""
    global _frozen
    _frozen = moment


def now() -> datetime:
    if _frozen is not None:
        return _frozen
    utc_now = datetime.now(UTC).replace(tzinfo=None)
    return utc_now + timedelta(minutes=NETWORK_OFFSET_MINUTES)


def today() -> date:
    return now().date()


def timestamp() -> str:
    """Current time as the ISO string format stored in the database."""
    return now().isoformat(timespec="seconds")


def local_to_network(local: datetime, tz_name: str) -> datetime:
    """Convert an airport-local time to network time."""
    offset = TIMEZONE_OFFSETS.get(tz_name, NETWORK_OFFSET_MINUTES)
    return local + timedelta(minutes=NETWORK_OFFSET_MINUTES - offset)


def local_to_utc(local: datetime, tz_name: str) -> datetime:
    """Convert an airport-local time to UTC, as calendar files require."""
    offset = TIMEZONE_OFFSETS.get(tz_name, NETWORK_OFFSET_MINUTES)
    return local - timedelta(minutes=offset)
