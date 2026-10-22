import random
from sqlalchemy import text
from app.db import engine

CLUSTERS = [
    ('voice speech AI', 'voice agents and speech recognition', 'devtools tracing and low latency infrastructure'),
    ('devtools infra', 'developer tooling observability and infrastructure', 'design community onboarding and user research'),
    ('fintech payments', 'fintech payments and financial inclusion', 'voice agents and speech accessibility'),
    ('climate energy', 'climate carbon accounting and clean energy', 'fintech payments and funding'),
    ('health accessibility', 'health diagnostics and accessible care', 'climate data and energy efficiency'),
    ('design community', 'design systems and community onboarding', 'health accessibility and inclusive design'),
]


def synthetic_data():
    rng = random.Random(42)
    members = []
    for i in range(80):
        topic, build, want = CLUSTERS[i % 6]
        members.append(dict(id=i+1, name=f'Synthetic {topic.split()[0].title()} Builder {i+1:02}',
                            handle=f'fake_builder_{i+1}', github=None, devpost=None,
                            builds=f'I build {build}, focused on {rng.choice(["open source", "early stage teams", "London communities"])}.',
                            wants=f'I want help with {want}.', speaker_topics=f'{topic}; lessons from building {build}',
                            consent_intros=i % 10 != 9, consent_speaker=i % 2 == 0, is_seed=True))
    interactions = []
    for m in members[:74]:
        candidates = [t for t in members[:77] if t['id'] != m['id']]
        weights = [(7 if t['id'] % 6 == m['id'] % 6 else 0.5) * (3 if t['id'] < 13 else 1) for t in candidates]
        selected = []
        for _ in range(rng.randint(7, 14)):
            t = rng.choices(candidates, weights=weights)[0]
            idx = candidates.index(t)
            selected.append(t)
            candidates.pop(idx)
            weights.pop(idx)
        for t in selected:
            interactions.append(dict(member_id=m['id'], target_id=t['id'], kind='like', is_seed=True))
    return members, interactions


def main():
    members, interactions = synthetic_data()
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM interactions WHERE is_seed=true'))
        ids = {}
        for m in members:
            old_id = m.pop('id')
            existing = conn.execute(text('SELECT id FROM members WHERE is_seed=true AND handle=:handle ORDER BY id LIMIT 1'), {'handle': m['handle']}).scalar_one_or_none()
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
