"""Adopt additive Stages 0–4.1 columns without repairing/replaying data."""
from alembic import op
from app.db.migration_steps import stable_columns

revision = '20260926_stable'
down_revision = '20251226_init_auth'
branch_labels = depends_on = None


def upgrade():
    stable_columns(op.get_bind())


def downgrade():
    raise RuntimeError('Restore a verified backup; do not discard sync metadata')
