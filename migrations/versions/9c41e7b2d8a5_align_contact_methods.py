"""Align ParentContact methods with the report contact checkboxes

ContactMethod changes from EMAIL/PHONE/IN_PERSON/OTHER to EMAIL/CALL/TEXT/OTHER,
matching BehaviorReport.CONTACT_METHODS. Existing rows are mapped across:
PHONE -> CALL, and IN_PERSON -> OTHER with "In person:" added to the start of
its notes so that detail isn't lost.

Revision ID: 9c41e7b2d8a5
Revises: 6af254fa3cff
Create Date: 2026-11-06 14:07:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c41e7b2d8a5'
down_revision = '6af254fa3cff'
branch_labels = None
depends_on = None

OLD_METHODS = sa.Enum('EMAIL', 'PHONE', 'IN_PERSON', 'OTHER', name='contactmethod')
NEW_METHODS = sa.Enum('EMAIL', 'CALL', 'TEXT', 'OTHER', name='contactmethod')

IN_PERSON_PREFIX = 'In person: '
IN_PERSON_ONLY = 'In person'


def upgrade():
    # Rewrite the data first, while every value is still valid for both enums'
    # column widths (SQLite stores these as VARCHAR without a CHECK constraint).
    op.execute("UPDATE parent_contact SET method = 'CALL' WHERE method = 'PHONE'")
    op.execute(
        "UPDATE parent_contact SET method = 'OTHER', "
        f"notes = CASE WHEN notes IS NULL OR notes = '' THEN '{IN_PERSON_ONLY}' "
        f"ELSE '{IN_PERSON_PREFIX}' || notes END "
        "WHERE method = 'IN_PERSON'"
    )
    with op.batch_alter_table('parent_contact', schema=None) as batch_op:
        batch_op.alter_column('method', existing_type=OLD_METHODS, type_=NEW_METHODS, existing_nullable=False)


def downgrade():
    with op.batch_alter_table('parent_contact', schema=None) as batch_op:
        batch_op.alter_column('method', existing_type=NEW_METHODS, type_=OLD_METHODS, existing_nullable=False)
    # Undo the in-person mapping where it's recognisable, then fold the new
    # methods back into the old set (TEXT has no old equivalent, so it's OTHER).
    op.execute(
        f"UPDATE parent_contact SET method = 'IN_PERSON', notes = NULL "
        f"WHERE method = 'OTHER' AND notes = '{IN_PERSON_ONLY}'"
    )
    op.execute(
        f"UPDATE parent_contact SET method = 'IN_PERSON', notes = substr(notes, {len(IN_PERSON_PREFIX) + 1}) "
        f"WHERE method = 'OTHER' AND notes LIKE '{IN_PERSON_PREFIX}%'"
    )
    op.execute("UPDATE parent_contact SET method = 'PHONE' WHERE method = 'CALL'")
    op.execute("UPDATE parent_contact SET method = 'OTHER' WHERE method = 'TEXT'")
