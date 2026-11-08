import re
from uuid import uuid4
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import current_user
from werkzeug.utils import secure_filename
from extensions import db
from models import Institute, User, Course
from utils.helpers import login_guard, owner_required, parse_money, valid_email, valid_phone
from utils.uploads import save_upload

bp = Blueprint("settings", __name__, url_prefix="/settings")
bp.before_request(login_guard)
ALLOWED = {"png", "jpg", "jpeg", "webp"}


def _valid_institute_phone(value):
    numbers = [number.strip() for number in re.split(r"[,;&]+", value or "") if number.strip()]
    return bool(numbers) and all(valid_phone(number) for number in numbers)


def _pw_errors(pw):
    return [] if len(pw) >= 8 and any(c.isdigit() for c in pw) and any(c.isalpha() for c in pw) \
        else ["Password must be at least 8 characters and include letters and numbers."]


@bp.route("/institute", methods=["GET", "POST"])
@owner_required
def institute():
    inst = Institute.query.first() or Institute()
    if request.method == "POST":
        f = request.form
        errors = []
        if not f.get("name", "").strip():
            errors.append("Institute name is required.")
        if f.get("phone", "").strip() and not _valid_institute_phone(f["phone"]):
            errors.append("Enter valid contact numbers (10 to 13 digits each, separated by commas).")
        if f.get("email") and not valid_email(f["email"]):
            errors.append("Enter a valid email address.")
        file = request.files.get("logo")
        fname = None
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in ALLOWED:
                errors.append("Logo must be a PNG, JPG or WEBP image.")
            else:
                fname = f"logo_{uuid4().hex[:8]}.{ext}"
        if errors:
            for m in errors:
                flash(m, "danger")
        else:
            for k in ("name", "owner_name", "address", "phone", "email", "website", "receipt_note"):
                setattr(inst, k, f.get(k, "").strip() or (inst.name if k == "name" else None))
            if fname:
                save_upload(file, fname)
                inst.logo = fname
            db.session.add(inst)
            db.session.commit()
            flash("Institute details saved.", "success")
            return redirect(url_for("settings.institute"))
    return render_template("settings/institute.html", i=inst)


@bp.route("/users", methods=["GET", "POST"])
@owner_required
def users():
    edit = db.session.get(User, request.args.get("edit", type=int) or 0)
    if request.method == "POST":
        f = request.form
        u = db.session.get(User, f.get("id", type=int) or 0) or User()
        new = u.id is None
        name, username, role = f.get("name", "").strip(), f.get("username", "").strip().lower(), f.get("role")
        pw, active = f.get("password", ""), f.get("active") == "1"
        errors = []
        if not name or not username:
            errors.append("Name and username are required.")
        if role not in ("owner", "receptionist"):
            errors.append("Select a role.")
        other = User.query.filter_by(username=username).first()
        if other and other.id != u.id:
            errors.append("This username is already taken.")
        if new or pw:
            errors += _pw_errors(pw)
        if not new and u.id == current_user.id and (role != "owner" or not active):
            errors.append("You cannot remove your own owner access or deactivate yourself.")
        if not new and u.role == "owner" and (role != "owner" or not active) and User.query.filter_by(role="owner", active=True).count() <= 1:
            errors.append("At least one active owner is required.")
        if errors:
            for m in errors:
                flash(m, "danger")
            return render_template("settings/users.html", users=User.query.order_by(User.name).all(), edit=u if not new else None)
        u.name, u.username, u.role, u.active = name, username, role, active
        if pw:
            u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        flash("User saved.", "success")
        return redirect(url_for("settings.users"))
    return render_template("settings/users.html", users=User.query.order_by(User.name).all(), edit=edit)


@bp.route("/courses", methods=["GET", "POST"])
@owner_required
def courses():
    edit = db.session.get(Course, request.args.get("edit", type=int) or 0)
    if request.method == "POST":
        f = request.form
        c = db.session.get(Course, f.get("id", type=int) or 0) or Course()
        name, fees, months = f.get("name", "").strip(), parse_money(f.get("fees")), f.get("duration_months", type=int)
        errors = []
        if not name:
            errors.append("Course name is required.")
        other = Course.query.filter(Course.name.ilike(name)).first() if name else None
        if other and other.id != c.id:
            errors.append("A course with this name already exists.")
        if fees is None or fees < 0:
            errors.append("Fees must be a number (0 or more).")
        if not months or months < 1:
            errors.append("Duration must be at least 1 month.")
        if errors:
            for m in errors:
                flash(m, "danger")
            return render_template("settings/courses.html", courses=Course.query.order_by(Course.name).all(), edit=c if c.id else None)
        c.name, c.fees, c.duration_months, c.active = name, fees, months, f.get("active", "1") == "1"
        db.session.add(c)
        db.session.commit()
        flash("Course saved.", "success")
        return redirect(url_for("settings.courses"))
    return render_template("settings/courses.html", courses=Course.query.order_by(Course.name).all(), edit=edit)


@bp.route("/courses/<int:id>/delete", methods=["POST"])
@owner_required
def course_delete(id):
    c = db.session.get(Course, id) or abort(404)
    if c.students or c.batches:
        c.active = False
        db.session.commit()
        flash("This course is used by students or batches, so it was deactivated instead of deleted.", "warning")
    else:
        db.session.delete(c)
        db.session.commit()
        flash("Course deleted.", "success")
    return redirect(url_for("settings.courses"))


@bp.route("/password", methods=["GET", "POST"])
def password():
    if request.method == "POST":
        cur, new, conf = (request.form.get(k, "") for k in ("current", "new", "confirm"))
        errors = []
        if not current_user.check_password(cur):
            errors.append("Your current password is wrong.")
        if new != conf:
            errors.append("New password and confirmation do not match.")
        errors += _pw_errors(new)
        if errors:
            for m in errors:
                flash(m, "danger")
        else:
            current_user.set_password(new)
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("settings.password"))
    return render_template("settings/password.html")
