"""Connection policy shared by application, migrations and isolated tests."""
from sqlalchemy import create_engine, event


def make_engine(url, **kwargs):
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if url.startswith('sqlite'):
        kwargs.setdefault('connect_args', {'check_same_thread': False})
    kwargs.setdefault("hide_parameters", True)  # SQL errors must not log private note/auth values.
    engine = create_engine(url, pool_pre_ping=True, **kwargs)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def configure(connection, _record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=10000')
    return engine
