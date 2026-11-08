from collections import OrderedDict
from datetime import date
from decimal import Decimal
from flask import Blueprint, render_template, request, send_file, abort
from sqlalchemy import or_
from sqlalchemy.orm import selectinload, joinedload
from models import (Attendance, Batch, Course, Inquiry, Institute, Payment, Student, INQUIRY_STATUSES)
from services import students_with_balance
from utils.exports import make_report_pdf, make_xlsx
from utils.helpers import owner_guard, parse_date

bp = Blueprint("reports", __name__, url_prefix="/reports")
bp.before_request(owner_guard)

REPORTS = OrderedDict([
    ("students", "Student-wise report"), ("batches", "Batch-wise report"), ("inquiries", "Inquiry-wise report"),
    ("attendance", "Attendance report"), ("fees_daily", "Daily fee collection"), ("fees_monthly", "Monthly fee collection"),
    ("pending", "Pending fees report")])
m = lambda v: f"{v:,.2f}"


def _match(q, *vals):
    return not q or any(q.lower() in (v or "").lower() for v in vals)


def build(kind, a):
    q, start, end = a.get("q", "").strip(), parse_date(a.get("start")), parse_date(a.get("end"))
    batch_id = a.get("batch_id", type=int)
    if kind == "students":
        qs = Student.query.options(selectinload(Student.payments), joinedload(Student.course), joinedload(Student.batch))
        if batch_id:
            qs = qs.filter_by(batch_id=batch_id)
        if start:
            qs = qs.filter(Student.admission_date >= start)
        if end:
            qs = qs.filter(Student.admission_date <= end)
        rows = [[s.student_code, s.name, s.phone, s.course.name, s.batch.name if s.batch else "-", f"{s.admission_date:%d-%m-%Y}",
                 m(s.net_fees), m(s.paid), m(s.balance), s.payment_status, "Active" if s.active else "Inactive"]
                for s in qs.order_by(Student.name) if _match(q, s.name, s.phone, s.student_code)]
        return ["ID", "Name", "Phone", "Course", "Batch", "Admission", "Net Fees", "Paid", "Balance", "Payment", "Status"], rows
    if kind == "batches":
        rows = [[b.name, b.course.name, b.instructor or "-", b.timing, f"{b.start_date:%d-%m-%Y}", b.capacity, b.filled,
                 b.capacity - b.filled, b.status] for b in Batch.query.options(selectinload(Batch.students)).order_by(Batch.name)
                if _match(q, b.name, b.instructor, b.course.name) and (not batch_id or b.id == batch_id)]
        return ["Batch", "Course", "Instructor", "Timing", "Start Date", "Capacity", "Students", "Seats Left", "Status"], rows
    if kind == "inquiries":
        qs = Inquiry.query.options(joinedload(Inquiry.course))
        if a.get("status") in INQUIRY_STATUSES:
            qs = qs.filter_by(status=a["status"])
        if start:
            qs = qs.filter(Inquiry.inquiry_date >= start)
        if end:
            qs = qs.filter(Inquiry.inquiry_date <= end)
        rows = [[i.name, i.phone, i.course.name if i.course else "-", i.source or "-", f"{i.inquiry_date:%d-%m-%Y}",
                 f"{i.follow_up_date:%d-%m-%Y}" if i.follow_up_date else "-", i.status, i.remarks or ""]
                for i in qs.order_by(Inquiry.inquiry_date.desc()) if _match(q, i.name, i.phone)]
        return ["Name", "Phone", "Course", "Source", "Inquiry Date", "Follow-up", "Status", "Remarks"], rows
    if kind == "attendance":
        qs = Student.query.options(selectinload(Student.attendance_records), joinedload(Student.batch))
        if batch_id:
            qs = qs.filter_by(batch_id=batch_id)
        rows = []
        for s in qs.order_by(Student.name):
            if not _match(q, s.name, s.student_code):
                continue
            recs = [r for r in s.attendance_records if (not start or r.date >= start) and (not end or r.date <= end)]
            pres = sum(r.status == "Present" for r in recs)
            ab, lv = sum(r.status == "Absent" for r in recs), sum(r.status == "Leave" for r in recs)
            rows.append([s.student_code, s.name, s.batch.name if s.batch else "-", len(recs), pres, ab, lv,
                         f"{100 * pres / len(recs):.1f}%" if recs else "-"])
        return ["ID", "Student", "Batch", "Days Marked", "Present", "Absent", "Leave", "Attendance %"], rows
    if kind in ("fees_daily", "fees_monthly"):
        qs = Payment.query.options(joinedload(Payment.student))
        if start:
            qs = qs.filter(Payment.payment_date >= start)
        if end:
            qs = qs.filter(Payment.payment_date <= end)
        pays = [p for p in qs.order_by(Payment.payment_date.desc(), Payment.id.desc()) if _match(q, p.student.name, p.receipt_no, p.reference)]
        if kind == "fees_daily":
            rows = [[f"{p.payment_date:%d-%m-%Y}", p.receipt_no, p.student.student_code, p.student.name, p.mode, p.reference or "-", m(p.amount)] for p in pays]
            if rows:
                rows.append(["", "", "", "", "", "TOTAL", m(sum(p.amount for p in pays))])
            return ["Date", "Receipt", "ID", "Student", "Mode", "Reference", "Amount"], rows
        grp = OrderedDict()
        for p in pays:
            k = p.payment_date.strftime("%B %Y")
            g = grp.setdefault(k, [0, Decimal(0)])
            g[0] += 1
            g[1] += p.amount
        rows = [[k, v[0], m(v[1])] for k, v in grp.items()]
        if rows:
            rows.append(["TOTAL", sum(v[0] for v in grp.values()), m(sum(v[1] for v in grp.values()))])
        return ["Month", "Payments", "Amount Collected"], rows
    if kind == "pending":
        rows = [[s.student_code, s.name, s.phone, s.course.name, f"{s.admission_date:%d-%m-%Y}", m(s.net_fees), m(s.paid), m(s.balance)]
                for s in students_with_balance() if _match(q, s.name, s.phone, s.student_code)]
        if rows:
            rows.append(["", "", "", "", "", "", "TOTAL", m(sum(s.balance for s in students_with_balance() if _match(q, s.name, s.phone, s.student_code)))])
        return ["ID", "Student", "Phone", "Course", "Admission", "Net Fees", "Paid", "Balance"], rows
    abort(404)


@bp.route("/")
def index():
    kind = request.args.get("type", "students")
    if kind not in REPORTS:
        abort(404)
    headers, rows = build(kind, request.args)
    fmt = request.args.get("export")
    title = REPORTS[kind]
    if fmt in ("xlsx", "pdf"):
        name = f"{kind}_{date.today():%Y%m%d}"
        if fmt == "xlsx":
            return send_file(make_xlsx(title, headers, rows), as_attachment=True, download_name=name + ".xlsx",
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        sub = " to ".join(x for x in [request.args.get("start"), request.args.get("end")] if x)
        return send_file(make_report_pdf(title, headers, rows, Institute.query.first(), sub), as_attachment=True,
                         download_name=name + ".pdf", mimetype="application/pdf")
    return render_template("reports/index.html", kind=kind, reports=REPORTS, headers=headers, rows=rows, f=request.args,
                           batches=Batch.query.order_by(Batch.name).all(), statuses=INQUIRY_STATUSES)
