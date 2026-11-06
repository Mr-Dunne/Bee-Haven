from models import BehaviorReport, Class, ParentContact, ReportSeverity, ReportType, Student, db


# --- Classes -----------------------------------------------------------------


def test_add_class_creates_it_and_ignores_blank_names(client, teacher):
    response = client.post("/classes", data={"name": "  Period 5 Biology  "})
    new_class = Class.query.filter_by(name="Period 5 Biology").one()
    assert new_class.teacher_id == teacher.id
    assert response.headers["Location"].endswith(f"/classes/{new_class.id}")

    client.post("/classes", data={"name": "   "})
    assert Class.query.count() == 2  # seeded homeroom + Biology, no blank class


def test_edit_class_renames_it(client, homeroom):
    client.post(f"/classes/{homeroom.id}/edit", data={"name": "Period 4 Homeroom"})
    assert db.session.get(Class, homeroom.id).name == "Period 4 Homeroom"


def test_delete_class_removes_students_reports_and_contacts(client, homeroom, student, make_report):
    make_report(student, contacts=2)
    client.post(f"/classes/{homeroom.id}/delete")
    assert Class.query.count() == 0
    assert Student.query.count() == 0
    assert BehaviorReport.query.count() == 0
    assert ParentContact.query.count() == 0


# --- Students ----------------------------------------------------------------


def test_add_and_edit_student(client, homeroom):
    client.post(
        f"/classes/{homeroom.id}/students",
        data={"name": "Morgan Diaz", "parent_email": "morgan.parent@example.com", "parent_phone": ""},
    )
    morgan = Student.query.filter_by(name="Morgan Diaz").one()
    assert morgan.class_id == homeroom.id
    assert morgan.parent_phone is None  # blank optional fields are stored as NULL

    client.post(
        f"/classes/{homeroom.id}/students/{morgan.id}/edit",
        data={"name": "Morgan Diaz-Lee", "parent_email": "", "parent_phone": "555-0199"},
    )
    db.session.refresh(morgan)
    assert morgan.name == "Morgan Diaz-Lee"
    assert morgan.parent_email is None
    assert morgan.parent_phone == "555-0199"


def test_delete_student_removes_only_their_reports_and_contacts(client, homeroom, student, make_report):
    classmate = Student.query.filter_by(name="Jordan Lee").one()
    make_report(student, contacts=1)
    kept = make_report(classmate, contacts=1)

    client.post(f"/classes/{homeroom.id}/students/{student.id}/delete")

    assert db.session.get(Student, student.id) is None
    assert Student.query.count() == 5
    assert [r.id for r in BehaviorReport.query.all()] == [kept.id]
    assert [c.report_id for c in ParentContact.query.all()] == [kept.id]


# --- Behavior reports --------------------------------------------------------


def test_add_negative_report_keeps_severity(client, homeroom, student, teacher):
    client.post(
        f"/classes/{homeroom.id}/students/{student.id}/reports",
        data={"report_type": "NEGATIVE", "category": "DISRUPTION", "severity": "MAJOR", "notes": "  Talking  "},
    )
    report = BehaviorReport.query.one()
    assert report.report_type == ReportType.NEGATIVE
    assert report.category == "DISRUPTION"
    assert report.severity == ReportSeverity.MAJOR
    assert report.notes == "Talking"
    assert report.teacher_id == teacher.id


def test_positive_report_never_gets_a_severity(client, homeroom, student, make_report):
    # Even if the form sends one (the field is only hidden in the UI).
    client.post(
        f"/classes/{homeroom.id}/students/{student.id}/reports",
        data={"report_type": "POSITIVE", "category": "ACADEMIC", "severity": "MAJOR"},
    )
    report = BehaviorReport.query.one()
    assert report.report_type == ReportType.POSITIVE
    assert report.severity is None

    # Editing a positive report can't add one either.
    client.post(
        f"/classes/{homeroom.id}/students/{student.id}/reports/{report.id}/edit",
        data={"category": "BEHAVIORAL", "severity": "MINOR", "notes": ""},
    )
    db.session.refresh(report)
    assert report.category == "BEHAVIORAL"
    assert report.severity is None


def test_edit_report_updates_fields_but_not_type(client, homeroom, student, make_report):
    report = make_report(student, category="TARDINESS", severity=ReportSeverity.MINOR)
    client.post(
        f"/classes/{homeroom.id}/students/{student.id}/reports/{report.id}/edit",
        data={"report_type": "POSITIVE", "category": "DISRESPECT", "severity": "MODERATE", "notes": "Updated"},
    )
    db.session.refresh(report)
    assert report.report_type == ReportType.NEGATIVE
    assert report.category == "DISRESPECT"
    assert report.severity == ReportSeverity.MODERATE
    assert report.notes == "Updated"


def test_delete_report_removes_its_contacts(client, homeroom, student, make_report):
    report = make_report(student, contacts=2)
    client.post(f"/classes/{homeroom.id}/students/{student.id}/reports/{report.id}/delete")
    assert BehaviorReport.query.count() == 0
    assert ParentContact.query.count() == 0


def test_contact_checkboxes_set_keep_and_clear_timestamps(client, homeroom, student, make_report):
    report = make_report(student)
    url = f"/classes/{homeroom.id}/students/{student.id}/reports/{report.id}/contact"

    client.post(url, data={"contact_sent_email": "on"})
    db.session.refresh(report)
    assert report.contact_sent_email is True
    first_ticked_at = report.contact_sent_email_at
    assert first_ticked_at is not None
    assert report.contact_received_email is False and report.contact_received_email_at is None

    # Saving again with it still ticked must not move the original timestamp.
    client.post(url, data={"contact_sent_email": "on", "contact_received_call": "on"})
    db.session.refresh(report)
    assert report.contact_sent_email_at == first_ticked_at
    assert report.contact_received_call is True and report.contact_received_call_at is not None

    # Unticking clears both the flag and its timestamp.
    client.post(url, data={"contact_received_call": "on"})
    db.session.refresh(report)
    assert report.contact_sent_email is False
    assert report.contact_sent_email_at is None


# --- Teacher scoping ---------------------------------------------------------


def test_pages_only_list_the_current_teachers_classes(client, homeroom, other_teacher):
    for url in ["/", f"/classes/{homeroom.id}"]:
        page = client.get(url).get_data(as_text=True)
        assert "Period 3 Homeroom" in page
        assert "Someone Else&#39;s Class" not in page and "Someone Else's Class" not in page
