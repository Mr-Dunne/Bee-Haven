import json
from html.parser import HTMLParser

import pytest

from models import BehaviorReport, Class, ReportSeverity, Student, db


# --- Confirm prompts survive apostrophes ------------------------------------


class _OnsubmitCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.handlers = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "onsubmit":
                self.handlers.append(value)  # already HTML-decoded, as the browser would see it


def _confirm_messages(page_html):
    # Pull the argument out of each `return confirm(...);` handler and parse it
    # as JSON. JSON strings are valid JS strings, so if this parses, the browser
    # gets a working prompt instead of a script error that skips confirmation.
    parser = _OnsubmitCollector()
    parser.feed(page_html)
    messages = []
    for handler in parser.handlers:
        assert handler.startswith("return confirm(") and handler.endswith(");"), handler
        messages.append(json.loads(handler[len("return confirm(") : -len(");")]))
    return messages


def test_remove_student_prompt_handles_apostrophes(client, homeroom):
    client.post(f"/classes/{homeroom.id}/students", data={"name": "Liam O'Brien"})
    liam = Student.query.filter_by(name="Liam O'Brien").one()
    page = client.get(f"/classes/{homeroom.id}/students/{liam.id}").get_data(as_text=True)
    assert any(m.startswith("Remove Liam O'Brien?") for m in _confirm_messages(page))


def test_delete_class_prompt_handles_apostrophes(client):
    client.post("/classes", data={"name": "Ms. O'Neil's \"Advanced\" Class"})
    new_class = Class.query.filter_by(name="Ms. O'Neil's \"Advanced\" Class").one()
    page = client.get(f"/classes/{new_class.id}").get_data(as_text=True)
    assert any(m.startswith("Delete Ms. O'Neil's \"Advanced\" Class?") for m in _confirm_messages(page))


# --- Another teacher's data is unreachable -----------------------------------


@pytest.fixture
def foreign_class(other_teacher):
    return Class.query.filter_by(teacher_id=other_teacher.id).one()


def test_cannot_view_or_change_another_teachers_class(client, foreign_class):
    cid = foreign_class.id
    assert client.get(f"/classes/{cid}").status_code == 404
    assert client.get(f"/classes/{cid}/reports/positive").status_code == 404
    assert client.post(f"/classes/{cid}/edit", data={"name": "Hijacked"}).status_code == 404
    assert client.post(f"/classes/{cid}/students", data={"name": "Intruder"}).status_code == 404
    assert client.post(f"/classes/{cid}/delete").status_code == 404

    db.session.expire_all()
    assert db.session.get(Class, cid).name == "Someone Else's Class"
    assert Student.query.filter_by(name="Intruder").count() == 0


def test_cannot_add_student_to_a_class_that_does_not_exist(client):
    assert client.post("/classes/999/students", data={"name": "Ghost"}).status_code == 404
    assert Student.query.filter_by(name="Ghost").count() == 0


# --- IDs in the URL must agree with each other -------------------------------


@pytest.fixture
def second_class(teacher):
    other = Class(name="Period 6 Chemistry", teacher_id=teacher.id)
    db.session.add(other)
    db.session.commit()
    return other


def test_student_under_the_wrong_class_is_404(client, student, second_class):
    base = f"/classes/{second_class.id}/students/{student.id}"
    assert client.get(base).status_code == 404
    assert client.post(f"{base}/edit", data={"name": "Renamed"}).status_code == 404
    assert client.post(f"{base}/delete").status_code == 404
    assert (
        client.post(f"{base}/reports", data={"report_type": "POSITIVE", "category": "ACADEMIC"}).status_code
        == 404
    )

    db.session.expire_all()
    assert db.session.get(Student, student.id).name == "Alex Rivera"
    assert BehaviorReport.query.count() == 0


def test_report_under_the_wrong_student_is_404(client, homeroom, student, make_report):
    report = make_report(student, severity=ReportSeverity.MINOR)
    classmate = Student.query.filter_by(name="Jordan Lee").one()
    base = f"/classes/{homeroom.id}/students/{classmate.id}/reports/{report.id}"

    edit = client.post(f"{base}/edit", data={"category": "DISRUPTION", "severity": "MAJOR"})
    assert edit.status_code == 404
    assert client.post(f"{base}/contact", data={"contact_sent_email": "on"}).status_code == 404
    assert client.post(f"{base}/delete").status_code == 404

    db.session.expire_all()
    report = db.session.get(BehaviorReport, report.id)
    assert report.category == "TARDINESS"
    assert report.contact_sent_email is False


# --- Bad values get 400/404 instead of a 500 ---------------------------------


@pytest.mark.parametrize(
    "form",
    [
        {"report_type": "BOGUS", "category": "ACADEMIC"},
        {"category": "ACADEMIC"},  # missing report_type
        {"report_type": "POSITIVE", "category": "TARDINESS"},  # negative-only category on a positive report
        {"report_type": "NEGATIVE", "category": "TARDINESS", "severity": "EXTREME"},
        {"report_type": "NEGATIVE", "category": "TARDINESS"},  # negative report missing severity
    ],
)
def test_add_report_with_bad_values_is_400(client, homeroom, student, form):
    response = client.post(f"/classes/{homeroom.id}/students/{student.id}/reports", data=form)
    assert response.status_code == 400
    assert BehaviorReport.query.count() == 0


def test_edit_report_with_bad_values_is_400(client, homeroom, student, make_report):
    report = make_report(student, severity=ReportSeverity.MINOR)
    url = f"/classes/{homeroom.id}/students/{student.id}/reports/{report.id}/edit"
    assert client.post(url, data={"category": "NOPE", "severity": "MINOR"}).status_code == 400
    assert client.post(url, data={"category": "DISRUPTION", "severity": "NOPE"}).status_code == 400

    db.session.expire_all()
    report = db.session.get(BehaviorReport, report.id)
    assert report.category == "TARDINESS"
    assert report.severity == ReportSeverity.MINOR


def test_unknown_report_type_in_url_is_404(client, homeroom):
    assert client.get(f"/classes/{homeroom.id}/reports/bogus").status_code == 404
    assert client.get(f"/classes/{homeroom.id}/reports/Positive").status_code == 200  # case-insensitive, as before
