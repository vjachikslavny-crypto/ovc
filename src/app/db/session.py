from __future__ import annotations

from contextlib import contextmanager
import logging
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException
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
    except OperationalError as exc:
        session.rollback()
        if engine.dialect.name == 'sqlite' and ('locked' in str(exc.orig).lower() or 'busy' in str(exc.orig).lower()):
            logging.getLogger(__name__).warning('database_busy')
            raise HTTPException(503, 'Database busy; retry the operation', headers={'Retry-After':'1'}) from None
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
