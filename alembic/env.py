from alembic import context
from app.db.migration_steps import metadata

config = context.config
target_metadata = metadata()


def run(connection):
    context.configure(connection=connection, target_metadata=target_metadata,
                      compare_type=True, transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError('These migrations inspect existing data; use an online maintenance connection')
connection = config.attributes.get('connection')
if connection is not None:
    run(connection)
else:
    from app.core.config import settings
    from app.db.engine import make_engine
    from app.db.migrate import migration_connection
    engine = make_engine(settings.database_url)
    try:
        with migration_connection(engine) as connection:
            run(connection)
    finally:
        engine.dispose()
