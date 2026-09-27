"""Validated canonical constraints, query indexes and ownership guard."""
from alembic import op
from app.db.migration_steps import enforce_schema

revision = '20260926_integrity'
down_revision = '20260926_stable'
branch_labels = depends_on = None


def upgrade():
    enforce_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Restore a verified backup; integrity enforcement is not downgraded')
