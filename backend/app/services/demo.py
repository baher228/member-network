from sqlalchemy import text
from app import eval as evaluation
from app.db import engine
from app.seed import synthetic_data
from app.services.recommender import embedder


def restore_members(conn, profiles):
    existing = list(conn.execute(text('SELECT id,handle FROM members WHERE is_seed=true ORDER BY id')).mappings())
    ids, used = {}, set()
    for profile in profiles:
        match = next((member for member in existing if member['id'] not in used and member['handle'] in
                      (profile['handle'], f'fake_builder_{profile["id"]}')), None)
        if match:
            ids[profile['id']] = match['id']
            used.add(match['id'])
    remaining = iter(member for member in existing if member['id'] not in used)
    for profile in profiles:
        if profile['id'] not in ids:
            match = next(remaining, None)
            if match:
                ids[profile['id']] = match['id']
    created = 0
    for profile in profiles:
        fields = {key: value for key, value in profile.items() if key != 'id'}
        if profile['id'] in ids:
            assignments = ','.join(f'{key}=:{key}' for key in fields)
            conn.execute(text(f'UPDATE members SET {assignments} WHERE id=:id AND is_seed=true'), dict(fields, id=ids[profile['id']]))
        else:
            columns = ','.join(fields)
            values = ','.join(f':{key}' for key in fields)
            ids[profile['id']] = conn.execute(text(f'INSERT INTO members ({columns}) VALUES ({values}) RETURNING id'), fields).scalar_one()
            created += 1
    return ids, created


def reset_demo():
    profiles, interactions = synthetic_data()
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(7349852)'))
        conn.execute(text('LOCK TABLE intros, intro_runs, interactions, members IN SHARE ROW EXCLUSIVE MODE'))
        ids, members_created = restore_members(conn, profiles)
        intros_deleted = conn.execute(text('''DELETE FROM intros i USING members a,members b
            WHERE i.member_id=a.id AND i.target_id=b.id AND a.is_seed=true AND b.is_seed=true''')).rowcount
        runs_deleted = conn.execute(text('''DELETE FROM intro_runs r
            WHERE NOT EXISTS (SELECT 1 FROM intros i WHERE i.run_id=r.id)''')).rowcount
        expected = {(ids[row['member_id']], ids[row['target_id']], row['kind']) for row in interactions}
        existing = conn.execute(text('''SELECT i.* FROM interactions i JOIN members a ON a.id=i.member_id
            JOIN members b ON b.id=i.target_id WHERE a.is_seed=true AND b.is_seed=true ORDER BY i.id''')).mappings()
        kept, delete_ids = set(), []
        for row in existing:
            key = (row['member_id'], row['target_id'], row['kind'])
            if row['is_seed'] and key in expected and key not in kept:
                kept.add(key)
            else:
                delete_ids.append(row['id'])
        if delete_ids:
            conn.execute(text('DELETE FROM interactions WHERE id=ANY(:ids)'), {'ids': delete_ids})
        missing = sorted(expected - kept)
        if missing:
            conn.execute(text('''INSERT INTO interactions(member_id,target_id,kind,is_seed)
                VALUES (:member_id,:target_id,:kind,true)'''),
                [dict(member_id=member_id, target_id=target_id, kind=kind) for member_id, target_id, kind in missing])
        result = dict(seed_members_restored=len(profiles), seed_members_created=members_created,
                      seed_interactions_restored=len(expected), interactions_deleted=len(delete_ids),
                      interactions_created=len(missing), intros_deleted=intros_deleted, intro_runs_deleted=runs_deleted)
    evaluation.invalidate_cache()
    embedder.clear_cache()
    return result
