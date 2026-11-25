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
    assert deletions == ['DELETE FROM intros', 'DELETE FROM intro_runs', 'DELETE FROM interactions WHERE is_seed=true']
    updates = [params for sql, params in statements if sql.startswith('UPDATE members')]
    assert len(updates) == 80
    assert all(p['id'] == 42 for p in updates)
    assert not any(sql.startswith('INSERT INTO members') for sql, _ in statements)


def test_profiles_varied_fictional_and_deterministic():
    members, interactions = seed.synthetic_data()
    assert (members, interactions) == seed.synthetic_data()
    assert len(members) == 80
    assert len({m['name'] for m in members}) == 80
    assert len({m['handle'] for m in members}) == 80
    assert all(m['is_seed'] and m['github'] is None and m['devpost'] is None for m in members)
    assert all(m['handle'].startswith('@') for m in members)
    for cluster in range(6):
        group = members[cluster::6]
        for field in ('builds', 'wants', 'speaker_topics'):
            assert len({m[field] for m in group}) >= 10
    assert sum(not m['consent_intros'] for m in members) == 8
    assert sum(m['consent_speaker'] for m in members) == 40
    assert not any(r['member_id'] >= 75 for r in interactions)
    assert not any(r['target_id'] >= 78 for r in interactions)
    assert len({(r['member_id'], r['target_id']) for r in interactions}) == len(interactions)


def test_like_probability_has_all_four_factors():
    base = seed.like_probability(False, False, False, 0, 0)
    assert seed.like_probability(True, False, False, 0, 0) > base
    assert seed.like_probability(False, True, False, 0, 0) > base
    assert seed.like_probability(False, True, True, 0, 0) > seed.like_probability(False, True, False, 0, 0)
    assert seed.like_probability(False, False, False, 1, 0) > base
    assert seed.like_probability(False, False, False, 0, .5) > base
    assert 0 < base < 1
