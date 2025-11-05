from app.db.models import Base
from app.db.session import engine


def upgrade() -> None:
    # Given the scale of schema changes between revisions we opt for a full
    # reset of SQLite structures. The application ships with demo data only,
    # so dropping tables is acceptable in development.
    with engine.begin() as conn:
        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)


if __name__ == "__main__":
    upgrade()
