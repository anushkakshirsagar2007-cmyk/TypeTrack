from datetime import date
from decimal import Decimal
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import current_user
from sqlalchemy import or_, func, select
from sqlalchemy.orm import selectinload, joinedload
from extensions import db
from models import Student, Course, Batch, Inquiry, InquiryFollowup, Payment, PAYMENT_MODES
from services import record_payment
from utils.helpers import (login_guard, owner_required, parse_date, parse_money, valid_phone, valid_email,
                           next_student_code, valid_aadhar, format_aadhar)

bp = Blueprint("students", __name__, url_prefix="/students")
bp.before_request(login_guard)


def _paid_sq():
    return select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.student_id == Student.id).correlate(Student).scalar_subquery()


@bp.route("/")
def index():
    a = request.args
    q = Student.query.options(selectinload(Student.payments), joinedload(Student.course), joinedload(Student.batch))
    if a.get("q", "").strip():
        like = f"%{a['q'].strip()}%"
        q = q.filter(or_(Student.name.ilike(like), Student.student_code.ilike(like), Student.phone.like(like),
                         Student.alt_phone.like(like), Student.aadhar_no.like(like)))
    if a.get("course_id", type=int):
        q = q.filter(Student.course_id == a.get("course_id", type=int))
    if a.get("batch_id", type=int):
        q = q.filter(Student.batch_id == a.get("batch_id", type=int))
    if a.get("status") in ("active", "inactive"):
        q = q.filter(Student.active == (a["status"] == "active"))
    net, paid = Student.total_fees - Student.discount, _paid_sq()
    pay = a.get("pay")
    if pay == "Paid":
        q = q.filter(paid >= net)
    elif pay == "Partial":
        q = q.filter(paid > 0, paid < net)
    elif pay == "Unpaid":
        q = q.filter(paid == 0, net > 0)
    p = q.order_by(Student.id.desc()).paginate(page=a.get("page", 1, type=int), per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("students/list.html", p=p, f=a, courses=Course.query.order_by(Course.name).all(),
                           batches=Batch.query.order_by(Batch.name).all())


def _collect(student=None):
    f = request.form
    raw_aadhar = f.get("aadhar_no", "").strip()
    d = {"name": f.get("name", "").strip(), "phone": f.get("phone", "").strip(),
         "alt_phone": f.get("alt_phone", "").strip() or None,
         "email": f.get("email", "").strip() or None,
         "address": f.get("address", "").strip() or None, "dob": parse_date(f.get("dob")),
         "aadhar_no": format_aadhar(raw_aadhar) if raw_aadhar else None,
         "admission_date": parse_date(f.get("admission_date")), "course_id": f.get("course_id", type=int),
         "batch_id": f.get("batch_id", type=int) or None, "total_fees": parse_money(f.get("total_fees")),
         "discount": parse_money(f.get("discount") or "0"), "active": f.get("active", "1") == "1"}
    e = []
    if not d["name"]:
        e.append("Student name is required.")
    if not valid_phone(d["phone"]):
        e.append("Enter a valid phone number (10 to 13 digits).")
    if d["alt_phone"] and not valid_phone(d["alt_phone"]):
        e.append("Enter a valid alternate phone number (10 to 13 digits) or leave it empty.")
    if d["email"] and not valid_email(d["email"]):
        e.append("Enter a valid email address or leave it empty.")
    if f.get("dob") and not d["dob"]:
        e.append("Date of birth is not valid.")
    if d["dob"] and d["dob"] >= date.today():
        e.append("Date of birth must be in the past.")
    if raw_aadhar and not valid_aadhar(raw_aadhar):
        e.append("Enter a valid 12-digit Aadhaar card number or leave it empty.")
    if not d["admission_date"]:
        e.append("Admission date is required.")
    course = db.session.get(Course, d["course_id"]) if d["course_id"] else None
    if not course:
        e.append("Please select a course.")
    if d["total_fees"] is None or d["total_fees"] < 0:
        e.append("Total fees must be a number (0 or more).")
    if d["discount"] is None or d["discount"] < 0:
        e.append("Discount must be a number (0 or more).")
    elif d["total_fees"] is not None and d["discount"] > d["total_fees"]:
        e.append("Discount cannot be more than total fees.")
    if d["batch_id"]:
        b = db.session.get(Batch, d["batch_id"])
        if not b:
            e.append("Selected batch does not exist.")
        else:
            if course and b.course_id != course.id:
                e.append("The selected batch is not for this course.")
            filled = Student.query.filter(Student.batch_id == b.id, Student.active.is_(True),
                                          Student.id != (student.id if student else 0)).count()
            if d["active"] and filled >= b.capacity:
                e.append(f"Batch '{b.name}' is full ({b.capacity} students).")
    if student and not e and d["total_fees"] is not None and d["discount"] is not None:
        if d["total_fees"] - d["discount"] < student.paid:
            e.append("Net fees cannot be less than the amount already paid.")
    return d, e


@bp.route("/add", methods=["GET", "POST"])
def add():
    inquiry = db.session.get(Inquiry, request.values.get("inquiry_id", type=int) or 0)
    if inquiry and inquiry.converted_student_id:
        flash("This inquiry has already been converted to a student.", "info")
        return redirect(url_for("students.profile", id=inquiry.converted_student_id))
    data = None
    if request.method == "POST":
        data, errors = _collect()
        init_amt = parse_money(request.form.get("initial_amount") or "0")
        mode = request.form.get("payment_mode", "Cash")
        if init_amt is None or init_amt < 0:
            errors.append("Amount paid now must be a number (0 or more).")
        elif data["total_fees"] is not None and data["discount"] is not None and init_amt > data["total_fees"] - data["discount"]:
            errors.append("Amount paid now cannot be more than the net fees.")
        if mode not in PAYMENT_MODES:
            errors.append("Select a valid payment mode.")
        if errors:
            for m in errors:
                flash(m, "danger")
        else:
            try:
                s = Student(student_code=next_student_code(), **data)
                db.session.add(s)
                db.session.flush()
                if inquiry:
                    inquiry.status, inquiry.converted_student_id, inquiry.follow_up_date = "Joined", s.id, None
                    db.session.add(InquiryFollowup(inquiry_id=inquiry.id, status="Joined", created_by=current_user.id,
                                                   note=f"Converted to student {s.student_code}."))
                if init_amt and init_amt > 0:
                    record_payment(s, init_amt, mode, data["admission_date"], request.form.get("reference", "").strip(),
                                   "Paid at admission", current_user)
                db.session.commit()
                flash(f"Student {s.name} added with ID {s.student_code}.", "success")
                return redirect(url_for("students.profile", id=s.id))
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Could not add student")
                flash("Could not save the student. Please try again.", "danger")
    elif inquiry:
        data = {
            "name": inquiry.name,
            "phone": inquiry.phone,
            "alt_phone": inquiry.alt_phone,
            "email": inquiry.email,
            "dob": inquiry.dob,
            "aadhar_no": inquiry.aadhar_no,
            "address": inquiry.address,
            "course_id": inquiry.course_id,
        }
    return render_template("students/form.html", s=None, d=data, inquiry=inquiry, **_form_ctx())


def _form_ctx():
    return {"courses": Course.query.filter_by(active=True).order_by(Course.name).all(),
            "batches": Batch.query.filter(Batch.status != "Completed").order_by(Batch.name).all(), "modes": PAYMENT_MODES}


@bp.route("/<int:id>/edit", methods=["GET", "POST"])
def edit(id):
    s = db.session.get(Student, id) or abort(404)
    data = None
    if request.method == "POST":
        data, errors = _collect(s)
        if errors:
            for m in errors:
                flash(m, "danger")
        else:
            for k, v in data.items():
                setattr(s, k, v)
            db.session.commit()
            flash("Student details updated.", "success")
            return redirect(url_for("students.profile", id=s.id))
    ctx = _form_ctx()
    if s.course and s.course not in ctx["courses"]:
        ctx["courses"].append(s.course)
    return render_template("students/form.html", s=s, d=data, inquiry=None, **ctx)


@bp.route("/<int:id>")
def profile(id):
    s = db.session.get(Student, id) or abort(404)
    return render_template("students/profile.html", s=s, st=s.attendance_stats(), att=s.attendance_records[:60])


@bp.route("/<int:id>/toggle", methods=["POST"])
def toggle(id):
    s = db.session.get(Student, id) or abort(404)
    if not s.active and s.batch and s.batch.filled >= s.batch.capacity:
        flash("Cannot activate: the batch is full.", "danger")
    else:
        s.active = not s.active
        db.session.commit()
        flash(f"{s.name} is now {'active' if s.active else 'inactive'}.", "success")
    return redirect(request.referrer or url_for("students.profile", id=id))


@bp.route("/<int:id>/delete", methods=["POST"])
@owner_required
def delete(id):
    s = db.session.get(Student, id) or abort(404)
    name = s.name
    db.session.delete(s)
    db.session.commit()
    flash(f"{name} and all related attendance and payment records were deleted.", "success")
    return redirect(url_for("students.index"))
