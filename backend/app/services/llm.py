import logging
from openai import OpenAI
from app.config import settings

log = logging.getLogger(__name__)


def get_api_key():
    return settings.gemini_api_key if settings.llm_provider == 'gemini' else settings.xai_api_key


def health():
    provider = settings.llm_provider
    available = bool(get_api_key())
    return dict(provider=provider, model=settings.gemini_model if provider == 'gemini' else settings.grok_model,
                available=available, reason=None if available else f'{"GEMINI_API_KEY" if provider == "gemini" else "XAI_API_KEY"} is not configured')


def create_client(api_key=None):
    return OpenAI(api_key=get_api_key() if api_key is None else api_key,
                  base_url='https://generativelanguage.googleapis.com/v1beta/openai/' if settings.llm_provider == 'gemini' else 'https://api.x.ai/v1',
                  timeout=20, max_retries=0)


def generate_json(messages, response_model, client=None, api_key=None):
    client = client or create_client(api_key)
    kwargs = dict(model=health()['model'], messages=messages)
    if settings.llm_provider == 'grok':
        kwargs['response_format'] = {'type': 'json_object'}
    response = client.chat.completions.create(**kwargs)
    return response_model.model_validate_json(response.choices[0].message.content)


def sanitized_error(exc):
    status = getattr(exc, 'status_code', None)
    detail = f' (HTTP {status}{"; provider credits unavailable" if status == 402 else ""})' if isinstance(status, int) else ''
    return f'LLM call or structured response failed: {type(exc).__name__}{detail}'


def check_llm():
    if settings.llm_provider != 'grok' or not get_api_key():
        return
    try:
        models = [model.id for model in create_client().models.list().data]
        log.info('xAI available models: %s', models)
    except Exception as exc:
        log.warning('xAI model discovery failed: %s', type(exc).__name__)
