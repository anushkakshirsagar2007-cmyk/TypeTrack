"""Business logic shared by several routes."""
from datetime import date, timedelta
from uuid import uuid4
from flask import current_app, url_for
from sqlalchemy.orm import selectinload
from extensions import db
from models import Inquiry, Student, Payment


def due_followups(limit=None):
    q = Inquiry.query.filter(Inquiry.follow_up_date.isnot(None), Inquiry.follow_up_date <= date.today(),
                             Inquiry.status.notin_(["Joined", "Not Interested"])).order_by(Inquiry.follow_up_date)
    return q.limit(limit).all() if limit else q.all()


def upcoming_followups(days=7, limit=None):
    t = date.today()
    q = Inquiry.query.filter(Inquiry.follow_up_date > t, Inquiry.follow_up_date <= t + timedelta(days=days),
                             Inquiry.status.notin_(["Joined", "Not Interested"])).order_by(Inquiry.follow_up_date)
    return q.limit(limit).all() if limit else q.all()


def students_with_balance(overdue_only=False):
    studs = Student.query.options(selectinload(Student.payments)).filter_by(active=True).order_by(Student.admission_date).all()
    studs = [s for s in studs if s.balance > 0]
    if overdue_only:
        cutoff = date.today() - timedelta(days=current_app.config["OVERDUE_DAYS"])
        studs = [s for s in studs if s.admission_date <= cutoff]
    return studs


def notification_items():
    items = []
    for i in due_followups(limit=6):
        late = (date.today() - i.follow_up_date).days
        items.append({"icon": "bi-telephone-outbound", "level": "warning",
                      "text": f"Follow up with {i.name}" + (f" ({late}d late)" if late else " today"),
                      "url": url_for("inquiries.view", id=i.id)})
    overdue = students_with_balance(overdue_only=True)
    for s in overdue[:6]:
        items.append({"icon": "bi-cash-coin", "level": "danger",
                      "text": f"{s.name} has overdue fees of Rs. {s.balance:,.0f}",
                      "url": url_for("students.profile", id=s.id)})
    if len(overdue) > 6:
        items.append({"icon": "bi-three-dots", "level": "info", "text": f"{len(overdue) - 6} more overdue fee reminders",
                      "url": url_for("fees.pending")})
    return items


def record_payment(student, amount, mode, pdate, reference, note, user):
    p = Payment(student_id=student.id, amount=amount, mode=mode, payment_date=pdate, reference=reference or None,
                note=note or None, received_by=user.id, receipt_no="TMP" + uuid4().hex[:12])
    db.session.add(p)
    db.session.flush()
    p.receipt_no = f"RCP-{pdate:%Y%m}-{p.id:05d}"
    return p
