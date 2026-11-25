import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app import cognee_client as cognee
from app import cognee_sync
from app.main import app


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    for name, value in dict(cognee_enabled=True, cognee_api_url='https://cognee.test',
            cognee_api_key='private-key', cognee_tenant_id='private-tenant', cognee_user_id='private-user').items():
        monkeypatch.setattr(cognee.settings, name, value)


def member(i, **extra):
    return dict(id=i, name=f'Fake {i}', builds='Voice AI', wants='Partners', speaker_topics='Speech',
        github='https://github.com/fake', opted_in=True, consent_intros=True, consent_speaker=False, **extra)


def client(handler):
    return cognee.CogneeClient(httpx.Client(transport=httpx.MockTransport(handler)))


def test_add_cognify_search_shapes_and_verbatim():
    requests = []
    def handle(request):
        requests.append(request)
        assert request.headers['X-Api-Key'] == 'private-key'
        assert request.headers['X-Tenant-Id'] == 'private-tenant'
        if request.url.path.endswith('/add'):
            assert request.extensions['timeout']['read'] == 60
            assert b'name="datasetName"\r\n\r\nmember-network' in request.content
            assert b'filename="member-1.txt"' in request.content and b'Name: Fake 1' in request.content
            return httpx.Response(200, json={'status': 'added'})
        if request.url.path.endswith('/cognify'):
            assert json.loads(request.content) == {'datasets': ['member-network'], 'runInBackground': False}
            assert request.extensions['timeout']['read'] == 120
            return httpx.Response(200, json={'run': {'status': 'completed'}})
        assert json.loads(request.content) == {'searchType': 'GRAPH_COMPLETION', 'query': 'Who?', 'datasets': ['member-network']}
        assert request.extensions['timeout']['read'] == 60
        return httpx.Response(200, json=[{'search_result': ['  Exact answer.\nSecond line.  ']}])
    with client(handle) as api:
        api.add([(1, 'Name: Fake 1')])
        api.cognify()
        assert api.search('Who?') == '  Exact answer.\nSecond line.  '
    assert [r.url.path for r in requests] == ['/api/v1/add', '/api/v1/cognify', '/api/v1/search']


@pytest.mark.parametrize('failure', ['http', 'timeout', 'connection', 'json', 'empty', 'payload'])
def test_search_failures_are_explicit_and_sanitized(failure):
    def handle(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('private-key')
        if failure == 'connection':
            raise httpx.ConnectError('private-tenant')
        if failure == 'http':
            return httpx.Response(403, json={'detail': 'Denied private-key private-tenant private-user https://cognee.test'})
        if failure == 'json':
            return httpx.Response(200, text='not json')
        return httpx.Response(200, json=[] if failure == 'empty' else {'error': 'private-key'})
    with client(handle) as api, pytest.raises(cognee.CogneeError) as caught:
        api.search('Who?')
    assert str(caught.value)
    assert all(secret not in str(caught.value) for secret in ('private-key', 'private-tenant', 'private-user', 'https://cognee.test'))


def test_consent_filter_and_cached_evidence():
    members = [member(1), member(2), member(3), member(4)]
    members[1]['opted_in'] = False
    members[2].update(consent_intros=False, consent_speaker=False)
    members[3].update(consent_intros=False, consent_speaker=True)
    evidence = [dict(source='github', key='repos:fake', payload=[dict(name='speech-kit', description='Public ASR')])]
    docs, counts = cognee.member_documents(members, evidence)
    assert [i for i, _ in docs] == [1, 4]
    assert all('speech-kit: Public ASR' in text for _, text in docs)
    assert all('Fake 2' not in text and 'Fake 3' not in text for _, text in docs)
    assert counts == dict(excluded=2, not_opted_in_excluded=1, no_consent_excluded=1)


@pytest.mark.parametrize('fail_at', [None, 'add', 'cognify'])
def test_sync_counts_and_failures(monkeypatch, fail_at):
    members = [member(1), member(2)]
    members[1]['opted_in'] = False
    monkeypatch.setattr(cognee, 'rows', lambda sql: members if 'FROM members' in sql else [])
    paths = []
    def handle(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/' + str(fail_at)):
            return httpx.Response(500, json={'detail': 'provider failed'})
        return httpx.Response(200, json={})
    api = client(handle)
    monkeypatch.setattr(cognee, 'CogneeClient', lambda: api)
    result = TestClient(app).post('/api/cognee/sync').json()
    assert result['sent'] == (0 if fail_at == 'add' else 1)
    assert result['excluded'] == result['not_opted_in_excluded'] == 1
    assert result['status'] == ('failed' if fail_at else 'completed')
    assert len(paths) == (1 if fail_at == 'add' else 2)


def test_empty_sync_does_not_call_partner(monkeypatch):
    monkeypatch.setattr(cognee, 'rows', lambda sql: [])
    monkeypatch.setattr(cognee, 'CogneeClient', lambda: pytest.fail('No upload expected'))
    assert cognee.sync_network()['sent'] == 0


def test_disabled_and_unconfigured_endpoints(monkeypatch):
    api = TestClient(app)
    monkeypatch.setattr(cognee.settings, 'cognee_enabled', False)
    assert cognee.health() == dict(enabled=False, configured=True)
    for path in ('sync', 'search'):
        assert api.post('/api/cognee/' + path, json={'query': 'Who?'}).status_code == 503
    monkeypatch.setattr(cognee.settings, 'cognee_enabled', True)
    monkeypatch.setattr(cognee.settings, 'cognee_api_key', '')
    assert cognee.health() == dict(enabled=True, configured=False)
    assert api.post('/api/cognee/search', json={'query': 'Who?'}).status_code == 503


def test_search_endpoint_failure_and_validation(monkeypatch):
    api = client(lambda request: httpx.Response(402, json={'detail': 'credits depleted'}))
    monkeypatch.setattr(cognee, 'CogneeClient', lambda: api)
    response = TestClient(app).post('/api/cognee/search', json={'query': 'Who?'})
    assert response.json() == dict(source='cognee', status='failed', answer=None,
        error='Cognee HTTP 402: {"detail":"credits depleted"}')
    for query in ('', '   '):
        assert TestClient(app).post('/api/cognee/search', json={'query': query}).status_code == 422


def test_cognify_reports_pipeline_failure():
    with client(lambda request: httpx.Response(200, json={'run': {'status': 'failed'}})) as api:
        with pytest.raises(cognee.CogneeError, match='failed'):
            api.cognify()


def test_sync_cli_exit_status(monkeypatch, capsys):
    monkeypatch.setattr(cognee_sync, 'sync_network', lambda: {'status': 'failed', 'error': 'error'})
    assert cognee_sync.main() == 1
    assert json.loads(capsys.readouterr().out)['error'] == 'error'
