"""Compatibility CLI and explicit Alembic runner. No independent schema DDL."""
from contextlib import contextmanager
from pathlib import Path
import argparse

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

EXPECTED_DB_REVISION = '20260926_integrity'
BASELINE_REVISION = '20260926_stable'
ROOT = Path(__file__).resolve().parents[3]


def alembic_config(connection=None):
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'alembic'))
    if connection is not None:
        config.attributes['connection'] = connection
    return config


@contextmanager
def migration_connection(engine):
    with engine.connect() as connection:
        sqlite = connection.dialect.name == 'sqlite'
        if sqlite:
            # Only this exclusive maintenance connection may rebuild parent
            # tables. Application connections always enforce FKs.
            connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
            connection.commit()
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            connection.begin()
            connection.exec_driver_sql('SELECT pg_advisory_xact_lock(678240051)')
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            if sqlite:
                connection.exec_driver_sql('PRAGMA foreign_keys=ON')
                connection.commit()


def upgrade_connection(connection, revision='head', *, legacy_fragment=False):
    config = alembic_config(connection)
    inspector = inspect(connection)
    tables = set(inspector.get_table_names()) - {'alembic_version'}
    if 'sync_identity' in tables:
        version = connection.exec_driver_sql("SELECT value FROM sync_identity WHERE key='schema_version'").scalar()
        if version not in (None, '1'):
            raise RuntimeError('Unsupported sync schema version; refusing to downgrade')
    current = MigrationContext.configure(connection).get_current_revision()
    if current == EXPECTED_DB_REVISION and revision in ('head', BASELINE_REVISION):
        return
    if tables and current is None:
        # Explicitly recognize the manual schema; do not mark an arbitrary DB
        # as migrated. The new revisions still validate/rebuild all constraints.
        required = {'users': {'id', 'username', 'password_hash'},
                    'notes': {'id', 'user_id', 'blocks_json'},
                    'files': {'id', 'note_id', 'user_id', 'path_original'}}
        from app.db.migration_steps import metadata
        if not tables <= set(metadata().tables):
            raise RuntimeError('Unknown legacy tables; explicit migration review required')
        if not legacy_fragment:
            for table, columns in required.items():
                if table not in tables or not columns <= {c['name'] for c in inspector.get_columns(table)}:
                    raise RuntimeError('Unrecognized manual schema; explicit adoption review required')
        command.stamp(config, '20251226_init_auth')
    command.upgrade(config, revision)


def upgrade(engine=None, *, revision='head'):
    if engine is None:
        from app.db.session import engine
    with migration_connection(engine) as connection:
        upgrade_connection(connection, revision)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='head')
    args = parser.parse_args()
    upgrade(revision=args.revision)
