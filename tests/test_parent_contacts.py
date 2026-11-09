from datetime import datetime

from flask_migrate import downgrade, upgrade

from models import BehaviorReport, ContactMethod, ParentContact, db
from test_hardening import _confirm_messages


def _contacts_url(homeroom, student, report):
    return f"/classes/{homeroom.id}/students/{student.id}/reports/{report.id}/contacts"


def test_contact_methods_match_the_report_checkboxes():
    # The detailed log and the quick checkboxes should describe contact the same way.
    assert [m.name.lower() for m in ContactMethod] == BehaviorReport.CONTACT_METHODS
    assert [m.value for m in ContactMethod] == [
        BehaviorReport.CONTACT_METHOD_LABELS[m] for m in BehaviorReport.CONTACT_METHODS
    ]


def test_log_contact_defaults_to_now(client, homeroom, student, make_report):
    report = make_report(student)
    before = datetime.utcnow().replace(microsecond=0)
    response = client.post(_contacts_url(homeroom, student, report), data={"method": "CALL", "notes": "  Left voicemail  "})

    assert response.headers["Location"].endswith(f"/students/{student.id}#report-{report.id}")
    contact = ParentContact.query.one()
    assert contact.report_id == report.id
    assert contact.method == ContactMethod.CALL
    assert contact.notes == "Left voicemail"
    assert contact.contacted_at >= before


def test_log_contact_can_be_backdated_and_notes_are_optional(client, homeroom, student, make_report):
    report = make_report(student)
    client.post(_contacts_url(homeroom, student, report), data={"method": "TEXT", "contacted_on": "2026-10-30", "notes": ""})
    contact = ParentContact.query.one()
    assert contact.contacted_at == datetime(2026, 10, 30)
    assert contact.notes is None


def test_log_contact_with_bad_values_is_400(client, homeroom, student, make_report):
    report = make_report(student)
    url = _contacts_url(homeroom, student, report)
    assert client.post(url, data={"method": "PHONE"}).status_code == 400  # old method name
    assert client.post(url, data={}).status_code == 400
    assert client.post(url, data={"method": "EMAIL", "contacted_on": "30/10/2026"}).status_code == 400
    assert ParentContact.query.count() == 0


def test_delete_contact_removes_only_that_entry(client, homeroom, student, make_report):
    report = make_report(student, contacts=2)
    first, second = ParentContact.query.order_by(ParentContact.id).all()
    client.post(f"{_contacts_url(homeroom, student, report)}/{first.id}/delete")
    assert [c.id for c in ParentContact.query.all()] == [second.id]
    assert db.session.get(BehaviorReport, report.id) is not None


def test_contacts_are_reachable_only_through_their_own_report(client, homeroom, student, make_report):
    report = make_report(student, contacts=1)
    other_report = make_report(student)
    contact = ParentContact.query.one()

    # Deleting through a different report's URL must not find it.
    assert client.post(f"{_contacts_url(homeroom, student, other_report)}/{contact.id}/delete").status_code == 404
    # Adding under a report whose student isn't in the URL is a 404 too.
    other_url = f"/classes/{homeroom.id}/students/999/reports/{report.id}/contacts"
    assert client.post(other_url, data={"method": "EMAIL"}).status_code == 404

    assert ParentContact.query.count() == 1


def test_student_page_lists_log_with_working_delete_prompts(client, homeroom, student, make_report):
    report = make_report(student)
    url = _contacts_url(homeroom, student, report)
    client.post(url, data={"method": "EMAIL", "contacted_on": "2026-11-02", "notes": "Sent O'Brien's progress note"})
    client.post(url, data={"method": "CALL", "contacted_on": "2026-11-04"})

    page = client.get(f"/classes/{homeroom.id}/students/{student.id}").get_data(as_text=True)
    assert "Sent O&#39;Brien&#39;s progress note" in page
    # Newest first.
    assert page.index("2026-11-04") < page.index("2026-11-02")
    messages = _confirm_messages(page)
    assert "Delete this call entry from 2026-11-04? This cannot be undone." in messages
    assert "Delete this email entry from 2026-11-02? This cannot be undone." in messages


def test_migration_maps_old_contact_methods(app, student, make_report):
    # Roll back to the baseline, insert rows the old way, and upgrade again.
    report_id = make_report(student).id
    db.session.remove()
    downgrade(revision="6af254fa3cff")
    rows = [("EMAIL", "e"), ("PHONE", "called"), ("IN_PERSON", "met at pickup"), ("IN_PERSON", None), ("OTHER", "x")]
    for method, notes in rows:
        db.session.execute(
            db.text("INSERT INTO parent_contact (report_id, method, notes) VALUES (:r, :m, :n)"),
            {"r": report_id, "m": method, "n": notes},
        )
    db.session.commit()
    db.session.remove()

    upgrade()

    result = db.session.execute(db.text("SELECT method, notes FROM parent_contact ORDER BY id")).all()
    assert [tuple(r) for r in result] == [
        ("EMAIL", "e"),
        ("CALL", "called"),
        ("OTHER", "In person: met at pickup"),
        ("OTHER", "In person"),
        ("OTHER", "x"),
    ]
