from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from sqlalchemy.orm import selectinload
from extensions import db
from models import Batch, Course
from utils.helpers import login_guard, owner_required, parse_date, parse_time

bp = Blueprint("batches", __name__, url_prefix="/batches")
bp.before_request(login_guard)
STATUSES = ["Active", "Inactive", "Completed"]


@bp.route("/")
def index():
    status = request.args.get("status", "")
    q = Batch.query.options(selectinload(Batch.students))
    if status in STATUSES:
        q = q.filter_by(status=status)
    return render_template("batches/list.html", batches=q.order_by(Batch.start_time).all(), status=status, statuses=STATUSES)


@bp.route("/<int:id>")
def view(id):
    b = db.session.get(Batch, id) or abort(404)
    return render_template("batches/view.html", b=b, students=sorted([s for s in b.students], key=lambda s: s.name))


def _save(b):
    f = request.form
    d = {"name": f.get("name", "").strip(), "course_id": f.get("course_id", type=int), "instructor": f.get("instructor", "").strip() or None,
         "start_time": parse_time(f.get("start_time")), "end_time": parse_time(f.get("end_time")),
         "start_date": parse_date(f.get("start_date")), "capacity": f.get("capacity", type=int), "status": f.get("status", "Active")}
    e = []
    if not d["name"]:
        e.append("Batch name is required.")
    if not d["course_id"] or not db.session.get(Course, d["course_id"]):
        e.append("Please select a course.")
    if not d["start_time"] or not d["end_time"]:
        e.append("Start time and end time are required.")
    elif d["end_time"] <= d["start_time"]:
        e.append("End time must be after start time.")
    if not d["start_date"]:
        e.append("Batch start date is required.")
    if not d["capacity"] or d["capacity"] < 1 or d["capacity"] > 500:
        e.append("Capacity must be between 1 and 500.")
    elif b and d["capacity"] < b.filled:
        e.append(f"Capacity cannot be lower than the {b.filled} students already in this batch.")
    if d["status"] not in STATUSES:
        e.append("Select a valid status.")
    return d, e


def _form(b):
    d = None
    if request.method == "POST":
        d, errors = _save(b)
        if errors:
            for m in errors:
                flash(m, "danger")
        else:
            b = b or Batch()
            for k, v in d.items():
                setattr(b, k, v)
            db.session.add(b)
            db.session.commit()
            flash("Batch saved.", "success")
            return redirect(url_for("batches.view", id=b.id))
    return render_template("batches/form.html", b=b, d=d, courses=Course.query.filter_by(active=True).order_by(Course.name).all(),
                           statuses=STATUSES)


@bp.route("/add", methods=["GET", "POST"])
@owner_required
def add():
    return _form(None)


@bp.route("/<int:id>/edit", methods=["GET", "POST"])
@owner_required
def edit(id):
    return _form(db.session.get(Batch, id) or abort(404))


@bp.route("/<int:id>/delete", methods=["POST"])
@owner_required
def delete(id):
    b = db.session.get(Batch, id) or abort(404)
    if b.students:
        flash("This batch still has students. Move them to another batch or mark the batch Completed instead.", "danger")
        return redirect(url_for("batches.view", id=id))
    db.session.delete(b)
    db.session.commit()
    flash("Batch deleted.", "success")
    return redirect(url_for("batches.index"))
