from datetime import datetime, timezone
import pytest
from app.services.recommender import Embedder, recommend, cf_matrix, hybrid_weight
from app.services.intros import draft_intro
from app.services.graph import graph
from app.seed import synthetic_data
from app.eval import evaluate
from app.models import Recommendations, EvalResult


def member(i, **kwargs):
    return dict(id=i, name=f'Fake {i}', handle=None, github=None, devpost=None,
                builds='speech voice agents', wants='speech help', speaker_topics='voice speech',
                consent_intros=True, consent_speaker=True, is_seed=True, created_at=datetime.now(timezone.utc), **kwargs)


def row(a, b, kind='like'):
    return dict(member_id=a, target_id=b, kind=kind, is_seed=True)


def test_cf_cosine_and_concrete_co_likers():
    members = [member(i) for i in range(1, 7)]
    interactions = [row(1, 2), row(1, 3), row(4, 2), row(4, 5), row(6, 3), row(6, 5)]
    matrix, sims, ids = cf_matrix(members, interactions)
    assert sims[ids[2], ids[5]] == pytest.approx(0.5)
    assert sims[ids[3], ids[5]] == pytest.approx(0.5)
    result = recommend(1, members, interactions, encoder=Embedder('tf-idf'))
    target = next(item for item in result['items'] if item['member']['id'] == 5)
    reason = next(r for r in target['reasons'] if r['kind'] == 'cf')
    assert reason['evidence']['co_likers'] == 2
    assert {liked['id'] for liked in reason['evidence']['liked']} == {2, 3}
    Recommendations.model_validate(result)


def test_accept_weight():
    matrix, _, _ = cf_matrix([member(1), member(2)], [row(1, 2, 'accept')])
    assert matrix[0, 1] == 2


def test_exclusions_and_consent():
    members = [member(i) for i in range(1, 8)]
    members[3]['consent_intros'] = False
    interactions = [row(1, 2, 'pass'), row(1, 3, 'like'), row(1, 5, 'decline')]
    result = recommend(1, members, interactions, [{'member_id': 6, 'target_id': 1}], encoder=Embedder('tf-idf'))
    assert [item['member']['id'] for item in result['items']] == [7]
    members[0]['consent_intros'] = False
    assert recommend(1, members, interactions)['items'] == []


def test_hybrid_weight_growth():
    assert hybrid_weight(0) == 0
    assert 0 < hybrid_weight(1) < hybrid_weight(10) < hybrid_weight(100) < 0.7


def test_empty_and_cold_start():
    assert recommend(1, [member(1)], [], encoder=Embedder('tf-idf'))['items'] == []
    result = recommend(1, [member(1), member(2)], [], encoder=Embedder('tf-idf'))
    assert result['model']['cf_weight'] == 0
    assert result['items'][0]['member']['id'] == 2
    with pytest.raises(KeyError):
        recommend(99, [], [], encoder=Embedder('tf-idf'))


def test_llm_unavailable_no_fabrication():
    outcome = draft_intro({'reasons': []}, api_key='')
    assert outcome == dict(message=None, llm_used=False, status='drafted', error=None)


def test_llm_failure():
    class BrokenClient:
        @property
        def chat(self):
            raise RuntimeError('unavailable')
    result = draft_intro({'reasons': []}, api_key='test', client=BrokenClient())
    assert result['status'] == 'failed'
    assert result['message'] is None
    assert 'RuntimeError' in result['error']


def test_eval_four_models():
    result = evaluate(*synthetic_data(), encoder=Embedder('tf-idf'))
    assert {r['model'] for r in result['results']} == {'popularity', 'cf', 'content', 'hybrid'}
    assert result['n_test_users'] > 0 and result['n_holdout'] > 0
    assert all(0 <= r['hit_rate'] <= 1 and 0 <= r['precision'] <= 1 for r in result['results'])
    EvalResult.model_validate(result)


def test_empty_eval_and_graph():
    result = evaluate([], [], encoder=Embedder('tf-idf'))
    assert result['n_test_users'] == 0
    assert all(r['hit_rate'] == 0 for r in result['results'])
    assert graph([], [])['metrics']['density'] == 0
    network = graph([member(1), member(2), member(3)], [row(1, 2), row(2, 1)])
    assert network['metrics']['n_isolated'] == 1
    assert network['metrics']['density'] == pytest.approx(1/3)
