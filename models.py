from datetime import date, datetime
from decimal import Decimal
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

INQUIRY_STATUSES = ["New", "Contacted", "Interested", "Joined", "Not Interested"]
INQUIRY_SOURCES = ["Walk-in", "Phone Call", "Facebook", "Instagram", "Google", "Friend / Referral", "Banner / Pamphlet", "Other"]
PAYMENT_MODES = ["Cash", "UPI", "Online", "Bank Transfer"]
ATTENDANCE_STATUSES = ["Present", "Absent", "Leave"]
ZERO = Decimal("0.00")


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("owner", "receptionist", name="user_role"), nullable=False, default="receptionist")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_active(self):  # Flask-Login hook: inactive users cannot log in
        return self.active

    @property
    def is_owner(self):
        return self.role == "owner"


class Institute(db.Model):
    __tablename__ = "institute"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, default="My Typing Institute")
    owner_name = db.Column(db.String(100))
    logo = db.Column(db.String(255))
    address = db.Column(db.Text)
    phone = db.Column(db.String(100))
    email = db.Column(db.String(120))
    website = db.Column(db.String(150))
    receipt_note = db.Column(db.String(255), default="Fees once paid are not refundable.")


class Course(db.Model):
    __tablename__ = "courses"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    duration_months = db.Column(db.Integer, nullable=False, default=3)
    fees = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)


class Batch(db.Model):
    __tablename__ = "batches"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    instructor = db.Column(db.String(100))
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    capacity = db.Column(db.Integer, nullable=False, default=20)
    status = db.Column(db.Enum("Active", "Inactive", "Completed", name="batch_status"), nullable=False, default="Active")
    course = db.relationship("Course", backref="batches")

    @property
    def filled(self):
        return sum(1 for s in self.students if s.active)

    @property
    def timing(self):
        return f"{self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"

    @property
    def label(self):
        return f"{self.name} ({self.timing})"


class Student(db.Model):
    __tablename__ = "students"
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    alt_phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    dob = db.Column(db.Date)
    aadhar_no = db.Column(db.String(20), index=True)
    admission_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id", ondelete="SET NULL"), index=True)
    total_fees = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    course = db.relationship("Course", backref="students")
    batch = db.relationship("Batch", backref="students")
    payments = db.relationship("Payment", backref="student", cascade="all, delete-orphan",
                               order_by="Payment.payment_date.desc(), Payment.id.desc()")
    attendance_records = db.relationship("Attendance", backref="student", cascade="all, delete-orphan",
                                         order_by="Attendance.date.desc()")

    @property
    def net_fees(self):
        return (self.total_fees or ZERO) - (self.discount or ZERO)

    @property
    def paid(self):
        return sum((p.amount for p in self.payments), ZERO)

    @property
    def balance(self):
        return self.net_fees - self.paid

    @property
    def payment_status(self):
        if self.balance <= 0:
            return "Paid"
        return "Partial" if self.paid > 0 else "Unpaid"

    def attendance_stats(self):
        recs = self.attendance_records
        today = date.today()

        def pct(rs):
            return round(100 * sum(1 for r in rs if r.status == "Present") / len(rs), 1) if rs else None

        month = [r for r in recs if r.date.year == today.year and r.date.month == today.month]
        return {
            "overall": pct(recs), "monthly": pct(month), "total_days": len(recs),
            "present": sum(1 for r in recs if r.status == "Present"),
            "absent": sum(1 for r in recs if r.status == "Absent"),
            "leave": sum(1 for r in recs if r.status == "Leave"),
            "today": next((r.status for r in recs if r.date == today), None),
        }


class Inquiry(db.Model):
    __tablename__ = "inquiries"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    alt_phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    dob = db.Column(db.Date)
    aadhar_no = db.Column(db.String(20), index=True)
    address = db.Column(db.Text)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), index=True)
    preferred_timing = db.Column(db.String(60))
    inquiry_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    source = db.Column(db.String(40))
    remarks = db.Column(db.Text)
    follow_up_date = db.Column(db.Date, index=True)
    status = db.Column(db.String(20), nullable=False, default="New", index=True)
    converted_student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="SET NULL"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    course = db.relationship("Course")
    converted_student = db.relationship("Student", foreign_keys=[converted_student_id])
    followups = db.relationship("InquiryFollowup", backref="inquiry", cascade="all, delete-orphan",
                                order_by="InquiryFollowup.id.desc()")

    @property
    def is_open(self):
        return self.status not in ("Joined", "Not Interested")


class InquiryFollowup(db.Model):
    __tablename__ = "inquiry_followups"
    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(db.Integer, db.ForeignKey("inquiries.id", ondelete="CASCADE"), nullable=False, index=True)
    note = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    next_follow_up = db.Column(db.Date)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (db.UniqueConstraint("student_id", "date", name="uq_attendance_student_date"),)
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id", ondelete="SET NULL"), index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.Enum("Present", "Absent", "Leave", name="att_status"), nullable=False)
    marked_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(30), unique=True, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    mode = db.Column(db.Enum("Cash", "UPI", "Online", "Bank Transfer", name="pay_mode"), nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    reference = db.Column(db.String(100))
    note = db.Column(db.String(255))
    received_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")
