from types import SimpleNamespace
from unittest.mock import MagicMock
import httpx
from openai import APIStatusError
import pytest
from pydantic import ValidationError
from app.config import Settings
from app.models import LLMHealth
from app.services import llm, intros, threads


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
    call = client.chat.completions.create.call_args.kwargs
    assert call['model'] == model
    assert ('response_format' in call) is (provider == 'grok')
    assert 'JSON' in call['messages'][0]['content']
    assert llm.health() == dict(provider=provider, model=model, available=True, reason=None)
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


def test_credit_errors_sanitized_for_intros_and_nudges(monkeypatch):
    monkeypatch.setattr(llm.settings, 'llm_provider', 'gemini')
    error = APIStatusError('prepayment credits depleted; private diagnostic', response=httpx.Response(402, request=httpx.Request('POST', 'https://example.com')), body={'error': 'private diagnostic'})
    client = MagicMock()
    client.chat.completions.create.side_effect = error
    result = intros.draft_intro({'reasons': []}, api_key='test-only', client=client)
    expected = 'LLM call or structured response failed: APIStatusError (HTTP 402; provider credits unavailable)'
    assert result['status'] == 'failed' and result['error'] == expected
    sample = threads.sample_chat()
    result = threads.analyze_chat(sample['log_text'], now=sample['suggested_now'], api_key='test-only', client=client)
    assert all(t.status == 'failed' and t.error == expected for t in result.threads if t.worth_reviving)
    assert 'private diagnostic' not in result.model_dump_json()
