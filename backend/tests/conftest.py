import pytest
import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from app import db, migrate
from app import import_luma
from app.services import demo, intros, member_identity
from app.services import llm


@pytest.fixture(autouse=True)
def offline_llm_defaults(monkeypatch):
    monkeypatch.setattr(llm.settings, 'llm_provider', 'gemini')
    for name in ('gemini_api_key', 'xai_api_key', 'cursor_api_key'):
        monkeypatch.setattr(llm.settings, name, '')
    monkeypatch.setattr(llm.settings, 'intro_llm_max_per_run', 10)
    monkeypatch.setattr(llm.settings, 'llm_model', '')
    monkeypatch.setattr(llm, '_calls_used', 0)
    monkeypatch.setattr(llm, '_last_call', None)
    monkeypatch.setattr(llm, '_probe_started', False)


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
    monkeypatch.setattr(db, 'engine', engine)
    monkeypatch.setattr(intros, 'engine', engine)
    monkeypatch.setattr(import_luma, 'engine', engine)
    monkeypatch.setattr(member_identity, 'engine', engine)
    migrate.main()
    with engine.begin() as conn:
        conn.execute(text('''TRUNCATE network.members,network.interactions,network.intros,
            network.intro_runs,network.thread_runs,network.evidence_cache,network.llm_cache,
            network.events,network.attendance RESTART IDENTITY'''))
    yield engine
    engine.dispose()
