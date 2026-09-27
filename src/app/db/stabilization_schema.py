"""Deprecated compatibility bootstrap; schema changes belong only to Alembic.

This historical helper stops at the additive baseline. It does not make an
unrepaired database ready. Normal deployment must run app.db.migrate to head.
"""
from app.db.migrate import BASELINE_REVISION, upgrade_connection


def upgrade(connection):
    upgrade_connection(connection, BASELINE_REVISION, legacy_fragment=True)
