"""init auth tables

Revision ID: 20251226_init_auth
Revises: 
Create Date: 2025-12-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20251226_init_auth"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("role", sa.String(), nullable=False, server_default=sa.text("'user'")),
    )
    op.create_index("idx_user_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("fingerprint_hash", sa.String(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
    )
    op.create_index("idx_token_user", "refresh_tokens", ["user_id"], unique=False)
    op.create_index("idx_token_expires", "refresh_tokens", ["expires_at"], unique=False)
    op.create_index("idx_token_hash", "refresh_tokens", ["token_hash"], unique=False)
    op.create_index(
        "idx_token_active",
        "refresh_tokens",
        ["user_id"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON().with_variant(postgresql.JSONB, "postgresql"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_audit_event_time", "audit_logs", ["event", "created_at"], unique=False)

    op.add_column("notes", sa.Column("user_id", sa.String(), nullable=True))
    op.add_column("notes", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("notes", sa.Column("tombstone", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("notes", sa.Column("client_origin", sa.String(), nullable=True))
    op.add_column("notes", sa.Column("last_client_ts", sa.DateTime(), nullable=True))
    op.create_foreign_key("fk_notes_user_id_users", "notes", "users", ["user_id"], ["id"], ondelete="CASCADE")

    op.add_column("files", sa.Column("user_id", sa.String(), nullable=True))
    op.create_foreign_key("fk_files_user_id_users", "files", "users", ["user_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("fk_files_user_id_users", "files", type_="foreignkey")
    op.drop_column("files", "user_id")

    op.drop_constraint("fk_notes_user_id_users", "notes", type_="foreignkey")
    op.drop_column("notes", "last_client_ts")
    op.drop_column("notes", "client_origin")
    op.drop_column("notes", "tombstone")
    op.drop_column("notes", "revision")
    op.drop_column("notes", "user_id")

    op.drop_index("idx_audit_event_time", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("idx_token_active", table_name="refresh_tokens")
    op.drop_index("idx_token_hash", table_name="refresh_tokens")
    op.drop_index("idx_token_expires", table_name="refresh_tokens")
    op.drop_index("idx_token_user", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("idx_user_email", table_name="users")
    op.drop_table("users")
