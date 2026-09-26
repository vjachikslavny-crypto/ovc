"""Missing prerequisite for the historical auth revision; frozen core schema."""
from alembic import op
from app.db.migration_steps import bootstrap_core

revision = '20251225_core'
down_revision = None
branch_labels = depends_on = None


def upgrade():
    bootstrap_core(op.get_bind())


def downgrade():
    raise RuntimeError('Destructive downgrade is unsupported; restore a verified backup')
