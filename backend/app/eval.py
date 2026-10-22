import random
from collections import defaultdict
from datetime import datetime, timezone
from app.services.recommender import recommend, embedder
from app.seed import synthetic_data


def evaluate(members, interactions, encoder=None):
    rng = random.Random(2025)
    positives = defaultdict(list)
    eligible = {m['id'] for m in members if m['is_seed'] and m['consent_intros']}
    for i, row in enumerate(interactions):
        if row.get('is_seed') and row['kind'] == 'like' and row['member_id'] in eligible and row['target_id'] in eligible:
            positives[row['member_id']].append((i, row['target_id']))
    held_indices, held = set(), {}
    for member_id, likes in positives.items():
        if len(likes) >= 5:
            chosen = rng.sample(likes, max(1, int(len(likes)*0.2)))
            held[member_id] = {target for _, target in chosen}
            held_indices.update(i for i, _ in chosen)
    train = [r for i, r in enumerate(interactions) if i not in held_indices]
    results = []
    for mode in ('popularity', 'cf', 'content', 'hybrid'):
        hits, precision = [], []
        for member_id, truth in held.items():
            predicted = {r['member']['id'] for r in recommend(member_id, members, train, k=5, encoder=encoder or embedder, mode=mode)['items']}
            count = len(predicted & truth)
            hits.append(int(count > 0))
            precision.append(count/5)
        results.append(dict(model=mode, hit_rate=sum(hits)/len(hits) if hits else 0.0, precision=sum(precision)/len(precision) if precision else 0.0))
    best = max(results, key=lambda r: r['hit_rate'])
    notes = [f'Highest hit-rate: {best["model"]} (ties resolved by display order).',
             f'Embedder: {(encoder or embedder).name}. Fixed random holdout; no tuning.',
             'Only consenting seed users with at least five eligible seed likes are evaluated.',
             'CF and content use per-user candidate min-max scaling to [0,1]; constant components become zero.',
             'CF weight = max_cf * n/(n+k0) (defaults: max_cf=0.7, k0=8); content gets the remainder.',
             'Synthetic likes combine affinity, tagged complementarity, popularity and noise; text similarity cannot reproduce all four.']
    metrics = {row['model']: row for row in results}
    if metrics['hybrid']['hit_rate'] < metrics['cf']['hit_rate']:
        notes.append('Hybrid trails CF on this holdout: adding content reorders the CF ranking, and semantic similarity is not the generator\'s exact tag matching. This aggregate does not isolate the cause of the gap; weights were not tuned to win.')
    return dict(computed_at=datetime.now(timezone.utc), holdout_fraction=0.2, k=5, n_test_users=len(held), n_holdout=len(held_indices), results=results,
                notes=notes)


def main():
    result = evaluate(*synthetic_data())
    print(f'Users: {result["n_test_users"]}; holdout: {result["n_holdout"]}; k=5')
    print('model        hit_rate@5  precision@5')
    for row in result['results']:
        print(f'{row["model"]:<12} {row["hit_rate"]:.4f}      {row["precision"]:.4f}')
    print('\n'.join(result['notes']))


if __name__ == '__main__':
    main()
