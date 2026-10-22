import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from app import db, eval as evaluation, migrate
from app.routes import api
from app.seed import synthetic_data
from app.services import demo
from app.services import intros, llm
from app.services.recommender import Embedder, recommend


@pytest.fixture
def database(monkeypatch):
    url = os.environ.get('DEMO_RESET_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set DEMO_RESET_TEST_DATABASE_URL to a dedicated local *_test database')
    parsed = make_url(url)
    assert parsed.host in ('localhost', '127.0.0.1') and parsed.database.endswith('_test')
    engine = create_engine(url)
    event.listen(engine, 'connect', db.set_network_search_path)
    monkeypatch.setattr(migrate, 'engine', engine)
    monkeypatch.setattr(demo, 'engine', engine)
    migrate.main()
    with engine.begin() as conn:
        conn.execute(text('''TRUNCATE network.members,network.interactions,network.intros,
            network.intro_runs,network.thread_runs,network.evidence_cache,network.llm_cache RESTART IDENTITY'''))
    yield engine
    engine.dispose()


def rows(engine, sql, params=None):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params or {}).mappings()]


def real_member(conn, name='Real member'):
    return conn.execute(text('''INSERT INTO members(name,builds,wants,speaker_topics,consent_intros)
        VALUES (:name,'real builds','real wants','real topic',true) RETURNING id'''), {'name': name}).scalar_one()


def intro_run(conn):
    return conn.execute(text("INSERT INTO intro_runs(trigger) VALUES ('manual') RETURNING id")).scalar_one()


def intro(conn, run_id, member_id, target_id):
    conn.execute(text('''INSERT INTO intros(run_id,member_id,target_id,score,status)
        VALUES (:run,:member,:target,.5,'drafted')'''), dict(run=run_id, member=member_id, target=target_id))


def state(engine):
    return {table: rows(engine, f'SELECT * FROM {table} ORDER BY id')
            for table in ('members', 'interactions', 'intros', 'intro_runs', 'thread_runs')}


def test_reset_preserves_non_seed_rows_and_thread_runs(database):
    with database.begin() as conn:
        first = real_member(conn)
    result = demo.reset_demo()
    assert result['seed_members_created'] == 80
    seed_id = rows(database, "SELECT id FROM members WHERE handle='@maya_r'")[0]['id']
    assert seed_id != first
    with database.begin() as conn:
        second = real_member(conn, 'Second real member')
        conn.execute(text('''INSERT INTO interactions(member_id,target_id,kind,is_seed)
            VALUES (:member,:target,:kind,:seed)'''), [
                dict(member=first, target=seed_id, kind='like', seed=False),
                dict(member=seed_id, target=first, kind='accept', seed=False),
                dict(member=first, target=second, kind='pass', seed=True),
                dict(member=second, target=first, kind='decline', seed=False)])
        run = intro_run(conn)
        intro(conn, run, seed_id, first)
        intro(conn, run, first, second)
        conn.execute(text("INSERT INTO thread_runs(n_threads,n_revive,llm_status,result) VALUES (0,0,'unavailable','{}')"))
        conn.execute(text("UPDATE members SET name='Edited seed',handle='@edited',builds='edited' WHERE id=:id"), {'id': seed_id})
    before = state(database)
    demo.reset_demo()
    after = state(database)
    assert [m for m in before['members'] if not m['is_seed']] == [m for m in after['members'] if not m['is_seed']]
    mixed = lambda r: r['member_id'] in (first, second) or r['target_id'] in (first, second)
    assert list(filter(mixed, before['interactions'])) == list(filter(mixed, after['interactions']))
    assert before['intros'] == after['intros']
    assert before['intro_runs'] == after['intro_runs']
    assert before['thread_runs'] == after['thread_runs']
    restored = next(m for m in after['members'] if m['id'] == seed_id)
    expected = synthetic_data()[0][0]
    assert all(restored[key] == value for key, value in expected.items() if key != 'id')


def test_two_resets_identical_including_ids_timestamps_and_caches(database, monkeypatch):
    demo.reset_demo()
    with database.begin() as conn:
        conn.execute(text("UPDATE members SET builds='edited' WHERE id=1"))
        conn.execute(text('DELETE FROM interactions WHERE id=(SELECT min(id) FROM interactions)'))
        conn.execute(text('''INSERT INTO interactions(member_id,target_id,kind,is_seed)
            SELECT member_id,target_id,kind,is_seed FROM interactions ORDER BY id LIMIT 1'''))
        conn.execute(text("INSERT INTO interactions(member_id,target_id,kind,is_seed) VALUES (1,2,'pass',false)"))
    monkeypatch.setattr(evaluation, '_last_result', {'stale': True})
    monkeypatch.setattr(demo.embedder, 'cache', {'stale': [1]})
    first = demo.reset_demo()
    assert first['interactions_created'] == 1 and first['interactions_deleted'] == 2
    assert evaluation._last_result is None and demo.embedder.cache == {}
    before = state(database)
    second = demo.reset_demo()
    assert state(database) == before
    assert second['interactions_created'] == second['interactions_deleted'] == 0
    expected = {(r['member_id'], r['target_id'], r['kind'], r['is_seed']) for r in synthetic_data()[1]}
    actual = [(r['member_id'], r['target_id'], r['kind'], r['is_seed']) for r in before['interactions']]
    assert set(actual) == expected and len(actual) == len(expected) == 512


def test_seed_only_intros_and_empty_runs_removed(database):
    demo.reset_demo()
    with database.begin() as conn:
        real = real_member(conn)
        seed_run, mixed_run, empty_run = intro_run(conn), intro_run(conn), intro_run(conn)
        intro(conn, seed_run, 1, 2)
        intro(conn, seed_run, 2, 3)
        intro(conn, mixed_run, 3, 4)
        intro(conn, mixed_run, 1, real)
    surviving = rows(database, 'SELECT * FROM intros WHERE target_id=:real', {'real': real})
    result = demo.reset_demo()
    assert result['intros_deleted'] == 3 and result['intro_runs_deleted'] == 2
    assert rows(database, 'SELECT * FROM intros') == surviving
    assert [r['id'] for r in rows(database, 'SELECT * FROM intro_runs')] == [mixed_run]
    assert seed_run != empty_run


def test_reset_failure_rolls_back_all_mutations_and_keeps_caches(database, monkeypatch):
    demo.reset_demo()
    with database.begin() as conn:
        intro(conn, intro_run(conn), 1, 2)
        conn.execute(text("UPDATE members SET builds='edited' WHERE id=1"))
    before = state(database)
    profiles, interactions = synthetic_data()
    interactions.append(dict(member_id=1, target_id=2, kind='invalid', is_seed=True))
    monkeypatch.setattr(demo, 'synthetic_data', lambda: (profiles, interactions))
    monkeypatch.setattr(evaluation, '_last_result', {'keep': True})
    monkeypatch.setattr(demo.embedder, 'cache', {'keep': [1]})
    with pytest.raises(IntegrityError):
        demo.reset_demo()
    assert state(database) == before
    assert evaluation._last_result == {'keep': True} and demo.embedder.cache == {'keep': [1]}


def test_demo_reset_response_shape(monkeypatch):
    expected = dict(seed_members_restored=80, seed_members_created=0, seed_interactions_restored=512,
                    interactions_deleted=2, interactions_created=1, intros_deleted=3, intro_runs_deleted=2)
    monkeypatch.setattr(api, 'reset_demo', lambda: expected)
    app = FastAPI()
    app.include_router(api.router)
    response = TestClient(app).post('/api/demo/reset')
    assert response.status_code == 200 and response.json() == expected


def test_recommendations_immediately_exclude_new_like_and_pass(database, monkeypatch):
    demo.reset_demo()
    monkeypatch.setattr(db, 'engine', database)
    encoder = Embedder('tf-idf')
    monkeypatch.setattr(api, 'recommend', lambda *args, **kwargs: recommend(*args, encoder=encoder, **kwargs))
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    url = '/api/members/75/recommendations?k=100'
    initial = client.get(url)
    assert initial.status_code == 200
    targets = [item['member']['id'] for item in initial.json()['items'][:2]]
    assert len(targets) == 2
    for kind, target in zip(('like', 'pass'), targets):
        response = client.post('/api/interactions', json=dict(member_id=75, target_id=target, kind=kind))
        assert response.status_code == 200
    refreshed = client.get(url)
    assert refreshed.status_code == 200
    assert set(targets).isdisjoint(item['member']['id'] for item in refreshed.json()['items'])


def test_drafted_cache_survives_demo_reset_and_reuses_without_calls(database, monkeypatch):
    demo.reset_demo()
    monkeypatch.setattr(db, 'engine', database)
    encoder = Embedder('tf-idf')
    monkeypatch.setattr(intros, 'recommend', lambda *args, **kwargs: recommend(*args, encoder=encoder, **kwargs))
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only')
    calls = []
    def generate(*args, **kwargs):
        calls.append(1)
        return intros.IntroMessage(message='A genuinely generated mocked intro.')
    monkeypatch.setattr(llm, 'generate_json', generate)
    first = intros._run_intros('manual')
    assert first['run']['n_drafted'] == 10 and len(calls) == 10
    cached = rows(database, 'SELECT * FROM llm_cache ORDER BY member_id,target_id')
    assert len(cached) == 10
    demo.reset_demo()
    assert rows(database, 'SELECT * FROM llm_cache ORDER BY member_id,target_id') == cached
    monkeypatch.setattr(llm.settings, 'intro_llm_max_per_run', 0)
    second = intros._run_intros('manual')
    assert len(calls) == 10 and second['run']['n_drafted'] == 10
    assert all(not row['llm_used'] for row in second['intros'])
