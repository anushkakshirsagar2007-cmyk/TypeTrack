from collections import OrderedDict
from datetime import date
from flask import Blueprint, render_template
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from extensions import db
from models import Student, Inquiry, Payment, Attendance
from services import due_followups, upcoming_followups, students_with_balance
from utils.helpers import login_guard

bp = Blueprint("dashboard", __name__)
bp.before_request(login_guard)


def _last_months(n=6):
    t = date.today()
    y, m = t.year, t.month
    out = []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


@bp.route("/")
def index():
    t = date.today()
    pending = students_with_balance()
    stats = {
        "total": Student.query.count(),
        "active": Student.query.filter_by(active=True).count(),
        "present_today": Attendance.query.filter_by(date=t, status="Present").count(),
        "marked_today": Attendance.query.filter_by(date=t).count(),
        "new_inquiries": Inquiry.query.filter_by(status="New").count(),
        "collected": db.session.query(func.coalesce(func.sum(Payment.amount), 0)).scalar(),
        "pending": sum(s.balance for s in pending),
        "pending_count": len(pending),
    }
    months = _last_months()
    adm = OrderedDict((m, 0) for m in months)
    fee = OrderedDict((m, 0.0) for m in months)
    first = date(months[0][0], months[0][1], 1)
    for (d,) in db.session.query(Student.admission_date).filter(Student.admission_date >= first):
        if (d.year, d.month) in adm:
            adm[(d.year, d.month)] += 1
    for d, a in db.session.query(Payment.payment_date, Payment.amount).filter(Payment.payment_date >= first):
        if (d.year, d.month) in fee:
            fee[(d.year, d.month)] += float(a)
    labels = [date(y, m, 1).strftime("%b %Y") for y, m in months]
    return render_template(
        "dashboard.html", stats=stats, labels=labels, adm=list(adm.values()), fee=list(fee.values()),
        due=due_followups(8), upcoming=upcoming_followups(7, 8), pending=pending[:8],
        recent=Student.query.options(selectinload(Student.course)).order_by(Student.id.desc()).limit(6).all())
