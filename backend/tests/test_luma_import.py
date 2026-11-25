import csv
import io
from pathlib import Path
from types import SimpleNamespace
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from app import db
from app import import_luma
from app.import_luma import import_csv
from app.models import MemberInput
from app.routes import api
from app.services import member_identity
from app.services.member_identity import submit_questionnaire
from app.services import demo, intros, speakers, threads
from app.services.recommender import Embedder, recommend

FIXTURE = Path(__file__).parent / 'fixtures/luma_fake.csv'


def test_import_upserts_members_events_and_attendance(database, monkeypatch):
    monkeypatch.setattr(import_luma, 'engine', database)
    first = import_csv(FIXTURE.read_bytes())
    assert first == dict(rows=3, members_created=2, members_matched=1, events_created=2, attendance_created=3)
    imported = rows(database, "SELECT * FROM members WHERE source='luma' ORDER BY id")
    assert len(imported) == 2 and all(not row['opted_in'] for row in imported)
    assert all(not row['consent_intros'] and not row['consent_speaker'] for row in imported)
    assert rows(database, 'SELECT count(*) AS n FROM interactions')[0]['n'] == 0
    assert rows(database, 'SELECT count(*) AS n FROM attendance')[0]['n'] == 3
    second = import_csv(FIXTURE.read_bytes())
    assert second['members_created'] == second['events_created'] == second['attendance_created'] == 0


def test_import_is_transactional_and_questionnaire_claims_luma_record(database, monkeypatch):
    monkeypatch.setattr(import_luma, 'engine', database)
    monkeypatch.setattr(member_identity, 'engine', database)
    import_csv(FIXTURE.read_bytes())
    row = rows(database, "SELECT * FROM members WHERE luma_profile_url='https://lu.ma/user/fake-ada'")[0]
    body = MemberInput(name=row['name'], luma_profile_url=row['luma_profile_url'], email=None,
                       handle=None, github=None, devpost=None, linkedin_url='self-entered headline',
                       builds='claimed builds', wants='claimed wants', speaker_topics='claimed topics',
                       consent_intros=True, consent_speaker=True)
    claimed = submit_questionnaire(body)
    assert claimed['id'] == row['id'] and claimed['opted_in']
    assert claimed['consent_intros'] and claimed['consent_speaker']
    with pytest.raises(ValueError, match='headers must be exactly'):
        import_csv(b'name,bad\n')
    assert rows(database, 'SELECT count(*) AS n FROM members')[0]['n'] == 2


def test_questionnaire_name_and_email_claims_existing_import(database, monkeypatch):
    monkeypatch.setattr(import_luma, 'engine', database)
    monkeypatch.setattr(member_identity, 'engine', database)
    import_csv(FIXTURE.read_bytes())
    with database.begin() as conn:
        conn.execute(text("UPDATE members SET email='ada@example.com' WHERE luma_profile_url='https://lu.ma/user/fake-ada'"))
    body = MemberInput(name='fictional ada example', email='ADA@example.com', luma_profile_url=None,
                       handle=None, github=None, devpost=None, linkedin_url=None, builds='b', wants='w',
                       speaker_topics='', consent_intros=True, consent_speaker=False)
    claimed = submit_questionnaire(body)
    assert claimed['source'] == 'luma' and claimed['opted_in']
    assert rows(database, "SELECT count(*) AS n FROM members WHERE source='luma'")[0]['n'] == 2


def test_import_endpoint_and_reset_preserve_luma_data(database, monkeypatch):
    monkeypatch.setattr(import_luma, 'engine', database)
    monkeypatch.setattr(member_identity, 'engine', database)
    app = FastAPI(); app.include_router(api.router)
    response = TestClient(app).post('/api/import/luma', files={'file': ('fake.csv', FIXTURE.read_bytes(), 'text/csv')})
    assert response.status_code == 200 and response.json()['members_created'] == 2
    before = rows(database, 'SELECT count(*) AS n FROM events')[0]['n']
    monkeypatch.setattr(demo, 'engine', database)
    demo.reset_demo()
    assert rows(database, 'SELECT count(*) AS n FROM events')[0]['n'] == before
    assert rows(database, "SELECT count(*) AS n FROM members WHERE source='luma'")[0]['n'] == 2


def test_not_opted_in_is_excluded_from_recommendations_intros_speakers_and_threads(database, monkeypatch):
    monkeypatch.setattr(import_luma, 'engine', database)
    import_csv(FIXTURE.read_bytes())
    data, interactions = db.snapshot()
    imported = next(member for member in data if member['source'] == 'luma')
    monkeypatch.setattr(intros, 'snapshot', lambda: (data, interactions))
    monkeypatch.setattr(intros, 'rows', lambda sql, *args: [] if 'SELECT member_id' in sql else [{'id': 1}])
    monkeypatch.setattr(intros, 'execute', lambda sql, params: [{'id': 1}])
    monkeypatch.setattr(intros, 'list_intros', lambda *args: [])
    result = recommend(imported['id'], data, interactions, encoder=Embedder('tf-idf'))
    assert result['items'] == []
    assert all(item['member']['id'] != imported['id'] for item in recommend(1, data, interactions, encoder=Embedder('tf-idf'))['items'])
    run = intros._run_intros('manual')
    assert run['intros'] == []
    speakers_result = asyncio.run(speakers.find_speakers(imported['name'], data, include_external=False))
    assert all(item.get('member_id') != imported['id'] for item in speakers_result['items'])
    thread_result = threads.analyze_chat(
        f'2026-10-01 12:00 | #private | {imported["name"]}: Anyone want to pair?\n'
        '2026-10-02 12:00 | #private | Maya R.: I can help.',
        now=threads.SUGGESTED_NOW, excluded_names=[imported['name']])
    assert thread_result.threads == [] and any(entry.step == 'privacy' for entry in thread_result.log)


def rows(engine, sql, params=None):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params or {}).mappings()]
