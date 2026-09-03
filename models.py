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

    reports = db.relationship("BehaviorReport", backref="student", lazy=True)

class ReportCategory(enum.Enum):
    POSITIVE = "Positive"
    NEGATIVE = "Negative"
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


class ReportSeverity(enum.Enum):
    MINOR = "Minor Concern"
    MODERATE = "Moderate Concern"
    MAJOR = "Major Concern"

class BehaviorReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)
    category = db.Column(db.Enum(ReportCategory), nullable=False)
    severity = db.Column(db.Enum(ReportSeverity), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    contacts = db.relationship("ParentContact", backref="report", lazy=True)


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

