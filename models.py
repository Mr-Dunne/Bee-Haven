#This file contains the database models for the Bee-Haven application. It defines the structure of the database tables and their relationships.

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import enum

db = SQLAlchemy()

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    classes = db.relationship("Class", backref="teacher", lazy=True)
    reports_filed = db.relationship("BehaviorReport", backref="filed_by", lazy=True)

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)

    students = db.relationship("Student", backref="parent_class", lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("class.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    parent_email = db.Column(db.String(120), nullable=True)
    parent_phone = db.Column(db.String(20), nullable=True)

    reports = db.relationship("BehaviorReport", backref="student", lazy=True, cascade="all, delete-orphan")

class ReportType(enum.Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"


class NegativeReportCategory(enum.Enum):
    DISRUPTION = "Disruption"
    TECH_MISUSE = "Inappropriate Use of Technology"
    ACADEMIC_DISHONESTY = "Academic Dishonesty"
    TARDINESS = "Tardiness"
    INCOMPLETE_WORK = "Lack of Completion"
    DISRESPECT = "Disrespect/Defiance"
    PHYSICAL_CONFLICT = "Physical Conflict"
    ATTENDANCE = "Attendance/Absence"
    PROPERTY_DAMAGE = "Property Damage"
    OTHER = "Other"


class PositiveReportCategory(enum.Enum):
    ACADEMIC = "Academic"
    BEHAVIORAL = "Behavioral"
    OTHER = "Other"


class ReportSeverity(enum.Enum):
    MINOR = "Minor Concern"
    MODERATE = "Moderate Concern"
    MAJOR = "Major Concern"

class BehaviorReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)
    report_type = db.Column(db.Enum(ReportType), nullable=False)
    # A single column can't be typed as "one of two enums" in SQLAlchemy, so this
    # stores the .name of whichever category enum matches report_type
    # (PositiveReportCategory or NegativeReportCategory) as plain text, and
    # category_enum() below resolves it back to the right enum member.
    category = db.Column(db.String(32), nullable=False)
    # Only negative reports carry a severity; positive reports leave this null.
    severity = db.Column(db.Enum(ReportSeverity), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Quick yes/no flags for whether this report has been communicated to the
    # parent, separate from the detailed ParentContact log below (which records
    # one row per contact attempt, with method/notes). The *_at timestamps
    # exist for the planned confirm-based cloud sync (CLAUDE.md), which needs
    # a "when did this change" marker on every field to detect conflicts.
    contact_sent = db.Column(db.Boolean, nullable=False, default=False)
    contact_sent_at = db.Column(db.DateTime, nullable=True)
    contact_received = db.Column(db.Boolean, nullable=False, default=False)
    contact_received_at = db.Column(db.DateTime, nullable=True)

    contacts = db.relationship("ParentContact", backref="report", lazy=True, cascade="all, delete-orphan")

    def category_enum(self):
        if self.report_type == ReportType.POSITIVE:
            return PositiveReportCategory[self.category]
        return NegativeReportCategory[self.category]

    def email_draft(self):
        # Draft only -- nothing here gets sent. The teacher copies this into
        # whatever email client they actually use, reviewing/editing first.
        student_name = self.student.name
        category_label = self.category_enum().value
        extra = f"{self.notes}\n\n" if self.notes else ""

        if self.report_type == ReportType.POSITIVE:
            subject = f"Great news about {student_name}"
            body = (
                f"Hi,\n\n"
                f"I wanted to share some positive news about {student_name}: {category_label}.\n\n"
                f"{extra}"
                f"Keep up the great work!\n\n"
                f"Best,\n[Your name]"
            )
        else:
            severity_note = f" ({self.severity.value})" if self.severity else ""
            subject = f"Regarding {student_name} -- {category_label}"
            body = (
                f"Hi,\n\n"
                f"I wanted to let you know that {student_name} was involved in an incident today "
                f"categorized as {category_label}{severity_note}.\n\n"
                f"{extra}"
                f"Please reach out if you'd like to discuss further.\n\n"
                f"Thank you,\n[Your name]"
            )
        return subject, body


class ContactMethod(enum.Enum):
    EMAIL = "Email"
    PHONE = "Phone Call"
    IN_PERSON = "In Person"
    OTHER = "Other"


class ParentContact(db.Model):
    # Logs each time a parent/guardian was actually contacted about a specific
    # report, separate from the student's on-file contact info (parent_email/
    # parent_phone on Student) so there's a record of what was communicated and when.
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("behavior_report.id"), nullable=False)
    method = db.Column(db.Enum(ContactMethod), nullable=False)
    contacted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text, nullable=True)

