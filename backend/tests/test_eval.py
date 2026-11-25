from collections import Counter
from app import eval as evaluation
from app.seed import synthetic_data


def test_splits_and_controlled_cold_start():
    members, interactions = synthetic_data()
    users = None
    holdouts = []
    for seed in range(5):
        train, held = evaluation.split_data(members, interactions, seed)
        assert set(held) == (users if users is not None else set(held))
        users = set(held)
        assert evaluation.split_data(members, interactions, seed) == (train, held)
        assert all(not (r['member_id'] in held and r['target_id'] in held[r['member_id']]) for r in train)
        cold = evaluation.cold_start_train(train, held, seed)
        counts = Counter(r['member_id'] for r in cold if r['kind'] == 'like')
        assert all(counts[u] == 2 for u in held)
        assert [r for r in train if r['member_id'] not in held] == [r for r in cold if r['member_id'] not in held]
        holdouts.append(held)
    assert holdouts[0] != holdouts[1]


def test_cache_first_get_and_explicit_refresh(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluation, '_last_result', None)
    monkeypatch.setattr(evaluation, 'snapshot', lambda: ([], []))
    def compute(*args):
        calls.append(1)
        return {'generation': len(calls)}
    monkeypatch.setattr(evaluation, 'evaluate', compute)
    assert evaluation.get_evaluation() == {'generation': 1}
    assert evaluation.get_evaluation() == {'generation': 1}
    assert evaluation.get_evaluation(refresh=True) == {'generation': 2}


def test_cache_retains_success_on_failure(monkeypatch):
    import pytest
    monkeypatch.setattr(evaluation, '_last_result', {'previous': True})
    def broken():
        raise RuntimeError('unavailable')
    monkeypatch.setattr(evaluation, 'snapshot', broken)
    with pytest.raises(RuntimeError):
        evaluation.get_evaluation(refresh=True)
    assert evaluation.get_evaluation() == {'previous': True}
