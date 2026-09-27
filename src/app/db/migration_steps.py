"""Frozen Stage 5 schema operations, invoked only by ordered Alembic revisions.

The JSON snapshot is versioned with these revisions, never read from live ORM
models. Historical extra columns/indexes are retained during SQLite rebuilds.
"""
from pathlib import Path
import json
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateTable, CreateIndex
from alembic.operations import Operations
from alembic.migration import MigrationContext

SCHEMA = Path(__file__).resolve().parents[3] / 'alembic' / 'schema_v5.json'
NAMING = {'fk': 'fk_%(table_name)s_%(column_0_name)s', 'pk': 'pk_%(table_name)s',
          'uq': 'uq_%(table_name)s_%(column_0_name)s'}


def metadata(*, core=False):
    meta = sa.MetaData(naming_convention=NAMING)
    for spec in json.loads(SCHEMA.read_text()):
        if core and spec['name'] in {'users', 'refresh_tokens', 'audit_logs'}:
            continue
        columns = []
        for c in spec['columns']:
            if core and ((spec['name'] == 'notes' and c['name'] in
                    {'user_id', 'revision', 'tombstone', 'client_origin', 'last_client_ts'}) or
                    (spec['name'] == 'files' and c['name'] == 'user_id')):
                continue
            kind = getattr(sa, c['type'])()
            if c['type'] == 'JSON':
                kind = kind.with_variant(JSONB, 'postgresql')
            default = c['default']
            if isinstance(default, bool):
                default = sa.true() if default else sa.false()
            elif default is not None:
                default = str(default)
            elif c['type'] == 'DateTime' and not c['nullable']:
                default = sa.text('CURRENT_TIMESTAMP')
            columns.append(sa.Column(c['name'], kind, primary_key=c['primary_key'],
                                     nullable=c['nullable'], server_default=default))
        table = sa.Table(spec['name'], meta, *columns)
        for fk in spec['fks']:
            if core and (fk['target'] == 'users' or not set(fk['columns']) <= set(table.c.keys())):
                continue
            table.append_constraint(sa.ForeignKeyConstraint(fk['columns'],
                [fk['target'] + '.' + c for c in fk['target_columns']], name=fk['name'], ondelete=fk['ondelete']))
        for unique in spec['unique']:
            table.append_constraint(sa.UniqueConstraint(*unique['columns'], name=unique['name']))
        for idx in spec['indexes']:
            if set(idx['columns']) <= set(table.c.keys()):
                sa.Index(idx['name'], *(table.c[c] for c in idx['columns']), unique=idx['unique'])
    return meta


def bootstrap_core(connection):
    metadata(core=True).create_all(connection)


def stable_columns(connection):
    target = metadata()
    inspector = sa.inspect(connection)
    if inspector.has_table('sync_identity'):
        version = connection.execute(sa.text("SELECT value FROM sync_identity WHERE key='schema_version'")).scalar()
        if version not in (None, '1'):
            raise RuntimeError('Unsupported sync schema version; refusing to downgrade')
    for table in target.sorted_tables:
        if not sa.inspect(connection).has_table(table.name):
            table.create(connection)
            continue
        present = {c['name'] for c in sa.inspect(connection).get_columns(table.name)}
        for column in table.columns:
            if column.name not in present:
                added = column._copy()
                if connection.exec_driver_sql(f'SELECT count(*) FROM "{table.name}"').scalar() and (
                        column.server_default is None or column.type.__class__ == sa.DateTime):
                    # Adoption is additive; do not fabricate historical owners or
                    # timestamps. The final revision refuses unresolved NULLs.
                    added.nullable = True
                    added.server_default = None
                definition = sa.schema.CreateColumn(added).compile(dialect=connection.dialect)
                connection.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN {definition}')
    sa.Index('uq_sync_change_sequence', target.tables['sync_change_log'].c.sequence, unique=True).create(connection, checkfirst=True)
    for key, value in [('client_id', str(uuid.uuid4())), ('server_id', str(uuid.uuid4())),
                       ('sequence', '0'), ('schema_version', '1')]:
        connection.execute(sa.text('INSERT INTO sync_identity (key,value) VALUES (:k,:v) ON CONFLICT (key) DO NOTHING'), {'k': key, 'v': value})


def integrity_issues(connection):
    """Portable FK/owner validation; never returns content or secret values."""
    problems = []
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    for name in tables:
        if name.startswith('_') or name == 'alembic_version':
            continue
        for fk in inspector.get_foreign_keys(name):
            cols, remote = fk['constrained_columns'], fk['referred_columns']
            if fk['referred_table'] not in tables:
                problems.append({'table': name, 'kind': 'missing_parent_table'})
                continue
            match = ' AND '.join(f'p."{b}"=c."{a}"' for a, b in zip(cols, remote))
            required = ' AND '.join(f'c."{a}" IS NOT NULL' for a in cols)
            n = connection.exec_driver_sql(f'SELECT count(*) FROM "{name}" c WHERE {required} AND NOT EXISTS '
                f'(SELECT 1 FROM "{fk["referred_table"]}" p WHERE {match})').scalar()
            if n:
                problems.append({'table': name, 'kind': 'foreign_key', 'columns': cols, 'count': n})
    if {'notes', 'users'} <= tables:
        for name in ('notes', 'files'):
            if name in tables:
                n = connection.exec_driver_sql(f'SELECT count(*) FROM "{name}" x WHERE x.user_id IS NULL OR NOT EXISTS '
                    '(SELECT 1 FROM users u WHERE u.id=x.user_id)').scalar()
                if n: problems.append({'table': name, 'kind': 'orphan_owner', 'count': n})
        if 'note_links' in tables:
            n = connection.exec_driver_sql('SELECT count(*) FROM note_links l JOIN notes a ON a.id=l.from_id '
                'JOIN notes b ON b.id=l.to_id WHERE a.user_id IS NULL OR b.user_id IS NULL OR a.user_id<>b.user_id').scalar()
            if n: problems.append({'table': 'note_links', 'kind': 'cross_owner', 'count': n})
        if 'files' in tables:
            n = connection.exec_driver_sql('SELECT count(*) FROM files f JOIN notes n ON n.id=f.note_id '
                'WHERE f.user_id IS NULL OR n.user_id IS NULL OR f.user_id<>n.user_id').scalar()
            if n: problems.append({'table': 'files', 'kind': 'cross_owner', 'count': n})
    return problems


def enforce_schema(connection):
    problems = integrity_issues(connection)
    if problems:
        raise RuntimeError('Integrity repair required before migration head: ' + json.dumps(problems))
    target = metadata()
    ops = Operations(MigrationContext.configure(connection))
    for table in target.sorted_tables:
        inspector = sa.inspect(connection)
        old = sa.Table(table.name, sa.MetaData(), autoload_with=connection)
        # Refuse to make ambiguous missing values conform by guessing.
        for c in table.columns:
            if not c.nullable and connection.execute(sa.select(sa.func.count()).select_from(old).where(old.c[c.name].is_(None))).scalar():
                raise RuntimeError(f'Explicit repair required for NULL {table.name}.{c.name}')
        if connection.dialect.name == 'sqlite':
            # Maintenance connection only: FK enforcement is restored after the
            # atomic rebuild, with a mandatory foreign_key_check before commit.
            temp = table.to_metadata(target, name='_ovc_' + table.name)
            for c in old.columns:
                if c.name not in temp.c:
                    temp.append_column(c._copy())
            uniques = {tuple(c.name for c in u.columns) for u in temp.constraints if isinstance(u, sa.UniqueConstraint)}
            for u in inspector.get_unique_constraints(table.name):
                if tuple(u['column_names']) not in uniques:
                    temp.append_constraint(sa.UniqueConstraint(*u['column_names'], name=u['name']))
            known_fks = {tuple(e.parent.name for e in f.elements) for f in temp.foreign_key_constraints}
            for f in inspector.get_foreign_keys(table.name):
                if tuple(f['constrained_columns']) not in known_fks:
                    temp.append_constraint(sa.ForeignKeyConstraint(f['constrained_columns'],
                        [f['referred_table'] + '.' + c for c in f['referred_columns']], name=f['name'], **f['options']))
            for check in inspector.get_check_constraints(table.name):
                temp.append_constraint(sa.CheckConstraint(check['sqltext'], name=check['name']))
            # Preserve expressions, partial predicates and unknown compatibility
            # indexes verbatim, instead of approximating their semantics.
            old_indexes = connection.execute(sa.text("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name=:t AND sql IS NOT NULL"), {'t': table.name}).all()
            triggers = connection.execute(sa.text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=:t"), {'t': table.name}).scalars().all()
            if triggers:
                raise RuntimeError(f'Existing triggers require explicit migration review: {table.name}')
            connection.execute(CreateTable(temp))
            names = list(old.c.keys())
            connection.execute(temp.insert().from_select(names, sa.select(*(old.c[n] for n in names))))
            connection.exec_driver_sql(f'DROP TABLE "{table.name}"')
            connection.exec_driver_sql(f'ALTER TABLE "{temp.name}" RENAME TO "{table.name}"')
            for name, sql in old_indexes:
                if name not in {i.name for i in table.indexes}:
                    connection.exec_driver_sql(sql)
        else:
            existing_columns = {c['name']: c for c in inspector.get_columns(table.name)}
            for c in table.columns:
                if existing_columns[c.name]['nullable'] != c.nullable:
                    ops.alter_column(table.name, c.name, nullable=c.nullable)
            existing_fks = inspector.get_foreign_keys(table.name)
            for fk in table.foreign_key_constraints:
                cols = [e.parent.name for e in fk.elements]
                matching = [f for f in existing_fks if f['constrained_columns'] == cols]
                for old_fk in matching:
                    ops.drop_constraint(old_fk['name'], table.name, type_='foreignkey')
                ops.create_foreign_key(fk.name, table.name, fk.elements[0].column.table.name,
                    cols, [e.column.name for e in fk.elements], ondelete=fk.ondelete)
            existing_unique = {tuple(c['column_names']) for c in inspector.get_unique_constraints(table.name)}
            for uq in table.constraints:
                if isinstance(uq, sa.UniqueConstraint) and tuple(c.name for c in uq.columns) not in existing_unique:
                    ops.create_unique_constraint(uq.name, table.name, [c.name for c in uq.columns])
        for idx in table.indexes:
            idx.create(connection, checkfirst=True)
    install_owner_guards(connection)
    if connection.dialect.name == 'sqlite' and connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('FK validation failed after canonical schema rebuild')


def install_owner_guards(connection):
    condition = ('NOT EXISTS (SELECT 1 FROM notes a JOIN notes b ON a.user_id=b.user_id '
                 'WHERE a.id=NEW.from_id AND b.id=NEW.to_id AND a.user_id IS NOT NULL)')
    if connection.dialect.name == 'sqlite':
        for action in ('INSERT', 'UPDATE'):
            connection.exec_driver_sql(f"CREATE TRIGGER owner_note_links_{action.lower()} BEFORE {action} ON note_links "
                f"WHEN {condition} BEGIN SELECT RAISE(ABORT, 'Cross-owner relation forbidden'); END")
    else:
        connection.exec_driver_sql(f"CREATE OR REPLACE FUNCTION ovc_note_link_owner() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN IF {condition} THEN RAISE EXCEPTION 'Cross-owner relation forbidden' USING ERRCODE='23514'; "
            "END IF; RETURN NEW; END $$")
        connection.exec_driver_sql('CREATE TRIGGER owner_note_links BEFORE INSERT OR UPDATE ON note_links '
            'FOR EACH ROW EXECUTE FUNCTION ovc_note_link_owner()')
