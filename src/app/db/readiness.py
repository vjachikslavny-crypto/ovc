"""Read-only schema checks and a disposable storage probe; no migration on requests."""
import tempfile
import logging
from pathlib import Path

import sqlalchemy as sa
from fastapi import HTTPException
from alembic.runtime.migration import MigrationContext

from app.db.migrate import EXPECTED_DB_REVISION
from app.db.migration_steps import metadata


def schema_checks(connection, *, columns=False):
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    expected = metadata()
    checks = {
        'database': True,
        'revision': MigrationContext.configure(connection).get_current_heads() == (EXPECTED_DB_REVISION,),
        'tables': set(expected.tables) <= tables,
        'foreign_keys': connection.dialect.name != 'sqlite' or connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1,
    }
    if columns:
        checks['columns'] = all(name in tables and set(table.c.keys()) <=
                               {c['name'] for c in inspector.get_columns(name)}
                               for name, table in expected.tables.items())
    return checks


def status(engine, storage, *, columns=True):
    try:
        with engine.connect() as connection:
            checks = schema_checks(connection, columns=columns)
    except Exception:
        # Never include driver error strings (URLs, SQL or credentials) publicly.
        checks = {'database': False, 'revision': False, 'tables': False, 'foreign_keys': False}
    try:
        from app.services.storage import require_space
        require_space(storage)
        with tempfile.TemporaryFile(dir=Path(storage)) as probe:
            probe.write(b'ovc-ready'); probe.flush(); probe.seek(0)
            checks['storage'] = probe.read() == b'ovc-ready'
    except (OSError, HTTPException):
        checks['storage'] = False
    if not all(checks.values()):
        logging.getLogger(__name__).warning('readiness_failed checks=%s', ','.join(k for k,v in checks.items() if not v))
    return {'ok': all(checks.values()), 'checks': checks}


def require_ready(engine, storage):
    result = status(engine, storage, columns=True)
    if not result['ok']:
        failed = ', '.join(k for k, ok in result['checks'].items() if not ok)
        raise RuntimeError(f'Database/storage not ready ({failed}). Run the explicit migration/repair procedure before starting OVC.')
