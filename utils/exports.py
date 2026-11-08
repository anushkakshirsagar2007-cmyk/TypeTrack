"""Reusable Excel / PDF generators (reports and fee receipts)."""
import os
from datetime import datetime
from io import BytesIO
from flask import current_app
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#0A2342")
LIGHT = colors.HexColor("#E3EFFA")


def _logo_path(inst):
    if inst and inst.logo:
        if current_app.config["UPLOAD_STORAGE_BACKEND"] == "supabase":
            from utils.uploads import read_upload
            return BytesIO(read_upload(inst.logo))
        p = os.path.join(current_app.config["UPLOAD_FOLDER"], inst.logo)
        if os.path.exists(p):
            return p
    return None


def _clean(v):
    return "" if v is None else str(v)


def make_xlsx(title, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = title[:30]
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0A2342")
        c.alignment = Alignment(horizontal="center")
    for r in rows:
        ws.append([float(v) if hasattr(v, "quantize") else v for v in r])
    for i, h in enumerate(headers, 1):
        width = max([len(str(h))] + [len(_clean(r[i - 1])) for r in rows] or [10])
        ws.column_dimensions[get_column_letter(i)].width = min(width + 3, 40)
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def make_report_pdf(title, headers, rows, inst, subtitle=""):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=title)
    ss = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=ss["BodyText"], fontSize=8, leading=10)
    head = ParagraphStyle("head", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    story = [Paragraph(f"<b>{inst.name if inst else 'TypeTrack'}</b>", ss["Title"]),
             Paragraph(f"<b>{title}</b>" + (f" &nbsp;|&nbsp; {subtitle}" if subtitle else ""), ss["Heading3"]),
             Paragraph(f"Generated on {datetime.now():%d %b %Y, %I:%M %p}", cell), Spacer(1, 6)]
    data = [[Paragraph(h, head) for h in headers]] + [[Paragraph(_clean(v), cell) for v in r] for r in rows]
    if not rows:
        data.append([Paragraph("No records found", cell)] + [""] * (len(headers) - 1))
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)
    doc.build(story)
    buf.seek(0)
    return buf


def make_receipt_pdf(payment, inst):
    s = payment.student
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Receipt {payment.receipt_no}")
    ss = getSampleStyleSheet()
    n = ParagraphStyle("n", parent=ss["BodyText"], fontSize=10, leading=14)
    big = ParagraphStyle("big", parent=n, fontSize=18, leading=22, textColor=NAVY, fontName="Helvetica-Bold")
    name = inst.name if inst else "TypeTrack"
    contact = " | ".join(x for x in [inst.phone if inst else None, inst.email if inst else None] if x)
    info = [Paragraph(name, big), Paragraph((inst.address or "").replace("\n", "<br/>") if inst else "", n), Paragraph(contact, n)]
    logo = _logo_path(inst)
    head = Table([[Image(logo, 22 * mm, 22 * mm, kind="proportional") if logo else "", info]], colWidths=[28 * mm, 140 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    banner = Table([[Paragraph("<font color='white'><b>FEE RECEIPT</b></font>", ParagraphStyle("b", parent=n, fontSize=13, alignment=1))]],
                   colWidths=[174 * mm])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))

    def kv(rows):
        t = Table([[Paragraph(f"<b>{a}</b>", n), Paragraph(_clean(b), n)] for a, b in rows], colWidths=[50 * mm, 124 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return t

    story = [head, Spacer(1, 8), banner, Spacer(1, 10),
             kv([("Receipt No.", payment.receipt_no), ("Payment Date", f"{payment.payment_date:%d %b %Y}")]), Spacer(1, 8),
             kv([("Student Name", s.name), ("Student ID", s.student_code), ("Phone", s.phone),
                 ("Course", s.course.name), ("Batch", s.batch.label if s.batch else "-")]), Spacer(1, 8),
             kv([("Amount Paid", f"Rs. {payment.amount:,.2f}"), ("Payment Mode", payment.mode),
                 ("Transaction Ref.", payment.reference or "-"), ("Net Course Fees", f"Rs. {s.net_fees:,.2f}"),
                 ("Total Paid So Far", f"Rs. {s.paid:,.2f}"), ("Remaining Balance", f"Rs. {s.balance:,.2f}")]),
             Spacer(1, 26), Table([["", Paragraph("Authorised Signature", n)]], colWidths=[110 * mm, 64 * mm]),
             Spacer(1, 10), Paragraph(f"<i>{(inst.receipt_note if inst and inst.receipt_note else '')}</i>", n),
             Paragraph("This is a computer generated receipt.", n)]
    doc.build(story)
    buf.seek(0)
    return buf
