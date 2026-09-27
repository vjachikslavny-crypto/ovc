"""All pytest runs use disposable storage, including modules with import-time setup."""
import os
from pathlib import Path
import sys
import tempfile
import sqlite3

import pytest

_data = tempfile.TemporaryDirectory(prefix="ovc-tests-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_data.name}/test.db", "OVC_UPLOAD_ROOT": f"{_data.name}/uploads",
    "AUTH_MODE": "local", "APP_ENV": "test", "DESKTOP_MODE": "false", "SYNC_MODE": "off",
    "SYNC_ENABLED": "false", "SYNC_REMOTE_BASE_URL": "", "SYNC_BEARER_TOKEN": "",
    "PUBLIC_MODE": "false", "PUBLIC_BASE_URL": "", "COOKIE_SECURE": "false", "COOKIE_SAMESITE": "lax",
    "GROQ_API_KEY": "", "SECRET_KEY": "isolated-test-secret-never-use-in-production",
    "OVC_ISOLATED_TESTS": "1", "DB_AUTO_MIGRATE": "false",
})

# Opt-in parity run, restricted to our disposable Stage 5 container/database.
_pg = os.getenv('OVC_STAGE5_POSTGRES_URL')
if _pg:
    from sqlalchemy.engine import make_url
    url = make_url(_pg)
    if (url.get_backend_name(), url.host, url.port, url.database, url.username) != (
            'postgresql', '127.0.0.1', 55435, 'ovc_stage5', 'postgres'):
        raise RuntimeError('Refusing tests outside the isolated Stage 5 PostgreSQL database')
    os.environ['DATABASE_URL'] = _pg


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    from app.db import session as db
    from app.main import app
    from app.db.base import Base
    from app.agent import token_counter
    from app.rag.tfidf_index import index
    from app.core.config import settings
    assert str(db.engine.url.database).startswith(_data.name) or (_pg and str(db.engine.url.database) == "ovc_stage5")
    previous_settings = dict(settings.__dict__)
    # Exercise the authoritative migration chain, never ORM create_all.
    from sqlalchemy import MetaData
    from app.db.migrate import upgrade
    seed = os.getenv('OVC_STAGE5_SQLITE_SEED')
    if seed:
        assert not _pg, 'Select either SQLite copy or PostgreSQL parity run'
        # Read the repaired snapshot into the guarded temporary test DB. Keep its
        # migrated schema, then replace private rows with ordinary test fixtures.
        db.engine.dispose()
        with sqlite3.connect(Path(seed).resolve().as_uri() + '?mode=ro', uri=True) as source:
            with sqlite3.connect(db.engine.url.database) as target:
                source.backup(target)
        upgrade(db.engine)
        schema = MetaData()
        schema.reflect(bind=db.engine)
        with db.engine.begin() as connection:
            for table in reversed(schema.sorted_tables):
                if table.name != 'alembic_version':
                    connection.execute(table.delete())
    else:
        schema = MetaData()
        schema.reflect(bind=db.engine)
        schema.drop_all(db.engine)
        upgrade(db.engine)
    app.dependency_overrides.clear()
    index.documents = []
    index.matrix = None
    index._loaded = False
    index._dirty = True
    from app.services.runtime import start_runtime
    from app.services.rate_limit import runtime_limiter
    start_runtime()
    runtime_limiter._hits.clear()
    # Do not download tokenizer data or call a live model during tests.
    monkeypatch.setattr(token_counter, "_tiktoken_enc", False)
    yield
    app.dependency_overrides.clear()
    settings.__dict__.clear()
    settings.__dict__.update(previous_settings)


def pytest_sessionfinish(session, exitstatus):
    from app.db.session import engine
    engine.dispose()
    _data.cleanup()
