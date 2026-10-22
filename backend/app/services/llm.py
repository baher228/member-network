import logging
import threading
from datetime import datetime, timezone
from openai import OpenAI, AuthenticationError, PermissionDeniedError, NotFoundError
from pydantic import BaseModel
from app.config import settings

log = logging.getLogger(__name__)
_call_lock = threading.Lock()
_last_call = None
_probe_started = False


class ProbeResult(BaseModel):
    ok: bool


class RunCircuitBreaker:
    def __init__(self):
        self.error = None

    def record_failure(self, exc):
        status = getattr(exc, 'status_code', None)
        if status not in (401, 402, 403, 404):
            status = next((code for error_type, code in (
                (AuthenticationError, 401), (PermissionDeniedError, 403), (NotFoundError, 404))
                if isinstance(exc, error_type)), None)
        if status is not None:
            detail = f'HTTP {status}{"; provider credits unavailable" if status == 402 else ""}'
            self.error = f'Skipped LLM call: provider rejected an earlier request in this run ({detail})'


def get_api_key():
    return settings.gemini_api_key if settings.llm_provider == 'gemini' else settings.xai_api_key


def health():
    provider = settings.llm_provider
    available = bool(get_api_key())
    with _call_lock:
        last_call = dict(_last_call) if _last_call is not None else None
    state = 'unavailable' if not available else ('not_checked' if last_call is None else ('working' if last_call['ok'] else 'unavailable'))
    reason = (f'{"GEMINI_API_KEY" if provider == "gemini" else "XAI_API_KEY"} is not configured'
              if not available else (last_call['error'] if last_call and not last_call['ok'] else None))
    return dict(provider=provider, model=settings.gemini_model if provider == 'gemini' else settings.grok_model,
                available=available, reason=reason, state=state, last_call=last_call)


def record_call(ok, http_status=None, error=None):
    global _last_call
    with _call_lock:
        _last_call = dict(ok=ok, at=datetime.now(timezone.utc).isoformat(), http_status=http_status, error=error)


def run_status(drafted, failed):
    if not get_api_key() or drafted == 0:
        return 'unavailable'
    return 'partial' if failed else 'available'


def create_client(api_key=None):
    return OpenAI(api_key=get_api_key() if api_key is None else api_key,
                  base_url='https://generativelanguage.googleapis.com/v1beta/openai/' if settings.llm_provider == 'gemini' else 'https://api.x.ai/v1',
                  timeout=15, max_retries=0)


def generate_json(messages, response_model, client=None, api_key=None):
    client = client or create_client(api_key)
    kwargs = dict(model=health()['model'], messages=messages)
    if settings.llm_provider == 'grok':
        kwargs['response_format'] = {'type': 'json_object'}
    response = None
    try:
        response = client.chat.completions.create(**kwargs)
        result = response_model.model_validate_json(response.choices[0].message.content)
    except Exception as exc:
        status = getattr(exc, 'status_code', None)
        record_call(False, status if isinstance(status, int) else (200 if response is not None else None), sanitized_error(exc))
        raise
    record_call(True, 200)
    return result


def probe_once():
    global _probe_started
    with _call_lock:
        if _probe_started or _last_call is not None or not get_api_key():
            return
        _probe_started = True
    try:
        generate_json([{'role': 'user', 'content': 'Reply only with the JSON object {"ok":true}.'}], ProbeResult)
    except Exception:
        pass


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
