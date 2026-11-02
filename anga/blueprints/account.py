"""Customer accounts: sign-in, dashboard, travellers, miles and price watches."""

from __future__ import annotations

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from anga import clock, validators
from anga.security import login_required, safe_redirect_target
from anga.services import accounts, loyalty, watches
from anga.services.accounts import AccountError
from anga.services.watches import WatchError

bp = Blueprint("account", __name__, url_prefix="/account")


def _start_session(user) -> None:
    """Clearing first means any pre-login session cannot be fixed onto the account."""
    draft = session.get("draft_token")
    verified = session.get("verified_bookings")
    lang, currency = session.get("lang"), session.get("currency")
    session.clear()
    session["user_id"] = user["id"]
    session.permanent = True
    # A customer who signs in part-way through booking keeps their place and display choices.
    for key, value in (
        ("draft_token", draft),
        ("verified_bookings", verified),
        ("lang", lang),
        ("currency", currency),
    ):
        if value:
            session[key] = value


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("account.dashboard"))
    errors: dict[str, str] = {}
    if request.method == "POST":
        data, errors = validators.validate_registration(request.form)
        if not errors:
            try:
                accounts.register(data)
            except AccountError as error:
                errors["email"] = str(error)
            else:
                _start_session(accounts.authenticate(data["email"], data["password"]))
                flash(f"Karibu, {data['full_name'].split()[0]}! Your account is ready.", "success")
                return redirect(url_for("account.dashboard"))
    return render_template("account/register.html", errors=errors, values=request.form), (
        400 if errors else 200
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("account.dashboard"))
    error = None
    target = request.values.get("next", "")
    if request.method == "POST":
        try:
            user = accounts.authenticate(
                request.form.get("email", ""), request.form.get("password", "")
            )
        except AccountError as failure:
            error = str(failure)
        else:
            _start_session(user)
            return redirect(safe_redirect_target(target, url_for("account.dashboard")))
    return render_template(
        "account/login.html", error=error, email=request.form.get("email", ""), next_url=target
    ), (401 if error else 200)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("public.home"))


@bp.get("/")
@login_required
def dashboard():
    watches.check(g.user["id"])
    upcoming, past = accounts.trips_for(g.user["id"])
    return render_template(
        "account/dashboard.html",
        upcoming=upcoming,
        past=past,
        tier=loyalty.tier_for(g.user["miles_balance"]),
        watches=watches.for_user(g.user["id"]),
    )


@bp.route("/travellers", methods=["GET", "POST"])
@login_required
def travellers():
    errors: dict[str, str] = {}
    if request.method == "POST":
        data, errors = validators.validate_traveller(request.form)
        if not errors:
            accounts.add_traveller(g.user["id"], data)
            flash("Traveller saved.", "success")
            return redirect(url_for("account.travellers"))
    return render_template(
        "account/travellers.html",
        travellers=accounts.saved_travellers(g.user["id"]),
        errors=errors,
        values=request.form,
    ), (400 if errors else 200)


@bp.post("/travellers/<int:traveller_id>/delete")
@login_required
def delete_traveller(traveller_id: int):
    if not accounts.delete_traveller(g.user["id"], traveller_id):
        abort(404)
    flash("Traveller removed.", "info")
    return redirect(url_for("account.travellers"))


@bp.get("/miles")
@login_required
def miles():
    return render_template(
        "account/miles.html",
        tier=loyalty.tier_for(g.user["miles_balance"]),
        ledger=accounts.miles_ledger(g.user["id"]),
    )


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    errors: dict[str, str] = {}
    if request.method == "POST":
        data, errors = validators.validate_profile(request.form)
        if not errors:
            accounts.update_profile(g.user["id"], data["full_name"], data["phone"])
            flash("Profile updated.", "success")
            return redirect(url_for("account.profile"))
    return render_template("account/profile.html", errors=errors, password_errors={}), (
        400 if errors else 200
    )


@bp.post("/password")
@login_required
def change_password():
    data, errors = validators.validate_password_change(request.form)
    if not errors:
        try:
            accounts.change_password(g.user, data["current"], data["new"])
        except AccountError as error:
            errors["current_password"] = str(error)
        else:
            flash("Password changed.", "success")
            return redirect(url_for("account.profile"))
    return render_template("account/profile.html", errors={}, password_errors=errors), 400


@bp.post("/watches")
@login_required
def add_watch():
    origin = validators.clean(request.form.get("from")).upper()
    destination = validators.clean(request.form.get("to")).upper()
    day = validators.parse_date(validators.clean(request.form.get("date")))
    cabin = validators.clean(request.form.get("cabin"))
    cabin = cabin if cabin in validators.CABINS else "Economy"
    back = safe_redirect_target(request.form.get("back"), url_for("account.dashboard"))
    if day is None or day < clock.today():
        flash("Choose a future date to watch.", "error")
        return redirect(back)
    try:
        price = watches.create(g.user["id"], origin, destination, day, cabin)
    except WatchError as error:
        flash(str(error), "error")
    else:
        flash(f"Watching this trip. We will alert you if it drops below KSh {price:,}.", "success")
    return redirect(back)


@bp.post("/watches/<int:watch_id>/dismiss")
@login_required
def dismiss_watch(watch_id: int):
    if not watches.dismiss(g.user["id"], watch_id):
        abort(404)
    return redirect(url_for("account.dashboard"))
