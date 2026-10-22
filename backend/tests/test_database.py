from contextlib import contextmanager
import runpy
from unittest.mock import patch
import pytest
from app import db, migrate


def test_every_connection_sets_network_search_path():
    with patch('sqlalchemy.create_engine') as create_engine, patch('sqlalchemy.event.listens_for', return_value=lambda fn: fn) as listens_for:
        runpy.run_path(db.__file__)
    kwargs = create_engine.call_args.kwargs
    assert kwargs['connect_args']['options'] == '-csearch_path=network'
    assert kwargs['connect_args']['connect_timeout'] == 5
    assert kwargs['pool_pre_ping'] is True
    listens_for.assert_called_once_with(create_engine.return_value, 'connect')


@pytest.mark.parametrize('autocommit', [True, False])
@pytest.mark.parametrize('fails', [True, False])
def test_search_path_hook_commits_session_setting_and_restores_autocommit(autocommit, fails):
    from unittest.mock import MagicMock
    connection = MagicMock()
    connection.autocommit = autocommit
    cursor = connection.cursor.return_value.__enter__.return_value
    def execute(sql):
        assert connection.autocommit is True
        assert sql == 'SET SESSION search_path TO network'
        if fails:
            raise RuntimeError('connection initialization failed')
    cursor.execute.side_effect = execute
    if fails:
        with pytest.raises(RuntimeError, match='connection initialization failed'):
            db.set_network_search_path(connection, None)
    else:
        db.set_network_search_path(connection, None)
    assert connection.autocommit is autocommit
    cursor.execute.assert_called_once()


@pytest.mark.parametrize('already_applied', [False, True])
def test_migration_bootstrap_and_bookkeeping_stay_in_network(monkeypatch, already_applied):
    statements, scripts = [], []
    class Connection:
        def execute(self, sql, params=None):
            statements.append(str(sql))
            return type('Result', (), {'scalar': lambda self: already_applied})()
        def exec_driver_sql(self, script):
            scripts.append(script)
    class Engine:
        @contextmanager
        def begin(self):
            yield Connection()
    monkeypatch.setattr(migrate, 'engine', Engine())
    migrate.main()
    assert statements.index('CREATE SCHEMA IF NOT EXISTS network') < next(i for i, sql in enumerate(statements) if sql.startswith('CREATE TABLE'))
    assert all('network.schema_migrations' in sql for sql in statements if 'schema_migrations' in sql)
    assert 'REVOKE ALL ON network.schema_migrations FROM anon, authenticated' in statements
    assert len(scripts) == (0 if already_applied else 2)
    if scripts:
        assert scripts[0].startswith('CREATE SCHEMA IF NOT EXISTS network;')
        assert all('SCHEMA public' not in script and 'public.' not in script for script in scripts)


def test_failed_migration_is_not_recorded(monkeypatch):
    recorded = []
    class Connection:
        def execute(self, sql, params=None):
            recorded.append(str(sql))
            return type('Result', (), {'scalar': lambda self: False})()
        def exec_driver_sql(self, script):
            raise RuntimeError('migration failed')
    class Engine:
        @contextmanager
        def begin(self):
            yield Connection()
    monkeypatch.setattr(migrate, 'engine', Engine())
    with pytest.raises(RuntimeError, match='migration failed'):
        migrate.main()
    assert not any(sql.startswith('INSERT INTO') for sql in recorded)
