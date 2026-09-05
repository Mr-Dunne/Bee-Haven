import os
from datetime import datetime, timezone

from flask import Flask, redirect, render_template, request, url_for

from models import (
    BehaviorReport,
    Class,
    NegativeReportCategory,
    PositiveReportCategory,
    ReportSeverity,
    ReportType,
    Student,
    Teacher,
    db,
)

app = Flask(__name__, instance_relative_config=True)

# instance/ is gitignored, so the SQLite file itself never gets committed.
os.makedirs(app.instance_path, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, "beehaven.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Prototype only: there's no login system yet, so every page acts as this one
# hard-coded teacher. CLAUDE.md's FERPA rule (every query scoped to the
# authenticated teacher) isn't satisfied until real auth replaces this.
DEMO_TEACHER_EMAIL = "demo.teacher@example.com"

DEMO_STUDENTS = [
    ("Alex Rivera", "alex.parent@example.com", "555-0101"),
    ("Jordan Lee", "jordan.parent@example.com", "555-0102"),
    ("Casey Morgan", "casey.parent@example.com", "555-0103"),
    ("Riley Chen", "riley.parent@example.com", "555-0104"),
    ("Sam Patel", None, "555-0105"),
    ("Taylor Brooks", "taylor.parent@example.com", None),
]


def get_demo_teacher():
    return Teacher.query.filter_by(email=DEMO_TEACHER_EMAIL).first()


def seed_demo_data():
    if Teacher.query.first():
        return
    teacher = Teacher(email=DEMO_TEACHER_EMAIL, password_hash="not-a-real-hash", name="Jane Demo")
    db.session.add(teacher)
    db.session.commit()

    homeroom = Class(name="Period 3 Homeroom", teacher_id=teacher.id)
    db.session.add(homeroom)
    db.session.commit()

    for name, parent_email, parent_phone in DEMO_STUDENTS:
        db.session.add(Student(class_id=homeroom.id, name=name, parent_email=parent_email, parent_phone=parent_phone))
    db.session.commit()


with app.app_context():
    db.create_all()
    seed_demo_data()


@app.route("/")
def dashboard():
    teacher = get_demo_teacher()
    classes = Class.query.filter_by(teacher_id=teacher.id).all()
    return render_template("dashboard.html", classes=classes, active_class=None, active_student=None)


@app.route("/classes/<int:class_id>")
def view_class(class_id):
    teacher = get_demo_teacher()
    classes = Class.query.filter_by(teacher_id=teacher.id).all()
    active_class = Class.query.get_or_404(class_id)

    reports = BehaviorReport.query.join(Student).filter(Student.class_id == class_id).all()
    positive_count = sum(1 for r in reports if r.report_type == ReportType.POSITIVE)
    negative_count = sum(1 for r in reports if r.report_type == ReportType.NEGATIVE)

    return render_template(
        "dashboard.html",
        classes=classes,
        active_class=active_class,
        active_student=None,
        active_report_type=None,
        positive_count=positive_count,
        negative_count=negative_count,
    )


@app.route("/classes/<int:class_id>/reports/<report_type>")
def class_reports(class_id, report_type):
    teacher = get_demo_teacher()
    classes = Class.query.filter_by(teacher_id=teacher.id).all()
    active_class = Class.query.get_or_404(class_id)
    rtype = ReportType[report_type.upper()]

    reports = (
        BehaviorReport.query.join(Student)
        .filter(Student.class_id == class_id, BehaviorReport.report_type == rtype)
        .order_by(BehaviorReport.created_at.desc())
        .all()
    )

    return render_template(
        "dashboard.html",
        classes=classes,
        active_class=active_class,
        active_student=None,
        active_report_type=rtype,
        reports=reports,
    )


@app.route("/classes/<int:class_id>/students/<int:student_id>")
def view_student(class_id, student_id):
    teacher = get_demo_teacher()
    classes = Class.query.filter_by(teacher_id=teacher.id).all()
    active_class = Class.query.get_or_404(class_id)
    active_student = Student.query.get_or_404(student_id)

    return render_template(
        "dashboard.html",
        classes=classes,
        active_class=active_class,
        active_student=active_student,
        report_types=list(ReportType),
        positive_categories=list(PositiveReportCategory),
        negative_categories=list(NegativeReportCategory),
        severities=list(ReportSeverity),
    )


@app.route("/classes", methods=["POST"])
def add_class():
    teacher = get_demo_teacher()
    name = request.form.get("name", "").strip()
    if name:
        db.session.add(Class(name=name, teacher_id=teacher.id))
        db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/classes/<int:class_id>/students", methods=["POST"])
def add_student(class_id):
    name = request.form.get("name", "").strip()
    if name:
        db.session.add(
            Student(
                class_id=class_id,
                name=name,
                parent_email=request.form.get("parent_email", "").strip() or None,
                parent_phone=request.form.get("parent_phone", "").strip() or None,
            )
        )
        db.session.commit()
    return redirect(url_for("view_class", class_id=class_id))


@app.route("/classes/<int:class_id>/edit", methods=["POST"])
def edit_class(class_id):
    active_class = Class.query.get_or_404(class_id)
    name = request.form.get("name", "").strip()
    if name:
        active_class.name = name
        db.session.commit()
    return redirect(url_for("view_class", class_id=class_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/edit", methods=["POST"])
def edit_student(class_id, student_id):
    student = Student.query.get_or_404(student_id)
    name = request.form.get("name", "").strip()
    if name:
        student.name = name
        student.parent_email = request.form.get("parent_email", "").strip() or None
        student.parent_phone = request.form.get("parent_phone", "").strip() or None
        db.session.commit()
    return redirect(url_for("view_class", class_id=class_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/delete", methods=["POST"])
def delete_student(class_id, student_id):
    # Cascade (configured on Student.reports / BehaviorReport.contacts in models.py)
    # takes the student's reports and those reports' contact logs with them.
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for("view_class", class_id=class_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/reports", methods=["POST"])
def add_report(class_id, student_id):
    teacher = get_demo_teacher()
    report_type = ReportType[request.form["report_type"]]
    category_enum = PositiveReportCategory if report_type == ReportType.POSITIVE else NegativeReportCategory
    category = category_enum[request.form["category"]]
    severity = ReportSeverity[request.form["severity"]] if report_type == ReportType.NEGATIVE else None

    db.session.add(
        BehaviorReport(
            student_id=student_id,
            teacher_id=teacher.id,
            report_type=report_type,
            category=category.name,
            severity=severity,
            notes=request.form.get("notes", "").strip() or None,
        )
    )
    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/reports/<int:report_id>/edit", methods=["POST"])
def edit_report(class_id, student_id, report_id):
    # report_type is not editable here: it decides which category enum applies,
    # so switching positive/negative is a delete-and-refile, not an edit.
    report = BehaviorReport.query.get_or_404(report_id)
    category_enum = PositiveReportCategory if report.report_type == ReportType.POSITIVE else NegativeReportCategory
    report.category = category_enum[request.form["category"]].name
    if report.report_type == ReportType.NEGATIVE:
        report.severity = ReportSeverity[request.form["severity"]]
    report.notes = request.form.get("notes", "").strip() or None
    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/reports/<int:report_id>/delete", methods=["POST"])
def delete_report(class_id, student_id, report_id):
    # Cascade (configured on BehaviorReport.contacts in models.py) takes the
    # report's contact log with it.
    report = BehaviorReport.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/reports/<int:report_id>/contact", methods=["POST"])
def update_report_contact(class_id, student_id, report_id):
    report = BehaviorReport.query.get_or_404(report_id)

    now = datetime.now(timezone.utc)
    for direction in ("sent", "received"):
        for method in BehaviorReport.CONTACT_METHODS:
            field = f"contact_{direction}_{method}"
            checked = field in request.form
            if checked != getattr(report, field):
                setattr(report, f"{field}_at", now if checked else None)
            setattr(report, field, checked)

    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id) + f"#report-{report_id}")


if __name__ == "__main__":
    app.run(debug=True)
