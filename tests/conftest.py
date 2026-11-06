import os

# Must be set before `app` is imported: app.py reads it once at import to pick
# the database. "sqlite://" is an in-memory database (Flask-SQLAlchemy keeps
# one shared connection for it), so tests never touch instance/beehaven.db.
os.environ["BEEHAVEN_DATABASE_URI"] = "sqlite://"

import pytest
from flask_migrate import upgrade

import app as app_module
from models import BehaviorReport, Class, ContactMethod, ParentContact, ReportType, Student, Teacher, db

assert app_module.app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite://", "tests must not use the real database"


@pytest.fixture
def app():
    flask_app = app_module.app
    flask_app.config["TESTING"] = True
    with flask_app.app_context():
        # Build the schema through the real migrations (not create_all), so the
        # suite also catches a migration that doesn't match the models.
        upgrade()
        app_module.seed_demo_data()
        yield flask_app
        db.session.remove()
        db.drop_all()
        db.session.execute(db.text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def teacher(app):
    return app_module.get_demo_teacher()


@pytest.fixture
def homeroom(teacher):
    # The seeded "Period 3 Homeroom" class with its six demo students.
    return Class.query.filter_by(teacher_id=teacher.id).one()


@pytest.fixture
def student(homeroom):
    return Student.query.filter_by(class_id=homeroom.id, name="Alex Rivera").one()


@pytest.fixture
def make_report(teacher):
    def _make(student, report_type=ReportType.NEGATIVE, category="TARDINESS", severity=None, contacts=0):
        report = BehaviorReport(
            student_id=student.id,
            teacher_id=teacher.id,
            report_type=report_type,
            category=category,
            severity=severity,
        )
        db.session.add(report)
        db.session.flush()
        for _ in range(contacts):
            db.session.add(ParentContact(report_id=report.id, method=ContactMethod.EMAIL))
        db.session.commit()
        return report

    return _make


@pytest.fixture
def other_teacher(app):
    other = Teacher(email="other.teacher@example.com", password_hash="x", name="Other Teacher")
    db.session.add(other)
    db.session.commit()
    db.session.add(Class(name="Someone Else's Class", teacher_id=other.id))
    db.session.commit()
    return other
