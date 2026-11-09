"""DEVELOPMENT ONLY - sample data for trying out TypeTrack.
Run with:  flask seed-demo
Do NOT run this on a real institute database."""
import random
from datetime import date, time, timedelta
from extensions import db
from models import (Attendance, Batch, Course, Inquiry, InquiryFollowup, Institute, Payment, Student, User)
from services import record_payment
from utils.helpers import next_student_code

NAMES = ["Aarav Patil", "Sneha Kulkarni", "Rohan Deshmukh", "Pooja Jadhav", "Omkar Shinde", "Neha Pawar", "Siddharth More",
         "Priya Gaikwad", "Vikram Chavan", "Anjali Kale", "Sahil Bhosale", "Komal Thorat"]


def seed():
    if Student.query.count():
        print("Students already exist - demo data NOT loaded.")
        return
    random.seed(7)
    inst = Institute.query.first() or Institute()
    inst.name, inst.owner_name = inst.name if inst.name != "My Typing Institute" else "Sai Typing Institute", "Demo Owner"
    inst.address, inst.phone, inst.email = "Shop 4, Main Road, Pune 411001", "9876543210", "info@example.com"
    db.session.add(inst)
    if not User.query.filter_by(username="reception").first():
        u = User(name="Demo Receptionist", username="reception", role="receptionist")
        u.set_password("Reception@123")
        db.session.add(u)
    courses = [Course(name=n, fees=f, duration_months=m) for n, f, m in
               [("English Typing 30 WPM", 3000, 3), ("English Typing 40 WPM", 4000, 4), ("Marathi Typing 30 WPM", 3500, 3), ("MS-CIT + Typing", 6500, 6)]]
    db.session.add_all(courses)
    db.session.flush()
    today = date.today()
    batches = [Batch(name="Morning 8 AM", course_id=courses[0].id, instructor="Mr. Joshi", start_time=time(8), end_time=time(9), start_date=today - timedelta(days=90), capacity=8),
               Batch(name="Evening 6 PM", course_id=courses[1].id, instructor="Mrs. Kamble", start_time=time(18), end_time=time(19), start_date=today - timedelta(days=60), capacity=10)]
    db.session.add_all(batches)
    db.session.flush()
    owner = User.query.filter_by(role="owner").first()
    for idx, name in enumerate(NAMES):
        b = batches[idx % 2]
        c = next(x for x in courses if x.id == b.course_id)
        s = Student(student_code=next_student_code(), gr_no=f"GR-{1001 + idx}", name=name, phone=f"98{random.randint(10000000, 99999999)}",
                    alt_phone=f"91{random.randint(10000000, 99999999)}",
                    dob=today - timedelta(days=random.randint(6500, 9000)),
                    aadhar_no=f"5{random.randint(100, 999)} {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
                    course_id=c.id,
                    batch_id=b.id, admission_date=today - timedelta(days=random.randint(5, 80)), total_fees=c.fees,
                    discount=random.choice([0, 0, 200, 500]), address="Pune")
        db.session.add(s)
        db.session.flush()
        net = s.total_fees - s.discount
        for amt in random.choice([[net], [net / 2], [net / 4, net / 4], []]):
            record_payment(s, round(amt, 2), random.choice(["Cash", "UPI"]), s.admission_date, "DEMO-REF", "", owner)
        db.session.flush()
        for k in range(10):
            d = today - timedelta(days=k)
            if d.weekday() < 6 and d >= s.admission_date:
                db.session.add(Attendance(student_id=s.id, batch_id=b.id, date=d, marked_by=owner.id,
                                          status=random.choices(["Present", "Absent", "Leave"], [8, 1, 1])[0]))
    for n, st, off in [("Ketan Rane", "New", 0), ("Madhuri Sawant", "Contacted", -1), ("Tushar Mane", "Interested", 2), ("Rutuja Bhise", "Not Interested", None)]:
        i = Inquiry(name=n, phone=f"97{random.randint(10000000, 99999999)}",
                    alt_phone=f"96{random.randint(10000000, 99999999)}",
                    dob=today - timedelta(days=7000),
                    aadhar_no=f"6{random.randint(100, 999)} {random.randint(1000, 9999)} {random.randint(1000, 9999)}",
                    address="Pune",
                    course_id=courses[0].id, source="Walk-in", status=st,
                    inquiry_date=today - timedelta(days=3), follow_up_date=None if off is None else today + timedelta(days=off), preferred_timing="Evening")
        db.session.add(i)
        db.session.flush()
        if st == "Contacted":
            db.session.add(InquiryFollowup(inquiry_id=i.id, note="Called, will visit this week.", status=st, created_by=owner.id))
    db.session.commit()
    print("Demo data loaded. Receptionist login: reception / Reception@123")
