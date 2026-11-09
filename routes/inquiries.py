from datetime import date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import current_user
from sqlalchemy import or_
from extensions import db
from models import Inquiry, InquiryFollowup, Course, INQUIRY_STATUSES, INQUIRY_SOURCES
from utils.helpers import login_guard, owner_required, parse_date, valid_phone, valid_email, wa_link, valid_aadhar, format_aadhar

bp = Blueprint("inquiries", __name__, url_prefix="/inquiries")
bp.before_request(login_guard)
TIMINGS = ["Morning", "Afternoon", "Evening", "Any time"]


@bp.route("/")
def index():
    a = request.args
    q = Inquiry.query
    if a.get("q", "").strip():
        like = f"%{a['q'].strip()}%"
        q = q.filter(or_(Inquiry.name.ilike(like), Inquiry.phone.like(like), Inquiry.alt_phone.like(like), Inquiry.aadhar_no.like(like)))
    if a.get("status") in INQUIRY_STATUSES:
        q = q.filter(Inquiry.status == a["status"])
    if a.get("source") in INQUIRY_SOURCES:
        q = q.filter(Inquiry.source == a["source"])
    if a.get("course_id", type=int):
        q = q.filter(Inquiry.course_id == a.get("course_id", type=int))
    if a.get("due") == "1":
        q = q.filter(Inquiry.follow_up_date <= date.today(), Inquiry.status.notin_(["Joined", "Not Interested"]))
    p = q.order_by(Inquiry.id.desc()).paginate(page=a.get("page", 1, type=int), per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("inquiries/list.html", p=p, f=a, statuses=INQUIRY_STATUSES, sources=INQUIRY_SOURCES,
                           courses=Course.query.order_by(Course.name).all())


def _collect():
    f = request.form
    raw_aadhar = f.get("aadhar_no", "").strip()
    d = {"name": f.get("name", "").strip(), "phone": f.get("phone", "").strip(),
         "alt_phone": f.get("alt_phone", "").strip() or None,
         "email": f.get("email", "").strip() or None,
         "dob": parse_date(f.get("dob")),
         "aadhar_no": format_aadhar(raw_aadhar) if raw_aadhar else None,
         "address": f.get("address", "").strip() or None,
         "course_id": f.get("course_id", type=int) or None, "preferred_timing": f.get("preferred_timing") or None,
         "inquiry_date": parse_date(f.get("inquiry_date")), "source": f.get("source") or None,
         "remarks": f.get("remarks", "").strip() or None, "follow_up_date": parse_date(f.get("follow_up_date")),
         "status": f.get("status", "New")}
    e = []
    if not d["name"]:
        e.append("Name is required.")
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
    if not d["inquiry_date"]:
        e.append("Inquiry date is required.")
    if f.get("follow_up_date") and not d["follow_up_date"]:
        e.append("Follow-up date is not valid.")
    if d["status"] not in INQUIRY_STATUSES:
        e.append("Select a valid status.")
    if d["course_id"] and not db.session.get(Course, d["course_id"]):
        e.append("Selected course does not exist.")
    return d, e


def _ctx():
    return {"courses": Course.query.filter_by(active=True).order_by(Course.name).all(), "statuses": INQUIRY_STATUSES,
            "sources": INQUIRY_SOURCES, "timings": TIMINGS}


@bp.route("/add", methods=["GET", "POST"])
def add():
    d = None
    if request.method == "POST":
        d, errors = _collect()
        if errors:
            for m in errors:
                flash(m, "danger")
        else:
            i = Inquiry(created_by=current_user.id, **d)
            db.session.add(i)
            db.session.commit()
            flash("Inquiry saved.", "success")
            return redirect(url_for("inquiries.view", id=i.id))
    return render_template("inquiries/form.html", i=None, d=d, **_ctx())


@bp.route("/<int:id>/edit", methods=["GET", "POST"])
def edit(id):
    i = db.session.get(Inquiry, id) or abort(404)
    d = None
    if request.method == "POST":
        d, errors = _collect()
        if errors:
            for m in errors:
                flash(m, "danger")
        else:
            for k, v in d.items():
                setattr(i, k, v)
            db.session.commit()
            flash("Inquiry updated.", "success")
            return redirect(url_for("inquiries.view", id=i.id))
    return render_template("inquiries/form.html", i=i, d=d, **_ctx())


@bp.route("/<int:id>")
def view(id):
    i = db.session.get(Inquiry, id) or abort(404)
    wa = wa_link(i.phone, f"Hello {i.name}, thank you for your interest in our typing course. Can we help you with admission?")
    return render_template("inquiries/view.html", i=i, statuses=INQUIRY_STATUSES, wa=wa)


@bp.route("/<int:id>/followup", methods=["POST"])
def followup(id):
    i = db.session.get(Inquiry, id) or abort(404)
    note = request.form.get("note", "").strip()
    status = request.form.get("status", i.status)
    nxt = parse_date(request.form.get("next_follow_up"))
    if not note:
        flash("Please write a short note about the follow-up.", "danger")
    elif status not in INQUIRY_STATUSES or status == "Joined" and not i.converted_student_id:
        flash("To mark as Joined, use the 'Convert to student' button.", "danger")
    else:
        db.session.add(InquiryFollowup(inquiry_id=i.id, note=note, status=status, next_follow_up=nxt, created_by=current_user.id))
        i.status = status
        i.follow_up_date = nxt if i.is_open else None
        db.session.commit()
        flash("Follow-up saved.", "success")
    return redirect(url_for("inquiries.view", id=i.id))


@bp.route("/<int:id>/delete", methods=["POST"])
@owner_required
def delete(id):
    i = db.session.get(Inquiry, id) or abort(404)
    db.session.delete(i)
    db.session.commit()
    flash("Inquiry deleted.", "success")
    return redirect(url_for("inquiries.index"))
