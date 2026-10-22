import json
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from app.config import Settings
from app.services import llm, intros, threads


def test_cursor_default_and_explicit_provider(monkeypatch):
    monkeypatch.delenv('LLM_PROVIDER', raising=False)
    monkeypatch.delenv('CURSOR_API_KEY', raising=False)
    assert Settings(_env_file=None).llm_provider == 'gemini'
    monkeypatch.setenv('CURSOR_API_KEY', 'test-only')
    assert Settings(_env_file=None).llm_provider == 'cursor'
    assert Settings(llm_provider='grok', _env_file=None).llm_provider == 'grok'
    assert Settings(llm_provider='', _env_file=None).llm_provider == 'cursor'
    assert Settings(_env_file=None).cursor_model == 'gemini-3.7-flash-high'


def cursor(monkeypatch, result='prefix ```json\n{"message":"Connect about {voice}?","extra":{"nested":true}}\n```'):
    monkeypatch.setattr(llm.settings, 'llm_provider', 'cursor')
    monkeypatch.setattr(llm.settings, 'cursor_api_key', 'test-only')
    directories = []
    def run(argv, **kwargs):
        directory = Path(kwargs['cwd'])
        assert directory.is_dir() and list(directory.iterdir()) == []
        assert 'member-network/backend' not in str(directory)
        directories.append(directory)
        assert argv[:7] == [str(Path.home() / '.local/bin/cursor-agent'), '-p', '--trust', '--model', llm.model_name(), '--output-format', 'json']
        assert '--mode' not in argv and 'test-only' not in argv[-1]
        assert kwargs['env']['CURSOR_API_KEY'] == 'test-only'
        assert 'DATABASE_URL' not in kwargs['env']
        assert kwargs['timeout'] == 60 and kwargs['stdin'] == subprocess.DEVNULL
        assert not kwargs.get('shell', False)
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(is_error=False, result=result)), stderr='')
    run_mock = MagicMock(side_effect=run)
    monkeypatch.setattr(llm.subprocess, 'run', run_mock)
    return run_mock, directories


def test_cursor_extracts_first_nested_json_validates_and_cleans_cwd(monkeypatch):
    run, directories = cursor(monkeypatch)
    for _ in range(2):
        result = intros.draft_intro({'reasons': []})
        assert result['message'] == 'Connect about {voice}?' and result['status'] == 'sent'
    assert run.call_count == 2 and directories[0] != directories[1]
    assert all(not directory.exists() for directory in directories)
    health = llm.health()
    assert health['provider'] == 'cursor' and health['state'] == 'working'
    assert health['last_call']['ok'] and health['last_call']['http_status'] is None


def test_model_override_and_cursor_alias(monkeypatch):
    run, _ = cursor(monkeypatch)
    monkeypatch.setattr(llm.settings, 'cursor_model', 'cursor-grok-4.5-high-fast')
    assert llm.health()['model'] == 'cursor-grok-4.5-high-fast'
    monkeypatch.setattr(llm.settings, 'llm_model', 'gemini-3.7-flash-high')
    intros.draft_intro({'reasons': []})
    assert run.call_args.args[0][4] == llm.health()['model'] == 'gemini-3.7-flash-high'


@pytest.mark.parametrize('failure', ['exit', 'envelope', 'json', 'missing', 'schema', 'timeout', 'missing_cli'])
def test_cursor_failures_are_explicit_sanitized_and_recorded(monkeypatch, failure):
    run, _ = cursor(monkeypatch)
    if failure == 'timeout':
        run.side_effect = subprocess.TimeoutExpired('private diagnostic test-only', 60)
    elif failure == 'missing_cli':
        run.side_effect = FileNotFoundError('private diagnostic test-only')
    else:
        payload = {'is_error': False, 'result': '{"message":"ok"}'}
        if failure == 'envelope':
            payload['is_error'] = True
            payload['result'] = 'private diagnostic test-only'
        elif failure == 'missing':
            payload['result'] = 'no object'
        elif failure == 'schema':
            payload['result'] = '{"message":""}'
        run.side_effect = None
        run.return_value = SimpleNamespace(returncode=1 if failure == 'exit' else 0,
            stdout='private diagnostic test-only' if failure == 'json' else json.dumps(payload), stderr='private diagnostic test-only')
    result = intros.draft_intro({'reasons': []})
    assert result['status'] == 'failed' and result['message'] is None
    assert 'test-only' not in result['error'] and 'private diagnostic' not in result['error']
    assert llm.health()['state'] == 'unavailable' and not llm.health()['last_call']['ok']
    assert run.call_count == 1


def test_shared_process_cap_and_cursor_probe_skipped(monkeypatch):
    run, _ = cursor(monkeypatch)
    llm.probe_once()
    assert run.call_count == 0 and llm._calls_used == 0
    for _ in range(40):
        assert intros.draft_intro({'reasons': []})['status'] == 'sent'
    result = intros.draft_intro({'reasons': []})
    assert run.call_count == 40 and llm._calls_used == 40
    assert result['error'] == 'call budget exhausted' and result['llm_used'] is False
    sample = threads.sample_chat()
    analysis = threads.analyze_chat(sample['log_text'], now=sample['suggested_now'])
    assert all(t.status == 'failed' and t.error == 'call budget exhausted' and not t.llm_used for t in analysis.threads if t.worth_reviving)
    assert run.call_count == 40


def test_process_cap_is_thread_safe(monkeypatch):
    run, _ = cursor(monkeypatch)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: intros.draft_intro({'reasons': []}), range(80)))
    assert run.call_count == 40 and llm._calls_used == 40
    assert sum(result['llm_used'] for result in results) == 40
    assert sum(result['error'] == 'call budget exhausted' for result in results) == 40


@pytest.mark.parametrize('cap', [0, 1, 2])
def test_intro_budget_uses_highest_scores_and_reuses_cached_pairs(monkeypatch, cap):
    monkeypatch.setattr(llm.settings, 'intro_llm_max_per_run', cap)
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only')
    monkeypatch.setattr(intros, 'snapshot', lambda: ([dict(id=i, consent_intros=True) for i in range(1, 5)], []))
    cache = [dict(member_id=1, target_id=5, message='Earlier drafted text')]
    monkeypatch.setattr(intros, 'rows', lambda sql, *args: cache if 'FROM llm_cache' in sql else ([] if 'SELECT member_id' in sql else [{'id': 1}]))
    monkeypatch.setattr(intros, 'recommend', lambda member_id, *args, **kwargs: {'items': [dict(member={'id': 5}, score=member_id / 10, reasons=[{'member': member_id}])]})
    generate = MagicMock(return_value=intros.IntroMessage(message='New drafted text'))
    monkeypatch.setattr(llm, 'generate_json', generate)
    monkeypatch.setattr(intros, 'list_intros', lambda *args: [])
    writes = []
    def execute(sql, params):
        writes.append((sql, params))
        return [{'id': 1}]
    monkeypatch.setattr(intros, 'execute', execute)
    intros._run_intros('manual')
    assert generate.call_count == cap
    assert [json.loads(call.args[0][1]['content'])[0]['member'] for call in generate.call_args_list] == [4, 3][:cap]
    outcomes = next(params for sql, params in writes if sql.startswith('INSERT INTO intros('))
    old = next(row for row in outcomes if row['member_id'] == 1)
    assert old['message'] == 'Earlier drafted text' and not old['llm_used']
    skipped = [row for row in outcomes if row['status'] == 'skipped']
    assert len(skipped) == 3 - cap and all(row['error'] == 'skipped: budget cap' and row['message'] is None for row in skipped)
    run = next(params for sql, params in writes if sql.startswith('UPDATE intro_runs'))
    assert run['drafted'] == cap + 1 and run['skipped'] == 3 - cap and run['failed'] == 0


def test_intro_llm_drafting_uses_five_workers(monkeypatch):
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only')
    members = [dict(id=i, consent_intros=True) for i in range(1, 11)]
    monkeypatch.setattr(intros, 'snapshot', lambda: (members, []))
    monkeypatch.setattr(intros, 'rows', lambda sql, *args: [] if 'FROM llm_cache' in sql or 'SELECT member_id' in sql else [{'id': 1}])
    monkeypatch.setattr(intros, 'recommend', lambda member_id, *args, **kwargs: {'items': [
        dict(member={'id': member_id + 100}, score=member_id, reasons=[])]})
    monkeypatch.setattr(intros, 'list_intros', lambda *args: [])
    active = 0
    maximum = 0
    lock = threading.Lock()
    barrier = threading.Barrier(5)
    def generate(*args, **kwargs):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        barrier.wait(timeout=2)
        time.sleep(.02)
        with lock:
            active -= 1
        return intros.IntroMessage(message='parallel draft')
    monkeypatch.setattr(llm, 'generate_json', generate)
    writes = []
    def execute(sql, params):
        writes.append((sql, params))
        return [{'id': 1}]
    monkeypatch.setattr(intros, 'execute', execute)
    intros._run_intros('manual')
    assert maximum == 5
    outcomes = next(params for sql, params in writes if sql.startswith('INSERT INTO intros('))
    assert len(outcomes) == 10 and all(row['llm_used'] for row in outcomes)


def test_intro_run_selects_only_requested_member(monkeypatch):
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only')
    monkeypatch.setattr(intros, 'snapshot', lambda: ([dict(id=i, consent_intros=True) for i in (1, 2, 3)], []))
    monkeypatch.setattr(intros, 'rows', lambda sql, *args: [] if 'FROM llm_cache' in sql or 'SELECT member_id' in sql else [{'id': 1}])
    recommend = MagicMock(return_value={'items': [dict(member={'id': 3}, score=.5, reasons=[])]})
    monkeypatch.setattr(intros, 'recommend', recommend)
    generate = MagicMock(return_value=intros.IntroMessage(message='one draft'))
    monkeypatch.setattr(llm, 'generate_json', generate)
    monkeypatch.setattr(intros, 'list_intros', lambda *args: [])
    writes = []
    monkeypatch.setattr(intros, 'execute', lambda sql, params: writes.append((sql, params)) or [{'id': 1}])
    intros._run_intros('manual', member_id=2)
    assert recommend.call_count == generate.call_count == 1
    assert recommend.call_args.args[0] == 2
    outcomes = next(params for sql, params in writes if sql.startswith('INSERT INTO intros('))
    assert len(outcomes) == 1 and outcomes[0]['member_id'] == 2
