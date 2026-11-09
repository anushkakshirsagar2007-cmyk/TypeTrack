"""Smoke/integration tests. Run:  python tests/test_app.py   (uses a temporary SQLite database)"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db")
from datetime import date, timedelta
from app import create_app
from extensions import db
from models import *

app = create_app({"WTF_CSRF_ENABLED": False, "TESTING": True})
runner = app.test_cli_runner()
runner.invoke(args=["init-db"])
runner.invoke(args=["seed-demo"])
ok = 0


def check(cond, msg):
    global ok
    assert cond, "FAILED: " + msg
    ok += 1
    print("  ok -", msg)


def login(c, u, p):
    return c.post("/login", data={"username": u, "password": p}, follow_redirects=True)

with app.app_context():
    check(Student.query.count() == 12, "demo data loaded")
    check(Student.query.first().student_code.startswith("TT-"), "student ID format")

owner, rec = app.test_client(), app.test_client()
check(owner.get("/").status_code == 302, "dashboard requires login")
check(b"Wrong username" in login(owner, "admin", "bad").data, "bad login rejected")
check(login(owner, "admin", "ChangeMe@123").status_code == 200, "owner login")
login(rec, "reception", "Reception@123")

for url in ["/", "/students/", "/students/add", "/inquiries/", "/inquiries/add", "/batches/", "/batches/add", "/attendance/",
            "/fees/", "/fees/add", "/fees/pending", "/reports/", "/settings/institute", "/settings/users", "/settings/courses",
            "/settings/password", "/notifications", "/search?q=a", "/api/search?q=aa", "/students/1", "/batches/1", "/inquiries/1"]:
    check(owner.get(url).status_code == 200, f"owner can open {url}")
for k in ["students", "batches", "inquiries", "attendance", "fees_daily", "fees_monthly", "pending"]:
    check(owner.get(f"/reports/?type={k}").status_code == 200, f"report {k}")
    x = owner.get(f"/reports/?type={k}&export=xlsx"); check(x.data[:2] == b"PK", f"xlsx export {k}")
    x = owner.get(f"/reports/?type={k}&export=pdf"); check(x.data[:4] == b"%PDF", f"pdf export {k}")

# role-based access
for url in ["/reports/", "/settings/users", "/settings/institute", "/settings/courses", "/batches/add"]:
    check(rec.get(url).status_code == 403, f"receptionist blocked from {url}")
for url in ["/students/", "/inquiries/", "/attendance/", "/fees/", "/settings/password", "/batches/"]:
    check(rec.get(url).status_code == 200, f"receptionist can open {url}")
check(rec.post("/students/1/delete").status_code == 403, "receptionist cannot delete student")

with app.app_context():
    course = Course.query.first(); batch = Batch.query.first()
    cid, bid = course.id, batch.id
# student CRUD + validation
r = owner.post("/students/add", data={"name": "", "phone": "12", "aadhar_no": "123"}, follow_redirects=True)
check(b"Student name is required" in r.data and b"valid phone" in r.data and b"valid 12-digit Aadhaar" in r.data, "student validation errors")
r = owner.post("/students/add", data={"name": "Test Stu", "gr_no": "GR-501", "phone": "9000000001", "alt_phone": "9000000002", "aadhar_no": "123456789012",
        "address": "Camp Area, Pune", "dob": "2002-05-10", "admission_date": date.today().isoformat(), "course_id": cid,
        "batch_id": bid, "total_fees": "3000", "discount": "500", "initial_amount": "1000", "payment_mode": "Cash"}, follow_redirects=True)
check(b"added with ID" in r.data, "student created with initial payment")
with app.app_context():
    s = Student.query.filter_by(name="Test Stu").first(); sid = s.id
    check(float(s.net_fees) == 2500 and float(s.balance) == 1500 and s.payment_status == "Partial", "fee calculations")
    check(s.gr_no == "GR-501" and s.alt_phone == "9000000002" and s.aadhar_no == "1234 5678 9012" and s.address == "Camp Area, Pune", "student new fields stored")
    pid = s.payments[0].id
check(owner.post(f"/students/{sid}/edit", data={"name": "Test Stu 2", "gr_no": "GR-502", "phone": "9000000001", "alt_phone": "9000000003", "aadhar_no": "123456789012",
      "address": "Camp Area, Pune", "dob": "2002-05-10", "admission_date": date.today().isoformat(),
      "course_id": cid, "batch_id": bid, "total_fees": "3000", "discount": "500", "active": "1"}).status_code == 302, "student edit")
check(b"Test Stu 2" in owner.get("/students/?q=9000000001").data, "student search by phone")
check(b"Test Stu 2" in owner.get("/students/?q=1234").data, "student search by aadhar")
check(b"Test Stu 2" in owner.get("/students/?q=GR-502").data, "student search by gr_no")
check(b"Test Stu 2" in owner.get("/students/?pay=Partial").data, "payment status filter")

# payments
r = owner.post("/fees/add", data={"student_id": sid, "amount": "99999", "payment_date": date.today().isoformat(), "mode": "Cash"}, follow_redirects=True)
check(b"more than the pending balance" in r.data, "overpayment rejected")
r = owner.post("/fees/add", data={"student_id": sid, "amount": "500", "payment_date": date.today().isoformat(), "mode": "UPI"}, follow_redirects=True)
check(b"transaction reference" in r.data, "UPI needs reference")
r = owner.post("/fees/add", data={"student_id": sid, "amount": "500", "payment_date": date.today().isoformat(), "mode": "UPI", "reference": "UTR1"}, follow_redirects=True)
check(b"Receipt" in r.data, "installment recorded")
pdf = owner.get(f"/fees/{pid}/receipt.pdf"); check(pdf.data[:4] == b"%PDF", "receipt PDF")
check(rec.post(f"/fees/{pid}/delete").status_code == 403, "receptionist cannot delete payment")
with app.app_context():
    check(float(db.session.get(Student, sid).balance) == 1000, "balance after installments")

# attendance
today = date.today().isoformat()
data = {"batch_id": bid, "date": today}
with app.app_context():
    ids = [x.id for x in Student.query.filter_by(batch_id=bid, active=True)]
for i in ids: data[f"status_{i}"] = "Present"
rec.post("/attendance/", data=data, follow_redirects=True)
data[f"status_{ids[0]}"] = "Absent"
rec.post("/attendance/", data=data, follow_redirects=True)
with app.app_context():
    check(Attendance.query.filter_by(student_id=ids[0], date=date.today()).count() == 1, "no duplicate attendance")
    check(Attendance.query.filter_by(student_id=ids[0], date=date.today()).first().status == "Absent", "attendance updated")
    check(db.session.get(Student, ids[0]).attendance_stats()["overall"] is not None, "attendance percentage")
old = (date.today() - timedelta(days=3)).isoformat(); data["date"] = old
r = rec.post("/attendance/", data=data, follow_redirects=True)
check(b"only be edited by the owner" in r.data, "receptionist cannot edit past attendance")
data["date"] = (date.today() + timedelta(days=2)).isoformat()
check(b"future date" in rec.post("/attendance/", data=data, follow_redirects=True).data, "future attendance blocked")

# inquiry -> student conversion
r = rec.post("/inquiries/add", data={"name": "Lead One", "phone": "9111111111", "alt_phone": "9111111112", "dob": "2001-08-15",
      "aadhar_no": "987654321098", "address": "Market Yard, Pune", "inquiry_date": today, "status": "New", "course_id": cid,
      "follow_up_date": today}, follow_redirects=True)
with app.app_context():
    iq = Inquiry.query.filter_by(name="Lead One").first(); iid = iq.id
    check(iq.alt_phone == "9111111112" and iq.aadhar_no == "9876 5432 1098" and iq.address == "Market Yard, Pune", "inquiry new fields stored")
check(b"Lead One" in rec.get("/inquiries/?due=1").data, "due follow-up listed")
check(b"Lead One" in rec.get(f"/students/add?inquiry_id={iid}").data, "convert form prefilled")
check(b"9876 5432 1098" in rec.get(f"/students/add?inquiry_id={iid}").data, "inquiry aadhar prefilled in student form")
rec.post(f"/inquiries/{iid}/followup", data={"note": "Called", "status": "Interested", "next_follow_up": today}, follow_redirects=True)
rec.post("/students/add", data={"inquiry_id": iid, "name": "Lead One", "phone": "9111111111", "alt_phone": "9111111112",
      "dob": "2001-08-15", "aadhar_no": "987654321098", "address": "Market Yard, Pune", "admission_date": today, "course_id": cid,
      "total_fees": "3000", "discount": "0", "initial_amount": "0", "payment_mode": "Cash"}, follow_redirects=True)
with app.app_context():
    iq = db.session.get(Inquiry, iid)
    check(iq.status == "Joined" and iq.converted_student_id, "inquiry converted to student")
    conv_student = db.session.get(Student, iq.converted_student_id)
    check(conv_student.alt_phone == "9111111112" and conv_student.aadhar_no == "9876 5432 1098", "converted student preserved inquiry fields")

# batch capacity
with app.app_context():
    b = db.session.get(Batch, bid); b.capacity = b.filled; db.session.commit()
r = owner.post("/students/add", data={"name": "Extra", "phone": "9222222222", "admission_date": today, "course_id": cid, "batch_id": bid,
      "total_fees": "100", "discount": "0"}, follow_redirects=True)
check(b"is full" in r.data, "batch capacity enforced")

# settings
check(b"already taken" in owner.post("/settings/users", data={"name": "X", "username": "admin", "password": "Abcdef12", "role": "receptionist"}, follow_redirects=True).data, "duplicate username rejected")
check(b"own owner access" in owner.post("/settings/users", data={"id": 1, "name": "A", "username": "admin", "role": "receptionist", "active": "1"}, follow_redirects=True).data, "owner cannot demote self")
check(b"Password changed" in rec.post("/settings/password", data={"current": "Reception@123", "new": "NewPass123", "confirm": "NewPass123"}, follow_redirects=True).data, "password change")
check(b"Institute details saved" in owner.post("/settings/institute", data={"name": "Sai Typing", "phone": "9876543210"}, follow_redirects=True).data, "institute update")
check(b"Institute details saved" in owner.post("/settings/institute", data={"name": "Sai Typing", "phone": "7055301090, 8442266037"}, follow_redirects=True).data, "multiple institute contact numbers")
with app.app_context():
    check(Institute.query.first().phone == "7055301090, 8442266037", "institute contact numbers stored")
check(owner.post(f"/students/{sid}/delete", follow_redirects=True).status_code == 200, "owner deletes student (cascade)")
with app.app_context():
    check(Payment.query.filter_by(student_id=sid).count() == 0, "payments cascade-deleted")
check(owner.get("/nope").status_code == 404, "404 page")
check(b"Log in" in (owner.post("/logout", follow_redirects=True).data), "logout")
print(f"\nALL {ok} CHECKS PASSED")
