from sqlalchemy import text

from app.db.models import Base
from app.db.session import engine


def upgrade():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        statements = [
            "ALTER TABLE notes ADD COLUMN importance FLOAT NOT NULL DEFAULT 1.0",
            "ALTER TABLE notes ADD COLUMN cluster VARCHAR NOT NULL DEFAULT 'default'",
            "ALTER TABLE notes ADD COLUMN cluster_color VARCHAR NOT NULL DEFAULT '#8b5cf6'",
        ]
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                # Column already exists or backend does not support ALTER; ignore.
                pass


if __name__ == "__main__":
    upgrade()
