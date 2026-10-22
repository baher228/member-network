import asyncio
from types import SimpleNamespace
import httpx
import numpy as np
import pytest
from app.services import evidence as ev, speakers, intros, llm
from app.services.recommender import Embedder
from app.models import SpeakersResult


def test_evidence_live_then_cached(monkeypatch):
    cache = []
    monkeypatch.setattr(ev, 'rows', lambda *args: cache)
    def store(sql, params):
        import json
        cache.append({'payload': json.loads(params['payload']), 'fetched_at': params['at']})
    monkeypatch.setattr(ev, 'execute', store)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'items': []})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            live = await ev.cached_fetch(client, 'github', 'test', 'https://api.github.com/test')
            cached = await ev.cached_fetch(client, 'github', 'test', 'https://api.github.com/test')
            assert live[1] is True
            assert cached[1] is False
            assert live[2] == cached[2]
    asyncio.run(run())
    assert len(requests) == 1


def test_source_failures_do_not_crash(monkeypatch):
    async def broken(*args):
        raise httpx.ReadTimeout('test failure')
    for name in ('external_github', 'external_devpost', 'external_hn', 'external_luma'):
        monkeypatch.setattr(ev, name, broken)
    monkeypatch.setattr(speakers, 'embedder', Embedder('tf-idf'))
    result = asyncio.run(speakers.find_speakers('voice', [], True))
    assert result['items'] == []
    assert all(s['status'] == 'failed' for s in result['sources'])
    SpeakersResult.model_validate(result)


def test_external_disabled_no_calls(monkeypatch):
    monkeypatch.setattr(speakers, 'embedder', Embedder('tf-idf'))
    result = asyncio.run(speakers.find_speakers('voice', [], False))
    assert result['items'] == []
    assert all(s['status'] == 'skipped' for s in result['sources'])


@pytest.mark.parametrize('n_members,n_external,expected_members,expected_external', [
    (40, 20, 15, 15),
    (40, 3, 27, 3),
    (3, 40, 3, 27),
    (40, 0, 30, 0),
    (0, 40, 0, 30),
    (0, 0, 0, 0),
])
def test_speaker_groups_reserve_slots_and_fill_unused_capacity(monkeypatch, n_members, n_external, expected_members, expected_external):
    class MemberFavoredEmbedder:
        def encode(self, texts):
            return np.array([[1., 0.]] + [[1., 0.] if text.startswith('member') else [(int(text.split()[2])+1)/(n_external+1), 1.] for text in texts[1:]])
    monkeypatch.setattr(speakers, 'embedder', MemberFavoredEmbedder())
    async def public(*args):
        return [dict(kind='external', member_id=None, name=f'Public {i}', handle=None,
                     evidence=[ev.evidence('github', f'Public project {i}', f'https://github.com/example/project-{i}', 'public evidence', False, None)])
                for i in range(n_external)], False
    async def empty(*args):
        return [], False
    monkeypatch.setattr(ev, 'external_github', public)
    for name in ('external_devpost', 'external_hn', 'external_luma'):
        monkeypatch.setattr(ev, name, empty)
    members = [dict(id=i, name=f'Member {i}', handle=None, builds='member project', speaker_topics='member voice', consent_speaker=True)
               for i in range(n_members)]
    members.append(dict(id=-1, name='Not consenting', handle=None, builds='member project', speaker_topics='member voice', consent_speaker=False))
    result = asyncio.run(speakers.find_speakers('voice agents', members))
    member_results = [c for c in result['items'] if c['kind'] == 'member']
    external_results = [c for c in result['items'] if c['kind'] == 'external']
    assert len(member_results) == expected_members
    assert len(external_results) == expected_external
    assert all(c['member_id'] != -1 for c in member_results)
    assert all(c['score'] == 1 for c in member_results)
    assert all(c['score'] < 1 and c['evidence'] for c in external_results)
    assert [c['name'] for c in external_results] == [f'Public {i}' for i in reversed(range(n_external-expected_external, n_external))]
    assert [c['score'] for c in result['items']] == sorted((c['score'] for c in result['items']), reverse=True)
    SpeakersResult.model_validate(result)


def test_llm_structured_message():
    class Completions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"message":"Would both of you like an introduction?"}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    result = intros.draft_intro({'reasons': []}, client=client, api_key='fake-test-key')
    assert result['status'] == 'sent'
    assert result['llm_used'] is True
    assert result['message'] == 'Would both of you like an introduction?'


def test_run_no_key_stays_drafted(monkeypatch):
    members = [dict(id=1, consent_intros=True), dict(id=2, consent_intros=False)]
    monkeypatch.setattr(intros, 'snapshot', lambda: (members, []))
    monkeypatch.setattr(llm.settings, 'llm_provider', 'gemini')
    monkeypatch.setattr(llm.settings, 'gemini_api_key', '')
    monkeypatch.setattr(intros, 'rows', lambda *args: [] if 'SELECT member_id' in args[0] else [{'id': 1}])
    monkeypatch.setattr(intros, 'recommend', lambda *args, **kwargs: {'items': [{'member': {'id': 2}, 'score': 0.5, 'reasons': []}]})
    monkeypatch.setattr(intros, 'list_intros', lambda *args: [])
    writes = []
    def execute(sql, params):
        writes.append((sql, params))
        return [{'id': 1}]
    monkeypatch.setattr(intros, 'execute', execute)
    intros._run_intros('manual')
    update = next(params for sql, params in writes if sql.startswith('INSERT INTO intros('))[0]
    assert update['message'] is None and update['llm_used'] is False
    assert update['status'] == 'drafted'
    run = next(params for sql, params in writes if sql.startswith('UPDATE intro_runs'))
    assert run['llm_status'] == 'unavailable'
    assert run['drafted'] == 1 and run['skipped'] == 1
