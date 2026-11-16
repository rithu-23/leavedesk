"""Idempotency keys for POST /leave-requests (SCHEMA.md 4.12, SPEC FR-15).

Drafted with autogenerate from IdempotencyKeyRow and reviewed. Autogenerate also
re-added ix_leave_requests_start_date_id (it compared against a development database
migrated before that index joined revision 0003); removed, as 0003 already creates it. Old rows may be deleted after 24 hours by a cleanup job (out of scope).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16 11:22:49.301548
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("leave_request_id", sa.BigInteger(), nullable=True),
        sa.Column("response_status", sa.SmallInteger(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(key) BETWEEN 1 AND 255", name=op.f("ck_idempotency_keys_key_length")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_idempotency_keys_employee_id_employees"),
        ),
        sa.ForeignKeyConstraint(
            ["leave_request_id"],
            ["leave_requests.id"],
            name=op.f("fk_idempotency_keys_leave_request_id_leave_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_idempotency_keys_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint(
            "tenant_id",
            "employee_id",
            "key",
            name=op.f("uq_idempotency_keys_tenant_id_employee_id_key"),
        ),
    )
    op.create_index(
        op.f("ix_idempotency_keys_employee_id"), "idempotency_keys", ["employee_id"], unique=False
    )
    op.create_index(
        op.f("ix_idempotency_keys_leave_request_id"),
        "idempotency_keys",
        ["leave_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_idempotency_keys_leave_request_id"), table_name="idempotency_keys")
    op.drop_index(op.f("ix_idempotency_keys_employee_id"), table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
