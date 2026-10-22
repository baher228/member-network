import json
import logging
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.config import settings
from app.db import rows

logging.getLogger('httpx').setLevel(logging.WARNING)
DATASET = 'member-network'
router = APIRouter(prefix='/api/cognee', tags=['cognee'])


class CogneeError(Exception):
    pass


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)


def health():
    return dict(enabled=settings.cognee_enabled, configured=bool(
        settings.cognee_api_url and settings.cognee_api_key and settings.cognee_tenant_id))


def require_enabled():
    state = health()
    if not state['enabled']:
        raise HTTPException(503, 'Cognee is disabled')
    if not state['configured']:
        raise HTTPException(503, 'Cognee is not configured')


def safe_error(value):
    value = str(value)
    for secret in (settings.cognee_api_key, settings.cognee_tenant_id,
                   settings.cognee_user_id, settings.cognee_api_url):
        if secret:
            value = value.replace(secret, '[redacted]')
    return value[:2000]


class CogneeClient:
    def __init__(self, client=None):
        self.client = client or httpx.Client()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def request(self, path, timeout, **kwargs):
        try:
            response = self.client.post(settings.cognee_api_url.rstrip('/') + path,
                headers={'X-Api-Key': settings.cognee_api_key, 'X-Tenant-Id': settings.cognee_tenant_id},
                timeout=timeout, **kwargs)
            if response.is_error:
                raise CogneeError(safe_error(f'Cognee HTTP {response.status_code}: {response.text}'))
            payload = response.json()
            if isinstance(payload, dict) and payload.get('error'):
                raise CogneeError(safe_error(json.dumps(payload)))
            return payload
        except httpx.TimeoutException:
            raise CogneeError('Cognee request timed out') from None
        except httpx.RequestError:
            raise CogneeError('Cognee connection failed') from None
        except ValueError:
            raise CogneeError('Cognee returned invalid JSON') from None

    def add(self, documents):
        return self.request('/api/v1/add', 60, data={'datasetName': DATASET},
            files=[('data', (f'member-{member_id}.txt', text.encode('utf-8'), 'text/plain'))
                   for member_id, text in documents])

    def cognify(self):
        result = self.request('/api/v1/cognify', 120,
            json={'datasets': [DATASET], 'runInBackground': False})
        if isinstance(result, dict):
            for run in result.values():
                if isinstance(run, dict) and str(run.get('status', '')).lower() in ('failed', 'error', 'pipeline_run_errored'):
                    raise CogneeError(safe_error(json.dumps(run)))
        return result

    def search(self, query):
        result = self.request('/api/v1/search', 60,
            json={'searchType': 'GRAPH_COMPLETION', 'query': query, 'datasets': [DATASET]})
        while True:
            if isinstance(result, list) and len(result) == 1:
                result = result[0]
            elif isinstance(result, dict) and 'search_result' in result:
                result = result['search_result']
            else:
                break
        if result is None or result == [] or result == '' or result == {}:
            raise CogneeError('Cognee returned no answer')
        return result


def member_documents(members, evidence=()):
    cached = {row['key']: row['payload'] for row in evidence if row['source'] == 'github'}
    documents = []
    not_opted_in = no_consent = 0
    for member in members:
        if not member.get('opted_in', False):
            not_opted_in += 1
            continue
        if not (member['consent_intros'] or member['consent_speaker']):
            no_consent += 1
            continue
        lines = [f"Name: {member['name']}", f"Builds: {member['builds']}",
                 f"Wants: {member['wants']}", f"Speaker topics: {member['speaker_topics']}",
                 f"Speaker consent: {member['consent_speaker']}", f"Intro consent: {member['consent_intros']}"]
        handle = (member.get('github') or '').strip().rstrip('/').split('/')[-1]
        repos = cached.get('repos:' + handle, [])
        if isinstance(repos, list):
            summary = '; '.join(f"{repo.get('name', '')}: {repo.get('description') or ''}" for repo in repos[:3] if isinstance(repo, dict))
            if summary:
                lines.append('Cached public GitHub evidence: ' + summary[:1200])
        documents.append((member['id'], '\n'.join(lines)))
    return documents, dict(excluded=not_opted_in + no_consent,
        not_opted_in_excluded=not_opted_in, no_consent_excluded=no_consent)


def sync_network():
    require_enabled()
    members = rows('SELECT id,name,builds,wants,speaker_topics,github,opted_in,consent_intros,consent_speaker FROM members ORDER BY id')
    evidence = rows("SELECT source,key,payload FROM evidence_cache WHERE source='github' AND key LIKE 'repos:%'")
    documents, counts = member_documents(members, evidence)
    result = dict(source='cognee', dataset=DATASET, sent=0, **counts, status='completed', error=None)
    if not documents:
        return result
    try:
        with CogneeClient() as client:
            client.add(documents)
            result['sent'] = len(documents)
            client.cognify()
    except CogneeError as exc:
        result.update(status='failed', error=str(exc))
    return result


@router.post('/sync')
def sync():
    return sync_network()


@router.post('/search')
def search(body: SearchInput):
    require_enabled()
    if not body.query.strip():
        raise HTTPException(422, 'Query must not be blank')
    try:
        with CogneeClient() as client:
            answer = client.search(body.query)
        return dict(source='cognee', status='completed', answer=answer, error=None)
    except CogneeError as exc:
        return dict(source='cognee', status='failed', answer=None, error=str(exc))
