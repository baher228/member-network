from types import SimpleNamespace
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import MagicMock
import httpx
from openai import APIStatusError
import pytest
from pydantic import ValidationError
from app.config import Settings
from app.models import LLMHealth
from app.services import llm, intros, threads


@pytest.fixture(autouse=True)
def fresh_call_state(monkeypatch):
    monkeypatch.setattr(llm, '_last_call', None)
    monkeypatch.setattr(llm, '_probe_started', False)


@pytest.mark.parametrize('provider,key_name,model,base_url', [
    ('gemini', 'gemini_api_key', 'gemini-3.8-flash', 'https://generativelanguage.googleapis.com/v1beta/openai/'),
    ('grok', 'xai_api_key', 'grok-3-mini', 'https://api.x.ai/v1'),
])
def test_provider_selection_and_structured_drafting(monkeypatch, provider, key_name, model, base_url):
    monkeypatch.setattr(llm.settings, 'llm_provider', provider)
    monkeypatch.setattr(llm.settings, 'gemini_api_key', 'gemini-test-only')
    monkeypatch.setattr(llm.settings, 'xai_api_key', 'grok-test-only')
    constructor = MagicMock()
    client = constructor.return_value
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"message":"Would you both like to connect?"}'))])
    monkeypatch.setattr(llm, 'OpenAI', constructor)
    result = intros.draft_intro({'reasons': []})
    assert result['status'] == 'sent' and result['llm_used']
    assert result['message'] == 'Would you both like to connect?'
    assert constructor.call_args.kwargs['base_url'] == base_url
    assert constructor.call_args.kwargs['api_key'] == getattr(llm.settings, key_name)
    assert constructor.call_args.kwargs['max_retries'] == 0
    assert constructor.call_args.kwargs['timeout'] == 15
    call = client.chat.completions.create.call_args.kwargs
    assert call['model'] == model
    assert ('response_format' in call) is (provider == 'grok')
    assert 'JSON' in call['messages'][0]['content']
    health = llm.health()
    assert {key: health[key] for key in ('provider', 'model', 'available', 'reason', 'state')} == dict(provider=provider, model=model, available=True, reason=None, state='working')
    assert health['last_call']['ok'] and health['last_call']['http_status'] == 200
    LLMHealth.model_validate(llm.health())
    monkeypatch.setattr(llm.settings, key_name, '')
    assert not llm.health()['available']
    assert key_name.upper() in llm.health()['reason']
    assert intros.draft_intro({'reasons': []})['llm_used'] is False


def test_provider_defaults_and_model_override(monkeypatch):
    for name in ('LLM_PROVIDER', 'GEMINI_MODEL'):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.llm_provider == 'gemini' and settings.gemini_model == 'gemini-3.8-flash'
    monkeypatch.setattr(llm.settings, 'llm_provider', 'gemini')
    monkeypatch.setattr(llm.settings, 'gemini_model', 'custom-model')
    assert llm.health()['model'] == 'custom-model'
    with pytest.raises(ValidationError):
        Settings(llm_provider='unsupported', _env_file=None)


def test_invalid_json_still_validated_without_response_format(monkeypatch):
    monkeypatch.setattr(llm.settings, 'llm_provider', 'gemini')
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='not json'))])
    result = intros.draft_intro({'reasons': []}, api_key='test-only', client=client)
    assert result['status'] == 'failed' and result['message'] is None
    assert 'ValidationError' in result['error']
    assert llm.health()['last_call']['http_status'] == 200
    assert not llm.health()['last_call']['ok']


@pytest.mark.parametrize('status', [401, 402, 403, 404, 429, 500])
def test_provider_errors_sanitized_and_analysis_circuit_scoped_to_run(monkeypatch, status):
    monkeypatch.setattr(llm.settings, 'llm_provider', 'gemini')
    error = APIStatusError('private diagnostic', response=httpx.Response(status, request=httpx.Request('POST', 'https://example.com')), body={'error': 'private diagnostic'})
    client = MagicMock()
    client.chat.completions.create.side_effect = error
    result = intros.draft_intro({'reasons': []}, api_key='test-only', client=client)
    detail = f'HTTP {status}{"; provider credits unavailable" if status == 402 else ""}'
    expected = f'LLM call or structured response failed: APIStatusError ({detail})'
    assert result['status'] == 'failed' and result['error'] == expected
    sample = threads.sample_chat()
    for _ in range(2):
        client.chat.completions.create.reset_mock()
        result = threads.analyze_chat(sample['log_text'], now=sample['suggested_now'], api_key='test-only', client=client)
        selected = [t for t in result.threads if t.worth_reviving]
        blocked = status in (401, 402, 403, 404)
        assert client.chat.completions.create.call_count == (1 if blocked else len(selected))
        assert all(t.status == 'failed' and t.nudge is None for t in selected)
        assert sum(t.llm_used for t in selected) == (1 if blocked else len(selected))
        assert all(t.error == (expected if t.llm_used else f'Skipped LLM call: provider rejected an earlier request in this run ({detail})') for t in selected)
        assert all(t.status == 'skipped' and not t.llm_used for t in result.threads if not t.worth_reviving)
        assert all(entry.detail != 'No configured provider key: nudge remains null; no substitute text.' for entry in result.log if not entry.ok)
        assert 'private diagnostic' not in result.model_dump_json()


@pytest.mark.parametrize('status', [401, 402, 403, 404, 429, 500, None])
@pytest.mark.parametrize('first_success', [False, True])
def test_intro_run_circuit_and_new_run_retries(monkeypatch, status, first_success):
    error = APIStatusError('private diagnostic', response=httpx.Response(status, request=httpx.Request('POST', 'https://example.com')), body=None) if status else ValueError('invalid JSON; private diagnostic')
    generate = MagicMock(side_effect=error)
    monkeypatch.setattr(llm, 'generate_json', generate)
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only')
    monkeypatch.setattr(intros, 'snapshot', lambda: ([dict(id=i, consent_intros=i < 4) for i in range(1, 5)], []))
    monkeypatch.setattr(intros, 'recommend', lambda *args, **kwargs: {'items': [dict(member={'id': 5}, score=.5, reasons=[])]})
    monkeypatch.setattr(intros, 'rows', lambda *args: [] if 'SELECT member_id' in args[0] else [{'id': 1}])
    monkeypatch.setattr(intros, 'list_intros', lambda *args: [])
    writes = []
    def execute(sql, params):
        writes.append((sql, params))
        return [{'id': 1}]
    monkeypatch.setattr(intros, 'execute', execute)
    for _ in range(2):
        writes.clear()
        generate.reset_mock()
        generate.side_effect = [intros.IntroMessage(message='Would you both like to connect?'), error, error] if first_success else error
        intros._run_intros('manual')
        blocked = status in (401, 402, 403, 404)
        assert generate.call_count == (1 + int(first_success) if blocked else 3)
        batches = [params for sql, params in writes if sql.startswith('INSERT INTO intros(')]
        assert len(batches) == 1
        outcomes = batches[0]
        assert len(outcomes) == 3
        assert len(writes) == 3
        assert [row['status'] for row in outcomes] == (['sent', 'failed', 'failed'] if first_success else ['failed'] * 3)
        assert all(row['message'] is None for row in outcomes[int(first_success):])
        if first_success:
            assert outcomes[0]['message'] == 'Would you both like to connect?' and outcomes[0]['error'] is None
        assert [row['llm_used'] for row in outcomes] == (([True, True, False] if first_success else [True, False, False]) if blocked else [True] * 3)
        if blocked:
            assert all(row['error'].startswith('Skipped LLM call: provider rejected an earlier request in this run') for row in outcomes[1 + int(first_success):])
        assert all('private diagnostic' not in (row['error'] or '') for row in outcomes)
        run = next(params for sql, params in writes if sql.startswith('UPDATE intro_runs'))
        assert run['failed'] == 3 - int(first_success) and run['drafted'] == int(first_success) and run['skipped'] == 1
        assert run['llm_status'] == ('partial' if first_success else 'unavailable')


@pytest.mark.parametrize('error_type,status', [(llm.AuthenticationError, 401), (llm.PermissionDeniedError, 403), (llm.NotFoundError, 404)])
def test_sdk_equivalent_errors_without_status(error_type, status):
    error = error_type('private diagnostic', response=httpx.Response(status, request=httpx.Request('POST', 'https://example.com')), body=None)
    error.status_code = None
    circuit = llm.RunCircuitBreaker()
    circuit.record_failure(error)
    assert circuit.error.endswith(f'(HTTP {status})')


def test_health_tracks_real_calls_but_not_missing_key_or_circuit_skips(monkeypatch):
    monkeypatch.setattr(llm.settings, 'llm_provider', 'gemini')
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only')
    assert llm.health()['state'] == 'not_checked' and llm.health()['last_call'] is None
    intros.draft_intro({'reasons': []}, api_key='')
    assert llm.health()['last_call'] is None
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"message":"Would you both like to connect?"}'))])
    intros.draft_intro({'reasons': []}, client=client)
    health = llm.health()
    assert health['state'] == 'working' and health['last_call']['error'] is None
    assert datetime.fromisoformat(health['last_call']['at']).tzinfo == timezone.utc
    health['last_call']['ok'] = False
    assert llm.health()['last_call']['ok']
    error = APIStatusError('private diagnostic', response=httpx.Response(402, request=httpx.Request('POST', 'https://example.com')), body=None)
    client.chat.completions.create.side_effect = error
    sample = threads.sample_chat()
    threads.analyze_chat(sample['log_text'], now=sample['suggested_now'], client=client)
    health = llm.health()
    assert client.chat.completions.create.call_count == 2
    assert health['state'] == 'unavailable' and health['available'] is True
    assert health['last_call']['ok'] is False and health['last_call']['http_status'] == 402
    assert health['reason'] == health['last_call']['error'] and 'private diagnostic' not in health['reason']
    circuit = llm.RunCircuitBreaker()
    circuit.record_failure(error)
    intros.draft_intro({'reasons': []}, client=client, circuit=circuit)
    assert llm.health() == health
    client.chat.completions.create.side_effect = None
    intros.draft_intro({'reasons': []}, client=client)
    assert llm.health()['state'] == 'working'
    monkeypatch.setattr(llm, 'get_api_key', lambda: '')
    health = llm.health()
    assert health['state'] == 'unavailable' and health['available'] is False
    assert health['reason'] == 'GEMINI_API_KEY is not configured'
    assert health['last_call']['ok'] is True


def test_generation_failure_without_http_response(monkeypatch):
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError('private diagnostic')
    intros.draft_intro({'reasons': []}, api_key='test-only', client=client)
    assert llm.health()['last_call']['http_status'] is None
    assert llm.health()['last_call']['error'] == 'LLM call or structured response failed: RuntimeError'


@pytest.mark.parametrize('drafted,failed,key,expected', [
    (0, 0, True, 'unavailable'), (0, 2, True, 'unavailable'),
    (1, 2, True, 'partial'), (2, 0, True, 'available'),
    (2, 0, False, 'unavailable'), (1, 2, False, 'unavailable')])
def test_run_availability_counts(monkeypatch, drafted, failed, key, expected):
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only' if key else '')
    assert llm.run_status(drafted, failed) == expected


def test_probe_at_most_once_even_with_concurrent_startup_calls(monkeypatch):
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only')
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])
    monkeypatch.setattr(llm, 'create_client', lambda *args: client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: llm.probe_once(), range(8)))
    assert client.chat.completions.create.call_count == 1
    assert llm.health()['state'] == 'working'


def test_failed_probe_records_result_once_and_missing_key_does_not_probe(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(llm, 'create_client', lambda *args: client)
    monkeypatch.setattr(llm, 'get_api_key', lambda: '')
    llm.probe_once()
    assert llm.health()['last_call'] is None
    client.chat.completions.create.assert_not_called()
    monkeypatch.setattr(llm, 'get_api_key', lambda: 'test-only')
    client.chat.completions.create.side_effect = RuntimeError('private diagnostic')
    llm.probe_once()
    llm.probe_once()
    assert client.chat.completions.create.call_count == 1
    assert llm.health()['last_call']['error'].endswith('RuntimeError')
    assert llm.health()['state'] == 'unavailable'


def test_startup_does_not_wait_for_probe(monkeypatch):
    from app import main
    started, release = threading.Event(), threading.Event()
    def probe():
        started.set()
        release.wait(timeout=2)
    monkeypatch.setattr(main, 'probe_once', probe)
    monkeypatch.setattr(main, 'check_llm', lambda: None)
    monkeypatch.setattr(main, 'BackgroundScheduler', MagicMock())
    async def run():
        async with main.lifespan(main.app):
            try:
                assert await asyncio.to_thread(started.wait, 1)
                assert not release.is_set()
            finally:
                release.set()
    asyncio.run(run())
