from contextlib import contextmanager
from app import seed


def test_seed_preserves_member_ids_and_only_resets_seed_interactions(monkeypatch):
    statements = []
    class Result:
        def scalar_one_or_none(self):
            return 42
    class Connection:
        def execute(self, sql, params=None):
            statements.append((str(sql), params))
            return Result()
    class Engine:
        @contextmanager
        def begin(self):
            yield Connection()
    monkeypatch.setattr(seed, 'engine', Engine())
    seed.main()
    deletions = [sql for sql, _ in statements if sql.startswith('DELETE')]
    assert deletions == ['DELETE FROM interactions WHERE is_seed=true']
    updates = [params for sql, params in statements if sql.startswith('UPDATE members')]
    assert len(updates) == 80
    assert all(p['id'] == 42 for p in updates)
    assert not any(sql.startswith('INSERT INTO members') for sql, _ in statements)
