"""The declarative base shared by every SQLAlchemy model.

The naming convention gives every index and constraint a predictable name
(ix_leave_requests_employee_id, ck_leave_requests_dates, ...). Alembic needs
stable names to drop or change a constraint later, and readable names make
database errors easy to trace back to a rule in SCHEMA.md.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    """Base class for all models. Tables are created only by Alembic revisions, never create_all()."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
