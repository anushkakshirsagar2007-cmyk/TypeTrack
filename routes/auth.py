from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from models import User

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip().lower()).first()
        if user and user.active and user.check_password(request.form.get("password", "")):
            login_user(user, remember=False)
            nxt = request.args.get("next", "")
            if nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for("dashboard.index"))
        flash("Wrong username or password. Please try again.", "danger")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
