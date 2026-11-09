import os
from datetime import date, datetime, time, timezone

from flask import Flask, abort, redirect, render_template, request, url_for
from flask_migrate import Migrate, stamp, upgrade
from sqlalchemy import inspect

from models import (
    BehaviorReport,
    Class,
    ContactMethod,
    NegativeReportCategory,
    ParentContact,
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

# BEEHAVEN_DATABASE_URI lets tests (and migration generation) point at a
# throwaway database instead of the real instance/beehaven.db.
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "BEEHAVEN_DATABASE_URI", "sqlite:///" + os.path.join(app.instance_path, "beehaven.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# Schema changes go through migrations/ (Alembic), never db.create_all(), so
# existing data survives model changes. render_as_batch is needed because
# SQLite can't ALTER/DROP columns in place; batch mode rebuilds the table.
migrate = Migrate(app, db, render_as_batch=True)

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


# Every route loads records through these instead of by bare ID, so a URL can
# only reach the current teacher's own data, and the IDs in a URL have to
# agree with each other (/classes/1/students/9 is a 404 if student 9 is in
# class 2). A 404 rather than a 403 also avoids confirming another teacher's
# record exists. When real login replaces get_demo_teacher(), this is the
# one place the FERPA scoping rule lives.
def get_owned_class(class_id):
    teacher = get_demo_teacher()
    return Class.query.filter_by(id=class_id, teacher_id=teacher.id).first_or_404()


def get_owned_student(class_id, student_id):
    owned_class = get_owned_class(class_id)
    return Student.query.filter_by(id=student_id, class_id=owned_class.id).first_or_404()


def get_owned_report(class_id, student_id, report_id):
    student = get_owned_student(class_id, student_id)
    return BehaviorReport.query.filter_by(id=report_id, student_id=student.id).first_or_404()


def get_owned_contact(class_id, student_id, report_id, contact_id):
    report = get_owned_report(class_id, student_id, report_id)
    return ParentContact.query.filter_by(id=contact_id, report_id=report.id).first_or_404()


def form_enum(enum_cls, field):
    # Look up a submitted form value by enum member name. A missing or unknown
    # value means a tampered or out-of-date form, so answer 400 Bad Request
    # instead of letting the KeyError become a 500.
    value = request.form.get(field)
    if value not in enum_cls.__members__:
        abort(400, description=f"Invalid {field}.")
    return enum_cls[value]


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


# The first migration, which matches the schema db.create_all() used to build
# before migrations existed. See adopt_pre_migration_db() below.
BASELINE_REVISION = "6af254fa3cff"


def adopt_pre_migration_db():
    # A database made by an older copy of the app (via db.create_all()) has
    # the tables but no alembic_version table, so upgrade() would try to
    # create the tables again and fail with "table already exists". Those
    # tables match the baseline exactly, so record the database as being at
    # the baseline (no SQL run), and upgrade() then applies only the newer
    # migrations. Stamping the baseline rather than "head" matters: anything
    # added after it still has to actually run.
    tables = inspect(db.engine).get_table_names()
    if "teacher" in tables and "alembic_version" not in tables:
        stamp(revision=BASELINE_REVISION)


def init_db():
    # Bring the database up to the latest migration, then seed the demo
    # teacher on a fresh database. Runs on `python app.py` rather than at
    # import, so `flask db ...` commands (which import this module) can
    # migrate/downgrade without the app fighting them.
    with app.app_context():
        adopt_pre_migration_db()
        upgrade()
        seed_demo_data()


@app.context_processor
def inject_last_updated():
    # Runs for every template render, so the nav bar's "last updated" display
    # (base.html) doesn't need every view function to fetch and pass it.
    teacher = get_demo_teacher()
    last_updated = (
        db.session.query(db.func.max(BehaviorReport.updated_at))
        .filter(BehaviorReport.teacher_id == teacher.id)
        .scalar()
    )
    return {"last_updated": last_updated}


@app.route("/")
def dashboard():
    teacher = get_demo_teacher()
    classes = Class.query.filter_by(teacher_id=teacher.id).all()
    return render_template("dashboard.html", classes=classes, active_class=None, active_student=None)


@app.route("/classes/<int:class_id>")
def view_class(class_id):
    teacher = get_demo_teacher()
    classes = Class.query.filter_by(teacher_id=teacher.id).all()
    active_class = get_owned_class(class_id)

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
    active_class = get_owned_class(class_id)
    # Part of the URL, so an unknown type is "no such page" (404), not a bad form (400).
    if report_type.upper() not in ReportType.__members__:
        abort(404)
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
    active_student = get_owned_student(class_id, student_id)
    active_class = active_student.parent_class

    return render_template(
        "dashboard.html",
        classes=classes,
        active_class=active_class,
        active_student=active_student,
        report_types=list(ReportType),
        positive_categories=list(PositiveReportCategory),
        negative_categories=list(NegativeReportCategory),
        severities=list(ReportSeverity),
        contact_methods=list(ContactMethod),
        today=date.today().isoformat(),
    )


@app.route("/classes", methods=["POST"])
def add_class():
    teacher = get_demo_teacher()
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("dashboard"))
    new_class = Class(name=name, teacher_id=teacher.id)
    db.session.add(new_class)
    db.session.commit()
    return redirect(url_for("view_class", class_id=new_class.id))


@app.route("/classes/<int:class_id>/students", methods=["POST"])
def add_student(class_id):
    # Also stops a student being added to a class ID that doesn't exist
    # (SQLite doesn't enforce foreign keys by default, so it would save).
    owned_class = get_owned_class(class_id)
    name = request.form.get("name", "").strip()
    if name:
        db.session.add(
            Student(
                class_id=owned_class.id,
                name=name,
                parent_email=request.form.get("parent_email", "").strip() or None,
                parent_phone=request.form.get("parent_phone", "").strip() or None,
            )
        )
        db.session.commit()
    return redirect(url_for("view_class", class_id=class_id))


@app.route("/classes/<int:class_id>/edit", methods=["POST"])
def edit_class(class_id):
    active_class = get_owned_class(class_id)
    name = request.form.get("name", "").strip()
    if name:
        active_class.name = name
        db.session.commit()
    return redirect(url_for("view_class", class_id=class_id))


@app.route("/classes/<int:class_id>/delete", methods=["POST"])
def delete_class(class_id):
    # Cascade (Class.students -> Student.reports -> BehaviorReport.contacts,
    # all configured in models.py) takes the whole roster and report history
    # with it.
    active_class = get_owned_class(class_id)
    db.session.delete(active_class)
    db.session.commit()
    return redirect(url_for("dashboard"))


@app.route("/classes/<int:class_id>/students/<int:student_id>/edit", methods=["POST"])
def edit_student(class_id, student_id):
    student = get_owned_student(class_id, student_id)
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
    student = get_owned_student(class_id, student_id)
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for("view_class", class_id=class_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/reports", methods=["POST"])
def add_report(class_id, student_id):
    teacher = get_demo_teacher()
    student = get_owned_student(class_id, student_id)
    report_type = form_enum(ReportType, "report_type")
    category_enum = PositiveReportCategory if report_type == ReportType.POSITIVE else NegativeReportCategory
    category = form_enum(category_enum, "category")
    severity = form_enum(ReportSeverity, "severity") if report_type == ReportType.NEGATIVE else None

    db.session.add(
        BehaviorReport(
            student_id=student.id,
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
    report = get_owned_report(class_id, student_id, report_id)
    category_enum = PositiveReportCategory if report.report_type == ReportType.POSITIVE else NegativeReportCategory
    report.category = form_enum(category_enum, "category").name
    if report.report_type == ReportType.NEGATIVE:
        report.severity = form_enum(ReportSeverity, "severity")
    report.notes = request.form.get("notes", "").strip() or None
    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/reports/<int:report_id>/delete", methods=["POST"])
def delete_report(class_id, student_id, report_id):
    # Cascade (configured on BehaviorReport.contacts in models.py) takes the
    # report's contact log with it.
    report = get_owned_report(class_id, student_id, report_id)
    db.session.delete(report)
    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id))


@app.route("/classes/<int:class_id>/students/<int:student_id>/reports/<int:report_id>/contact", methods=["POST"])
def update_report_contact(class_id, student_id, report_id):
    report = get_owned_report(class_id, student_id, report_id)

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


@app.route(
    "/classes/<int:class_id>/students/<int:student_id>/reports/<int:report_id>/contacts", methods=["POST"]
)
def add_parent_contact(class_id, student_id, report_id):
    # One entry in the report's detailed contact log. The date is optional and
    # defaults to now; a teacher logging yesterday's call can backdate it.
    report = get_owned_report(class_id, student_id, report_id)
    method = form_enum(ContactMethod, "method")

    contacted_on = request.form.get("contacted_on", "").strip()
    if contacted_on:
        try:
            # Stored as midnight on that day: only the date is ever shown.
            contacted_at = datetime.combine(date.fromisoformat(contacted_on), time.min)
        except ValueError:
            abort(400, description="Invalid contacted_on date.")
    else:
        contacted_at = datetime.now(timezone.utc)

    db.session.add(
        ParentContact(
            report_id=report.id,
            method=method,
            contacted_at=contacted_at,
            notes=request.form.get("notes", "").strip() or None,
        )
    )
    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id) + f"#report-{report_id}")


@app.route(
    "/classes/<int:class_id>/students/<int:student_id>/reports/<int:report_id>/contacts/<int:contact_id>/delete",
    methods=["POST"],
)
def delete_parent_contact(class_id, student_id, report_id, contact_id):
    contact = get_owned_contact(class_id, student_id, report_id, contact_id)
    db.session.delete(contact)
    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id) + f"#report-{report_id}")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
