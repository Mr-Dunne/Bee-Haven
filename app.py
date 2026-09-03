import os

from flask import Flask, redirect, render_template, request, url_for

from models import BehaviorReport, Class, ReportCategory, ReportSeverity, Student, Teacher, db

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


def get_demo_teacher():
    return Teacher.query.filter_by(email=DEMO_TEACHER_EMAIL).first()


def seed_demo_data():
    if Teacher.query.first():
        return
    teacher = Teacher(email=DEMO_TEACHER_EMAIL, password_hash="not-a-real-hash", name="Jane Demo")
    db.session.add(teacher)
    db.session.commit()
    db.session.add(Class(name="Period 3 Homeroom", teacher_id=teacher.id))
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
    severity_counts = {sev: sum(1 for r in reports if r.severity == sev) for sev in ReportSeverity}

    return render_template(
        "dashboard.html",
        classes=classes,
        active_class=active_class,
        active_student=None,
        severity_counts=severity_counts,
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
        categories=list(ReportCategory),
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


@app.route("/classes/<int:class_id>/students/<int:student_id>/reports", methods=["POST"])
def add_report(class_id, student_id):
    teacher = get_demo_teacher()
    db.session.add(
        BehaviorReport(
            student_id=student_id,
            teacher_id=teacher.id,
            category=ReportCategory[request.form["category"]],
            severity=ReportSeverity[request.form["severity"]],
            notes=request.form.get("notes", "").strip() or None,
        )
    )
    db.session.commit()
    return redirect(url_for("view_student", class_id=class_id, student_id=student_id))


if __name__ == "__main__":
    app.run(debug=True)
