import pytest
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
