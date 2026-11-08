from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from extensions import db
from models import Attendance, Batch, Student, ATTENDANCE_STATUSES
from utils.helpers import login_guard, parse_date

bp = Blueprint("attendance", __name__, url_prefix="/attendance")
bp.before_request(login_guard)


@bp.route("/", methods=["GET", "POST"])
def mark():
    batch_id = request.values.get("batch_id", type=int)
    d = parse_date(request.values.get("date")) or date.today()
    batches = Batch.query.filter_by(status="Active").order_by(Batch.start_time).all()
    batch = next((b for b in batches if b.id == batch_id), None)
    students, existing = [], {}
    if batch:
        students = Student.query.options(selectinload(Student.attendance_records)) \
            .filter_by(batch_id=batch.id, active=True).order_by(Student.name).all()
        ids = [s.id for s in students]
        if ids:
            existing = {a.student_id: a for a in Attendance.query.filter(Attendance.date == d, Attendance.student_id.in_(ids))}
    locked = bool(existing) and not current_user.is_owner and d != date.today()

    if request.method == "POST" and batch:
        if d > date.today():
            flash("You cannot mark attendance for a future date.", "danger")
        elif locked:
            flash("Attendance for a past date can only be edited by the owner.", "danger")
        else:
            saved = 0
            try:
                for s in students:
                    st = request.form.get(f"status_{s.id}")
                    if st not in ATTENDANCE_STATUSES:
                        continue
                    rec = existing.get(s.id)
                    if rec:                      # one record per student per day: update, never duplicate
                        rec.status, rec.marked_by = st, current_user.id
                    else:
                        db.session.add(Attendance(student_id=s.id, batch_id=batch.id, date=d, status=st, marked_by=current_user.id))
                    saved += 1
                db.session.commit()
                flash(f"Attendance saved for {saved} student(s).", "success") if saved else flash("Nothing to save: mark at least one student.", "warning")
            except IntegrityError:
                db.session.rollback()
                flash("Attendance for this date was already saved by someone else. Please reload.", "danger")
            return redirect(url_for("attendance.mark", batch_id=batch.id, date=d.isoformat()))

    counts = {k: sum(1 for a in existing.values() if a.status == k) for k in ATTENDANCE_STATUSES}
    return render_template("attendance/mark.html", batches=batches, batch=batch, d=d, students=students, existing=existing,
                           locked=locked, counts=counts, stats={s.id: s.attendance_stats() for s in students})
