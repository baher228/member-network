import json
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.models import ThreadAnalysis
from app.routes.threads import router
from app.services import threads

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def discord(message, day=1, name='Maya R.', marker='#voice'):
    return f'2026-10-{day:02} 12:00 | {marker} | {name}: {message}'


def test_parser_both_formats_invalid_dates_and_bad_lines():
    text = '\n'.join([discord('Could someone help?'), '[02/10/2026, 18:04] Theo R.: I can try.',
                       'bad line', '[99/10/2026, 18:04] Maya R.: wrong date', '',
                       '2026-10-01 18:04 | #voice | : no author'])
    messages, skipped, log = threads.parse_chat(text)
    assert len(messages) == 2 and skipped == 4
    assert messages[0].thread == '#voice' and messages[1].thread is None
    assert all(m.at.tzinfo == timezone.utc for m in messages)
    assert len([entry for entry in log if not entry.ok]) == 4
    assert any(entry.step == 'parse.line.4' for entry in log)


def test_whatsapp_strict_silence_split_and_chronological_sort():
    text = '\n'.join(['[05/10/2026, 00:01] Maya R.: New chat?',
                       '[01/10/2026, 12:00] Theo R.: First.',
                       '[03/10/2026, 00:00] Maya R.: Exactly 36 hours later.'])
    messages, _, _ = threads.parse_chat(text)
    groups = threads.group_threads(messages)
    assert [len(v) for v in groups.values()] == [2, 1]


@pytest.mark.parametrize('last,participants,day,worth,question,unanswered', [
    ('Can anyone help with tracing?', 1, 1, True, True, 'Maya R.'),
    ('Anyone want to pair on tracing', 1, 1, True, False, 'Maya R.'),
    ('Happy to help review a design', 1, 1, True, False, 'Maya R.'),
    ('Here is an update.', 1, 1, False, False, None),
    ('Here is an update.', 2, 1, True, False, None),
    ('Solved, thanks!', 2, 1, False, False, None),
    ('All set.', 2, 1, False, False, None),
    ('Thanks, can anyone still help?', 2, 1, True, True, 'Maya R.'),
    ('Can anyone help?', 2, 19, False, True, 'Maya R.'),
    ('Can anyone help?', 2, 17, False, True, 'Maya R.'),
])
def test_rules(last, participants, day, worth, question, unanswered):
    text = (discord('Earlier reply.', day, 'Theo R.')+'\n' if participants == 2 else '') + discord(last, day)
    messages, _, _ = threads.parse_chat(text)
    result = threads.decide_thread('test', messages, NOW, silence_days=3)
    assert result.worth_reviving is worth
    assert result.ended_with_question is question
    assert result.unanswered_by == unanswered
    assert result.status == ('drafted' if worth else 'skipped')
    assert 0 <= result.score <= 1
    if not worth:
        assert result.score == 0
    assert any('days ago' in reason for reason in result.reasons)
    assert all('..' not in reason for reason in result.reasons)


def test_future_time_and_default_real_now():
    result = threads.analyze_chat(discord('Any ideas?', 25), now=NOW, api_key='')
    assert result.threads[0].days_silent == 0
    assert not result.threads[0].worth_reviving
    before = datetime.now(timezone.utc)
    result = threads.analyze_chat('', api_key='')
    assert f'{before.year}-' in next(entry.detail for entry in result.log if entry.step == 'group')


def test_unanswered_means_final_message_not_earlier_question():
    result = threads.analyze_chat(discord('Any ideas?')+'\n'+discord('Solved, thanks!', name='Theo R.'), now=NOW, api_key='')
    assert result.threads[0].unanswered_by is None
    assert not result.threads[0].worth_reviving


def test_sample_no_llm_and_reproducible_decisions():
    sample = threads.sample_chat()
    assert sample['suggested_now'] == NOW
    result = threads.analyze_chat(sample['log_text'], now=NOW, api_key='')
    assert result.parsed_lines == 152 and result.skipped_lines == 0
    assert len(result.threads) == 8
    assert sum(t.worth_reviving for t in result.threads) == 4
    assert all(t.nudge is None and not t.llm_used for t in result.threads)
    assert all(t.status == ('drafted' if t.worth_reviving else 'skipped') for t in result.threads)
    assert result == threads.analyze_chat(sample['log_text'], now=NOW, api_key='')
    ThreadAnalysis.model_validate(result)


@pytest.mark.parametrize('text,parsed,skipped', [('', 0, 0), ('bad\nalso bad', 0, 2)])
def test_empty_or_all_bad_input(text, parsed, skipped):
    result = threads.analyze_chat(text, now=NOW, api_key='')
    assert result.parsed_lines == parsed and result.skipped_lines == skipped
    assert result.threads == []


@pytest.mark.parametrize('content,status,nudge', [
    ('{"nudge":"Maya, is pairing on tracing still useful?"}', 'drafted', 'Maya, is pairing on tracing still useful?'),
    ('not json', 'failed', None),
    ('{"nudge":"   "}', 'failed', None),
    ('{"nudge":"Hello", "extra":"not allowed"}', 'failed', None),
])
def test_llm_validated_drafts_and_errors(content, status, nudge):
    completions = SimpleNamespace(create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))]))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = threads.analyze_chat(discord('Anyone want to pair on tracing?'), now=NOW, api_key='test-only', client=client)
    thread = result.threads[0]
    assert thread.status == status and thread.nudge == nudge and thread.llm_used
    if status == 'failed':
        assert thread.error and any(not entry.ok for entry in result.log)


def test_llm_call_failure_and_skipped_threads_never_call():
    class Broken:
        @property
        def chat(self):
            raise RuntimeError('do not leak this detail')
    result = threads.analyze_chat(discord('Any ideas?'), now=NOW, api_key='test-only', client=Broken())
    assert result.threads[0].status == 'failed'
    assert result.threads[0].error.endswith('RuntimeError')
    assert 'do not leak' not in result.model_dump_json()
    result = threads.analyze_chat(discord('Any ideas?', 19), now=NOW, api_key='test-only', client=Broken())
    assert result.threads[0].status == 'skipped' and not result.threads[0].llm_used


def test_persistence_records_result_id_and_log(monkeypatch):
    writes = []
    class Connection:
        def execute(self, sql, params):
            writes.append((str(sql), params))
            return SimpleNamespace(scalar_one=lambda: 23)
    class Engine:
        @contextmanager
        def begin(self):
            yield Connection()
    monkeypatch.setattr(threads, 'engine', Engine())
    monkeypatch.setattr(threads.settings, 'llm_provider', 'gemini')
    monkeypatch.setattr(threads.settings, 'gemini_api_key', '')
    result = threads.persist_analysis(threads.analyze_chat(discord('Any ideas?'), now=NOW, api_key=''))
    assert result.run_id == 23
    assert writes[0][1]['llm'] == 'unavailable'
    stored = json.loads(writes[-1][1]['result'])
    assert stored['run_id'] == 23 and stored['log'][-1]['step'] == 'persist'


def test_routes_no_db(monkeypatch):
    monkeypatch.setattr(threads.settings, 'llm_provider', 'gemini')
    monkeypatch.setattr(threads.settings, 'gemini_api_key', '')
    monkeypatch.setattr(threads, 'persist_analysis', lambda result: result.model_copy(update={'run_id': 42}))
    monkeypatch.setattr(threads, 'list_runs', lambda: [])
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    sample = client.get('/api/threads/sample').json()
    response = client.post('/api/threads/analyze', json={'log_text': sample['log_text'], 'now': sample['suggested_now']})
    assert response.status_code == 200 and response.json()['run_id'] == 42
    assert len(response.json()['threads']) == 8
    assert client.get('/api/threads/runs').json() == []
    assert client.post('/api/threads/analyze', json={'log_text': '', 'now': 'not a date'}).status_code == 422
