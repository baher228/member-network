import asyncio
import numpy as np
import httpx
from app.services.recommender import embedder
from app.services import evidence as ev
from app.config import settings


async def find_speakers(topic, members, include_external=True):
    consenting = [m for m in members if m['consent_speaker']]
    candidates = [dict(kind='member', member_id=m['id'], name=m['name'], handle=m['handle'],
                       evidence=[ev.evidence('questionnaire', m['speaker_topics'], None, m['builds'], False, m.get('created_at'))]) for m in consenting]
    statuses = {source: [] for source in ('github', 'devpost', 'hn', 'luma')}

    async def external(source, fn, client):
        try:
            items, live = await fn(client, topic)
            candidates.extend(items)
            statuses[source].append(dict(source=source, status='live' if live else 'cached', error=None))
        except Exception as exc:
            statuses[source].append(dict(source=source, status='failed', error=f'{type(exc).__name__}: source request failed'))

    async def member_evidence(source, fn, client, candidate, username):
        try:
            items, live = await fn(client, username)
            candidate['evidence'].extend(items)
            statuses[source].append(dict(source=source, status='live' if live else 'cached', error=None))
        except Exception as exc:
            statuses[source].append(dict(source=source, status='failed', error=f'{type(exc).__name__}: member evidence request failed'))

    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0), follow_redirects=True) as client:
        jobs = []
        for member, candidate in zip(consenting, candidates):
            for source, fn in [('github', ev.github_member), ('devpost', ev.devpost)]:
                username = ev.handle(member.get(source))
                if username:
                    jobs.append(member_evidence(source, fn, client, candidate, username))
        if include_external:
            for source, fn in [('github', ev.external_github), ('devpost', ev.external_devpost), ('hn', ev.external_hn), ('luma', ev.external_luma)]:
                if source != 'luma' or settings.luma_event_ids.strip():
                    jobs.append(external(source, fn, client))
        await asyncio.gather(*jobs)
    texts = [topic] + [' '.join((e['title']+' '+(e['detail'] or '')) for e in candidate['evidence']) for candidate in candidates]
    vectors = await asyncio.to_thread(embedder.encode, texts)
    for i, candidate in enumerate(candidates):
        candidate['score'] = float(max(0, np.dot(vectors[0], vectors[i+1])))
        candidate['match_reasons'] = [f'Topic similarity to supplied evidence: {candidate["score"]:.3f}', 'Questionnaire speaker consent granted.' if candidate['kind'] == 'member' else 'Public evidence match; location/availability require verification.']
    candidates.sort(key=lambda c: -c['score'])
    sources = []
    for source, states in statuses.items():
        if not states:
            sources.append(dict(source=source, status='skipped', error=None))
        else:
            # Preserve partial failure visibility instead of hiding it behind successes.
            status = next((s for s in states if s['status'] == 'failed'), None) or next((s for s in states if s['status'] == 'live'), states[0])
            sources.append(status)
    return dict(topic=topic, items=candidates[:30], sources=sources)
