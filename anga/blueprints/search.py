"""Flight search results, flight details and the fare calendar."""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, render_template, request

from anga import clock, validators
from anga.services import search as search_service

bp = Blueprint("search", __name__, url_prefix="/search")


@bp.get("/")
def results() -> str:
    today = clock.today()
    query, errors = validators.validate_search(request.args, today)
    filters = validators.validate_filters(request.args)
    context = {
        "query": query,
        "errors": errors,
        "filters": filters,
        "airports": search_service.airports(),
        "args": request.args.to_dict(),
    }
    if errors:
        return render_template("search/results.html", **context), 400

    seats_needed = query["adults"] + query["children"]
    outbound = search_service.search_flights(
        query["from"],
        query["to"],
        query["depart"],
        query["cabin"],
        seats_needed,
        filters["sort"],
        filters["time"],
        filters["max_price"],
    )
    inbound = []
    if query["trip"] == "round_trip":
        inbound = search_service.search_flights(
            query["to"],
            query["from"],
            query["return"],
            query["cabin"],
            seats_needed,
            filters["sort"],
            filters["time"],
            filters["max_price"],
        )
    nearby = []
    if not any(option.cheapest for option in outbound):
        nearby = search_service.nearby_dates(
            query["from"], query["to"], query["depart"], query["cabin"], today
        )
    return render_template(
        "search/results.html",
        outbound=outbound,
        inbound=inbound,
        nearby=nearby,
        seats_needed=seats_needed,
        **context,
    )


@bp.get("/calendar")
def calendar() -> str:
    today = clock.today()
    origin = validators.clean(request.args.get("from")).upper() or search_service.HUB
    destination = validators.clean(request.args.get("to")).upper() or "MBA"
    cabin = validators.clean(request.args.get("cabin"))
    cabin = cabin if cabin in validators.CABINS else "Economy"
    month = validators.validate_month(request.args.get("month", ""), today)
    fare_calendar = search_service.fare_calendar(origin, destination, month, cabin, today)
    return render_template(
        "search/calendar.html",
        calendar=fare_calendar,
        origin=origin,
        destination=destination,
        cabin=cabin,
        airports=search_service.airports(),
        can_go_back=month > today.replace(day=1),
        can_go_forward=fare_calendar.next_month <= today + timedelta(days=180),
    )
