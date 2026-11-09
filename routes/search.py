from flask import Blueprint, render_template, request, jsonify, url_for
from sqlalchemy import or_
from models import Student, Inquiry
from utils.helpers import login_guard

bp = Blueprint("search", __name__)
bp.before_request(login_guard)


def _find(q, limit):
    like = f"%{q}%"
    studs = Student.query.filter(or_(
        Student.name.ilike(like),
        Student.student_code.ilike(like),
        Student.gr_no.ilike(like),
        Student.phone.like(like),
        Student.alt_phone.like(like),
        Student.aadhar_no.like(like),
    )).order_by(Student.name).limit(limit).all()
    inqs = Inquiry.query.filter(or_(
        Inquiry.name.ilike(like),
        Inquiry.phone.like(like),
        Inquiry.alt_phone.like(like),
        Inquiry.aadhar_no.like(like),
    )).order_by(Inquiry.id.desc()).limit(limit).all()
    return studs, inqs


@bp.route("/search")
def page():
    q = request.args.get("q", "").strip()
    studs, inqs = _find(q, 50) if q else ([], [])
    return render_template("search.html", q=q, studs=studs, inqs=inqs)


@bp.route("/api/search")
def api():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    studs, inqs = _find(q, 5)
    return jsonify(
        [{"type": "Student", "title": s.name, "sub": f"{s.student_code} · {s.phone}", "url": url_for("students.profile", id=s.id)} for s in studs] +
        [{"type": "Inquiry", "title": i.name, "sub": f"{i.status} · {i.phone}", "url": url_for("inquiries.view", id=i.id)} for i in inqs])


@bp.route("/notifications")
def notifications():
    from services import due_followups, students_with_balance, upcoming_followups
    return render_template("notifications.html", due=due_followups(), upcoming=upcoming_followups(7),
                           overdue=students_with_balance(overdue_only=True))
