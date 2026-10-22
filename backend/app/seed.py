"""Fictional demo world, generated with RNG seed 42 (not fitted to eval).

Each member builds one tagged phrase and wants a tagged capability from another
cluster. Tags are seed-only metadata: neither embeddings nor recommender scores
participate in generating likes. For each directed pair among active members:

    P(like) = sigmoid(-3.1 + 1.2 * same_cluster
                     + 1.1 * wanted_cluster + 1.6 * exact_wanted_tag
                     + 0.9 * popularity + Uniform(-0.5, 0.5))

Popularity is a fixed shuffled rank, 1/sqrt(rank), independent of cluster/needs.
Independent Bernoulli draws produce variable activity, affinity-based co-likes,
cross-cluster complementarity and occasional surprising connections. Members
75-77 have no outgoing likes (cold starts); 78-80 are excluded from both sides
(isolated). Names/handles are invented demo identities, never public accounts.
"""

import math
import random
from sqlalchemy import text
from app.db import engine

CLUSTERS = [
    ('voice / speech AI', [
        'real-time speech-to-text for call centres', 'a Whisper fine-tune for Scottish accents',
        'on-device voice commands for noisy workshops', 'speaker diarisation for community radio',
        'multilingual voice agents for booking appointments', 'speech synthesis for low-bandwidth phones']),
    ('devtools / infrastructure', [
        'OpenTelemetry tracing for Python services', 'GPU inference cost dashboards',
        'reliable background job queues', 'preview deployments for small teams',
        'Postgres query profiling tools', 'offline-first sync for mobile apps']),
    ('fintech / payments', [
        'open banking cash-flow forecasts', 'low-fee payments for local markets',
        'fraud detection for small charities', 'grant budgeting tools for nonprofits',
        'accessible invoicing for freelancers', 'community lending risk models']),
    ('climate / energy', [
        'heat-pump demand forecasting', 'carbon accounting for small suppliers',
        'air-quality sensors for school streets', 'repair and reuse marketplace logistics',
        'solar output prediction from weather data', 'energy monitoring for rented flats']),
    ('health / accessibility', [
        'accessible medication reminders', 'privacy-preserving patient intake forms',
        'appointment triage for community clinics', 'screen-reader testing for health apps',
        'wearable fatigue tracking for shift workers', 'plain-language clinical information']),
    ('design / community', [
        'user research with multilingual communities', 'onboarding flows for volunteer groups',
        'accessible design systems for tiny teams', 'community event discovery maps',
        'peer mentoring circles for new builders', 'usability testing for older adults']),
]

FIRST_NAMES = ('Maya Theo Priya Arun Lena Jonah Amara Felix Noor Oscar Iris Ravi '
               'Zara Hugo Esme Idris Ada Milo Leila Finn Nia Owen Sana Kit Rosa '
               'Eli Anika Luca Talia Remy Imani Ellis Farah Nico Cleo Dev Asha '
               'Jules Mina Samir').split()
AUDIENCES = ['local cooperatives', 'weekend makers', 'neighbourhood charities',
             'two-person startups', 'volunteer organisers', 'public libraries',
             'independent studios', 'community workshops']


def like_probability(same_cluster, wanted_cluster, exact_tag, popularity, noise):
    logit = -3.1 + 1.2*same_cluster + 1.1*wanted_cluster + 1.6*exact_tag + 0.9*popularity + noise
    return 1 / (1 + math.exp(-logit))


def synthetic_data():
    rng = random.Random(42)
    members = []
    profiles = []
    popularity_ranks = list(range(1, 81))
    rng.shuffle(popularity_ranks)
    for i in range(80):
        cluster = i % len(CLUSTERS)
        topic, phrases = CLUSTERS[cluster]
        build_tag = (cluster, (i // len(CLUSTERS)) % len(phrases))
        want_cluster = rng.choice([c for c in range(len(CLUSTERS)) if c != cluster])
        want_tag = (want_cluster, rng.randrange(len(CLUSTERS[want_cluster][1])))
        build, want = phrases[build_tag[1]], CLUSTERS[want_cluster][1][want_tag[1]]
        first, initial = FIRST_NAMES[i % len(FIRST_NAMES)], ('R' if i < len(FIRST_NAMES) else 'K')
        audience = rng.choice(AUDIENCES)
        profiles.append(dict(cluster=cluster, build_tag=build_tag, want_tag=want_tag))
        members.append(dict(id=i+1, name=f'{first} {initial}.',
                            handle=f'@{first.lower()}_{initial.lower()}', github=None, devpost=None,
                            builds=f'I am building {build} for {audience}.',
                            wants=f'I need help with {want} to support {audience}.',
                            speaker_topics=f'{topic}: {build}; {rng.choice(["prototyping", "field testing", "lessons from pilots", "responsible deployment"])} with {audience}.',
                            consent_intros=i % 10 != 9, consent_speaker=i % 2 == 0, is_seed=True))
    interactions = []
    for u in range(74):
        for t in range(77):
            if u == t:
                continue
            liker, target = profiles[u], profiles[t]
            probability = like_probability(
                liker['cluster'] == target['cluster'], liker['want_tag'][0] == target['cluster'],
                liker['want_tag'] == target['build_tag'], 1/math.sqrt(popularity_ranks[t]), rng.uniform(-0.5, 0.5))
            if rng.random() < probability:
                interactions.append(dict(member_id=u+1, target_id=t+1, kind='like', is_seed=True))
    return members, interactions


def main():
    members, interactions = synthetic_data()
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM intros'))
        conn.execute(text('DELETE FROM intro_runs'))
        conn.execute(text('DELETE FROM interactions WHERE is_seed=true'))
        ids = {}
        for m in members:
            old_id = m.pop('id')
            existing = conn.execute(text('SELECT id FROM members WHERE is_seed=true AND handle IN (:handle,:legacy_handle) ORDER BY id LIMIT 1'), {'handle': m['handle'], 'legacy_handle': f'fake_builder_{old_id}'}).scalar_one_or_none()
            if existing is not None:
                assignments = ','.join(f'{key}=:{key}' for key in m)
                conn.execute(text(f'UPDATE members SET {assignments} WHERE id=:id'), dict(m, id=existing))
                ids[old_id] = existing
            else:
                cols = ','.join(m)
                ids[old_id] = conn.execute(text(f'INSERT INTO members ({cols}) VALUES ({",".join(":"+k for k in m)}) RETURNING id'), m).scalar_one()
        for interaction in interactions:
            interaction['member_id'] = ids[interaction['member_id']]
            interaction['target_id'] = ids[interaction['target_id']]
            conn.execute(text('INSERT INTO interactions(member_id,target_id,kind,is_seed) VALUES (:member_id,:target_id,:kind,true)'), interaction)
    print(f'Seeded {len(members)} clearly synthetic members and {len(interactions)} likes.')


if __name__ == '__main__':
    main()
