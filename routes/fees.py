from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, current_app
from flask_login import current_user
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload
from extensions import db
from models import Payment, Student, Institute, PAYMENT_MODES
from services import record_payment, students_with_balance
from utils.exports import make_receipt_pdf
from utils.helpers import login_guard, owner_required, parse_date, parse_money, wa_link

bp = Blueprint("fees", __name__, url_prefix="/fees")
bp.before_request(login_guard)


@bp.route("/")
def index():
    a = request.args
    q = Payment.query.join(Student).options(joinedload(Payment.student))
    if a.get("q", "").strip():
        like = f"%{a['q'].strip()}%"
        q = q.filter(or_(Student.name.ilike(like), Student.student_code.ilike(like), Payment.receipt_no.ilike(like),
                         Payment.reference.ilike(like)))
    if a.get("mode") in PAYMENT_MODES:
        q = q.filter(Payment.mode == a["mode"])
    if parse_date(a.get("start")):
        q = q.filter(Payment.payment_date >= parse_date(a["start"]))
    if parse_date(a.get("end")):
        q = q.filter(Payment.payment_date <= parse_date(a["end"]))
    total = q.with_entities(func.coalesce(func.sum(Payment.amount), 0)).scalar()
    p = q.order_by(Payment.payment_date.desc(), Payment.id.desc()).paginate(
        page=a.get("page", 1, type=int), per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("fees/list.html", p=p, f=a, total=total, modes=PAYMENT_MODES)


@bp.route("/add", methods=["GET", "POST"])
def add():
    students = Student.query.filter_by(active=True).order_by(Student.name).all()
    selected = request.values.get("student_id", type=int)
    if request.method == "POST":
        s = db.session.get(Student, selected or 0)
        amount, pdate = parse_money(request.form.get("amount")), parse_date(request.form.get("payment_date"))
        mode = request.form.get("mode")
        errors = []
        if not s:
            errors.append("Please select a student.")
        if amount is None or amount <= 0:
            errors.append("Enter an amount greater than 0.")
        elif s and amount > s.balance:
            errors.append(f"Amount is more than the pending balance (Rs. {s.balance:,.2f}).")
        if not pdate or pdate > date.today():
            errors.append("Enter a valid payment date (not in the future).")
        if mode not in PAYMENT_MODES:
            errors.append("Select a payment mode.")
        if mode in ("UPI", "Online", "Bank Transfer") and not request.form.get("reference", "").strip():
            errors.append("Please enter the transaction reference for non-cash payments.")
        if errors:
            for m in errors:
                flash(m, "danger")
        else:
            p = record_payment(s, amount, mode, pdate, request.form.get("reference", "").strip(),
                               request.form.get("note", "").strip(), current_user)
            db.session.commit()
            flash(f"Payment of Rs. {amount:,.2f} received. Receipt {p.receipt_no} is ready.", "success")
            return redirect(url_for("fees.receipt_page", id=p.id))
    return render_template("fees/form.html", students=students, selected=selected, modes=PAYMENT_MODES)


@bp.route("/<int:id>/receipt")
def receipt_page(id):
    p = db.session.get(Payment, id) or abort(404)
    return render_template("fees/receipt.html", p=p)


@bp.route("/<int:id>/receipt.pdf")
def receipt_pdf(id):
    p = db.session.get(Payment, id) or abort(404)
    buf = make_receipt_pdf(p, Institute.query.first())
    return send_file(buf, mimetype="application/pdf", download_name=f"{p.receipt_no}.pdf",
                     as_attachment=request.args.get("download") == "1")


@bp.route("/<int:id>/delete", methods=["POST"])
@owner_required
def delete(id):
    p = db.session.get(Payment, id) or abort(404)
    sid = p.student_id
    db.session.delete(p)
    db.session.commit()
    flash("Payment deleted. The student's balance has been updated.", "success")
    return redirect(request.referrer or url_for("students.profile", id=sid))


@bp.route("/pending")
def pending():
    overdue_only = request.args.get("overdue") == "1"
    studs = students_with_balance(overdue_only)
    inst = Institute.query.first()
    rows = [(s, wa_link(s.phone, f"Dear {s.name}, your pending fee balance at {inst.name if inst else 'our institute'} "
                                  f"is Rs. {s.balance:,.0f}. Please pay at your earliest convenience. Thank you.")) for s in studs]
    return render_template("fees/pending.html", rows=rows, total=sum(s.balance for s in studs), overdue_only=overdue_only)
