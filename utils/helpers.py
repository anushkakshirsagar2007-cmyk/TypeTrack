import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import quote
from flask import abort, current_app
from flask_login import current_user


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return fn(*a, **k)
        return wrapper
    return deco


owner_required = role_required("owner")
login_guard = role_required("owner", "receptionist")(lambda: None)   # use with bp.before_request
owner_guard = role_required("owner")(lambda: None)


def parse_date(v):
    try:
        return datetime.strptime((v or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_time(v):
    try:
        return datetime.strptime((v or "").strip(), "%H:%M").time()
    except ValueError:
        return None


def parse_money(v):
    try:
        d = Decimal(str(v).strip()).quantize(Decimal("0.01"))
        return d if d.is_finite() else None
    except (InvalidOperation, AttributeError):
        return None


def valid_phone(p):
    digits = re.sub(r"\D", "", p or "")
    return bool(re.fullmatch(r"\+?[\d\s\-]+", p or "")) and 10 <= len(digits) <= 13


def valid_aadhar(a):
    digits = re.sub(r"\D", "", a or "")
    return bool(re.fullmatch(r"[\d\s\-]+", (a or "").strip())) and len(digits) == 12


def format_aadhar(a):
    digits = re.sub(r"\D", "", str(a or ""))
    if len(digits) == 12:
        return f"{digits[:4]} {digits[4:8]} {digits[8:]}"
    return (a or "").strip()


def valid_email(e):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e or ""))


def wa_link(phone, text):
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        digits = "91" + digits
    return f"https://wa.me/{digits}?text={quote(text)}"


def next_student_code():
    from models import Student
    prefix = f"TT-{datetime.now().year}-"
    last = Student.query.filter(Student.student_code.like(prefix + "%")).order_by(Student.student_code.desc()).first()
    n = int(last.student_code.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{n:04d}"
