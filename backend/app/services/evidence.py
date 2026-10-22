import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import httpx
from app.config import settings
from app.db import rows, execute


def handle(value):
    value = (value or '').strip().rstrip('/').split('/')[-1]
    return value if re.fullmatch(r'[\w.-]{1,100}', value) else None


async def cached_fetch(client, source, key, url, params=None, headers=None):
    cached = None
    try:
        values = await asyncio.to_thread(rows, 'SELECT payload,fetched_at FROM evidence_cache WHERE source=:source AND key=:key', {'source': source, 'key': key})
        cached = values[0] if values else None
    except Exception:
        pass
    if cached and cached['fetched_at'] > datetime.now(timezone.utc)-timedelta(hours=6):
        return cached['payload'], False, cached['fetched_at']
    response = await client.get(url, params=params, headers=headers)
    response.raise_for_status()
    payload = response.json()
    fetched_at = datetime.now(timezone.utc)
    try:
        await asyncio.to_thread(execute, '''INSERT INTO evidence_cache(source,key,payload,fetched_at)
               VALUES (:source,:key,CAST(:payload AS jsonb),:at) ON CONFLICT(source,key)
               DO UPDATE SET payload=EXCLUDED.payload,fetched_at=EXCLUDED.fetched_at''',
               {'source': source, 'key': key, 'payload': json.dumps(payload), 'at': fetched_at})
    except Exception:
        pass
    return payload, True, fetched_at


def evidence(source, title, url, detail, live, at):
    return dict(source=source, title=str(title), url=url, detail=str(detail)[:1200] if detail else None, live=live, fetched_at=at)


async def github_member(client, username):
    headers = {'Accept': 'application/vnd.github+json'}
    if settings.github_token:
        headers['Authorization'] = f'Bearer {settings.github_token}'
    data, live, at = await cached_fetch(client, 'github', f'repos:{username}', f'https://api.github.com/users/{quote(username)}/repos', {'sort': 'updated', 'per_page': 30}, headers)
    if not isinstance(data, list):
        raise ValueError('Unexpected GitHub repository response')
    top = sorted(data, key=lambda r: r.get('stargazers_count', 0), reverse=True)[:3]
    return [evidence('github', r['name'], r['html_url'], f'{r.get("description") or ""} | {r.get("stargazers_count",0)} stars | {r.get("language") or "unknown language"}', live, at) for r in top], live


async def external_github(client, topic):
    headers = {'Accept': 'application/vnd.github+json'}
    if settings.github_token:
        headers['Authorization'] = f'Bearer {settings.github_token}'
    data, live, at = await cached_fetch(client, 'github', f'search:{topic}', 'https://api.github.com/search/users', {'q': f'location:London {topic}', 'per_page': 5}, headers)
    users = data.get('items', [])[:5]
    repos = await asyncio.gather(*(github_member(client, u['login']) for u in users), return_exceptions=True)
    candidates = []
    for user, result in zip(users, repos):
        items = [evidence('github', user['login'], user['html_url'], f'GitHub user search matched location:London {topic}', live, at)]
        if not isinstance(result, Exception):
            items.extend(result[0])
            live = live or result[1]
        candidates.append(dict(kind='external', member_id=None, name=user['login'], handle=user['login'], evidence=items))
    return candidates, live


async def devpost(client, query, external=False):
    data, live, at = await cached_fetch(client, 'devpost', f'search:{query}', 'https://devpost.com/software/search', {'query': query}, {'Accept': 'application/json'})
    projects = data.get('software', data.get('results', [])) if isinstance(data, dict) else data
    if not isinstance(projects, list):
        raise ValueError('Unexpected Devpost search response')
    items = []
    for p in projects[:5]:
        if not isinstance(p, dict):
            continue
        items.append(evidence('devpost', p.get('name') or p.get('title') or query, p.get('url'), p.get('tagline') or p.get('description'), live, at))
    return items, live


async def external_devpost(client, topic):
    query = f'{topic} London'
    data, live, at = await cached_fetch(client, 'devpost', f'search:{query}', 'https://devpost.com/software/search', {'query': query}, {'Accept': 'application/json'})
    projects = data.get('software', data.get('results', [])) if isinstance(data, dict) else data
    if not isinstance(projects, list):
        raise ValueError('Unexpected Devpost search response')
    candidates = []
    for project in projects[:5]:
        if not isinstance(project, dict):
            continue
        people = project.get('team_members') or project.get('members') or []
        if not isinstance(people, list):
            continue
        for person in people[:5]:
            if not isinstance(person, dict) or not person.get('name'):
                continue
            candidates.append(dict(kind='external', member_id=None, name=person['name'], handle=person.get('username'),
                                   evidence=[evidence('devpost', project.get('name') or project.get('title') or query, project.get('url'), project.get('tagline') or project.get('description'), live, at)]))
    return candidates, live


async def external_hn(client, topic):
    data, live, at = await cached_fetch(client, 'hn', f'search:{topic}', 'https://hn.algolia.com/api/v1/search', {'query': f'{topic} London', 'tags': 'story', 'hitsPerPage': 5})
    candidates = []
    for story in data.get('hits', []):
        author = story.get('author')
        if not author:
            continue
        candidates.append(dict(kind='external', member_id=None, name=author, handle=author,
                               evidence=[evidence('hn', story.get('title') or 'HN story', f'https://news.ycombinator.com/item?id={story["objectID"]}', 'Story matched topic and London search; author location is not independently verified.', live, at)]))
    return candidates, live


async def external_luma(client, topic):
    candidates, lives = [], []
    for event_id in filter(None, (s.strip() for s in settings.luma_event_ids.split(','))):
        data, live, at = await cached_fetch(client, 'luma', event_id, 'https://api.lu.ma/event/get', {'event_api_id': event_id})
        lives.append(live)
        event = data.get('event', {})
        title, description = event.get('name', ''), event.get('description', '')
        if not set(re.findall(r'\w+', topic.lower())) & set(re.findall(r'\w+', (title+' '+description).lower())):
            continue
        for host in data.get('hosts', []):
            candidates.append(dict(kind='external', member_id=None, name=host.get('name') or 'Event host', handle=host.get('username'),
                                   evidence=[evidence('luma', title, event.get('url') or f'https://lu.ma/{event_id}', description, live, at)]))
    return candidates, any(lives)
