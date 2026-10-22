import random
import threading
from statistics import mean, pstdev
from collections import defaultdict
from datetime import datetime, timezone
from app.services.recommender import recommend, embedder
from app.seed import synthetic_data
from app.db import snapshot

HOLDOUT_SEEDS = range(5)
_last_result = None
_cache_lock = threading.Lock()


def split_data(members, interactions, seed):
    rng = random.Random(seed)
    positives = defaultdict(list)
    eligible = {m['id'] for m in members if m['is_seed'] and m['consent_intros']}
    for i, row in enumerate(interactions):
        if row.get('is_seed') and row['kind'] == 'like' and row['member_id'] in eligible and row['target_id'] in eligible:
            positives[row['member_id']].append((i, row['target_id']))
    held_indices, held = set(), {}
    for member_id, likes in sorted(positives.items()):
        if len(likes) >= 5:
            chosen = rng.sample(likes, max(1, int(len(likes)*0.2)))
            held[member_id] = {target for _, target in chosen}
            held_indices.update(i for i, _ in chosen)
    train = [r for i, r in enumerate(interactions) if i not in held_indices]
    return train, held


def cold_start_train(train, users, seed):
    rng = random.Random(seed)
    by_user = defaultdict(list)
    for index, row in enumerate(train):
        if row['member_id'] in users and row['kind'] == 'like':
            by_user[row['member_id']].append(index)
    dropped = set()
    for user, indices in sorted(by_user.items()):
        retained = set(rng.sample(indices, min(2, len(indices))))
        dropped.update(set(indices) - retained)
    return [row for index, row in enumerate(train) if index not in dropped]


def evaluate(members, interactions, encoder=None):
    measurements = defaultdict(list)
    n_users = n_holdout = 0
    for seed in HOLDOUT_SEEDS:
        train, held = split_data(members, interactions, seed)
        n_users = len(held)
        n_holdout = sum(len(truth) for truth in held.values())
        for slice_name, training in [('all', train), ('cold-start', cold_start_train(train, held, seed))]:
            for mode in ('popularity', 'cf', 'content', 'hybrid'):
                hits, precision = [], []
                for member_id, truth in held.items():
                    predicted = {r['member']['id'] for r in recommend(member_id, members, training, k=5, encoder=encoder or embedder, mode=mode)['items']}
                    count = len(predicted & truth)
                    hits.append(int(count > 0))
                    precision.append(count/5)
                measurements[(mode, slice_name)].append((mean(hits) if hits else 0.0, mean(precision) if precision else 0.0))
    results = []
    for (mode, slice_name), values in measurements.items():
        hits, precision = zip(*values)
        results.append(dict(model=mode if slice_name == 'all' else f'{mode} · cold-start', slice=slice_name,
                            hit_rate=mean(hits), precision=mean(precision), hit_rate_std=pstdev(hits), precision_std=pstdev(precision)))
    best = max((r for r in results if r['slice'] == 'all'), key=lambda r: r['hit_rate'])
    notes = [f'Highest hit-rate: {best["model"]} (ties resolved by display order).',
             f'Embedder: {(encoder or embedder).name}. Holdout seeds 0..4; no tuning. Standard deviations are population std across five split-level metrics, not confidence intervals.',
             'Only consenting seed users with at least five eligible seed likes are evaluated.',
             'Both slices use the same evaluated users and held-out targets per split; n_holdout is the count per split, not summed across seeds.',
             'Cold-start caps training likes at two for every evaluated user simultaneously; other users and non-like interactions stay unchanged. Dropped training likes are not test labels.',
             'CF and content use per-user candidate min-max scaling to [0,1]; constant components become zero.',
             'CF weight = max_cf * n/(n+k0) (defaults: max_cf=0.7, k0=8); content gets the remainder.',
             'Synthetic likes combine affinity, tagged complementarity, popularity and noise; text similarity cannot reproduce all four.']
    metrics = {row['model']: row for row in results}
    if metrics['hybrid']['hit_rate'] < metrics['cf']['hit_rate']:
        notes.append('Hybrid trails CF on the five-split mean: adding content reorders the CF ranking, and semantic similarity is not the generator\'s exact tag matching. This aggregate does not isolate the cause of the gap; weights were not tuned to win.')
    return dict(computed_at=datetime.now(timezone.utc), holdout_fraction=0.2, k=5, n_test_users=n_users, n_holdout=n_holdout, results=results,
                notes=notes)


def get_evaluation(refresh=False):
    global _last_result
    with _cache_lock:
        if refresh or _last_result is None:
            _last_result = evaluate(*snapshot())
        return _last_result


def main():
    result = evaluate(*synthetic_data())
    print(f'Users: {result["n_test_users"]}; holdout: {result["n_holdout"]}; k=5')
    print('model                       hit_rate@5 ± std   precision@5 ± std')
    for row in result['results']:
        print(f'{row["model"]:<27} {row["hit_rate"]:.4f} ± {row["hit_rate_std"]:.4f}    {row["precision"]:.4f} ± {row["precision_std"]:.4f}')
    print('\n'.join(result['notes']))


if __name__ == '__main__':
    main()
