from __future__ import annotations

from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker
from app.db.engine import make_engine

from app.core.config import settings

# Fix postgres:// -> postgresql:// (SQLAlchemy requires postgresql://)
DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def get_session(*, immediate: bool = False):
    session = SessionLocal()
    try:
        if immediate and session.bind.dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
