"""Notification outbox and pg_notify trigger (SCHEMA.md 4.11, SPEC FR-16).

Table drafted with autogenerate from NotificationOutboxRow and reviewed. Written by hand:
the trigger that calls pg_notify after each notification insert. PostgreSQL delivers
NOTIFY only when the inserting transaction commits, so a rolled-back leave action
never wakes the live stream (SPEC DB-23, DB-25).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16 10:41:28.269077
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name=op.f("ck_notification_outbox_status_values"),
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_notification_outbox_attempts_positive")),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name=op.f("fk_notification_outbox_notification_id_notifications"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_notification_outbox_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_outbox")),
        sa.UniqueConstraint("notification_id", name=op.f("uq_notification_outbox_notification_id")),
    )
    op.create_index(
        op.f("ix_notification_outbox_tenant_id"), "notification_outbox", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_outbox_pending",
        "notification_outbox",
        ["available_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ---------- Not expressible in the ORM (written by hand) ----------
    # The payload is tiny JSON (NOTIFY payloads must stay under 8000 bytes): the
    # listener loads the full notification from the table.
    op.execute(
        """
        CREATE FUNCTION notify_new_notification() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_notify(
            'leavedesk_notifications',
            json_build_object('id', NEW.public_id, 'tenant_id', NEW.tenant_id)::text
          );
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER notifications_notify AFTER INSERT ON notifications "
        "FOR EACH ROW EXECUTE FUNCTION notify_new_notification()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS notifications_notify ON notifications")
    op.execute("DROP FUNCTION IF EXISTS notify_new_notification()")
    op.drop_index(
        "ix_outbox_pending",
        table_name="notification_outbox",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index(op.f("ix_notification_outbox_tenant_id"), table_name="notification_outbox")
    op.drop_table("notification_outbox")
