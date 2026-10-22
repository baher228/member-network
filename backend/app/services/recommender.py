import hashlib
import logging
import threading
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from app.config import settings

log = logging.getLogger(__name__)


class Embedder:
    def __init__(self, mode=None):
        self.mode = mode or settings.embedder
        self.name = 'tf-idf'
        self.model = None
        self.attempted = False
        self.cache = {}
        self.lock = threading.Lock()

    def encode(self, texts, keys=None):
        with self.lock:
            return self._encode(texts, keys)

    def _encode(self, texts, keys=None):
        if not self.attempted and self.mode != 'tf-idf':
            self.attempted = True
            try:
                import torch
                from sentence_transformers import SentenceTransformer
                torch.set_num_threads(min(4, torch.get_num_threads()))
                self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu')
                self.name = 'sentence-transformers/all-MiniLM-L6-v2'
            except Exception as exc:
                log.warning('Embedding model unavailable; using TF-IDF: %s', exc)
        if self.model is not None:
            cache_keys = [(keys[i] if keys else '', hashlib.sha256(t.encode()).hexdigest()) for i, t in enumerate(texts)]
            missing = [i for i, key in enumerate(cache_keys) if key not in self.cache]
            if missing:
                vectors = self.model.encode([texts[i] for i in missing], normalize_embeddings=True)
                for i, vector in zip(missing, vectors):
                    self.cache[cache_keys[i]] = vector
            return np.array([self.cache[k] for k in cache_keys])
        try:
            return TfidfVectorizer(ngram_range=(1, 2)).fit_transform(texts).toarray()
        except ValueError:
            return np.zeros((len(texts), 1))


embedder = Embedder()


def normalize(values):
    values = np.maximum(0, np.asarray(values, dtype=float))
    low, high = values.min(initial=0), values.max(initial=0)
    return (values-low)/(high-low) if high > low else values * 0


def hybrid_weight(n, max_cf=None, k0=None):
    return (settings.max_cf_weight if max_cf is None else max_cf) * n / (n + (settings.cf_k0 if k0 is None else k0))


def cf_matrix(members, interactions):
    ids = {m['id']: i for i, m in enumerate(members)}
    matrix = np.zeros((len(members), len(members)))
    for row in interactions:
        if row['kind'] in ('like', 'accept') and row['member_id'] in ids and row['target_id'] in ids:
            matrix[ids[row['member_id']], ids[row['target_id']]] += 2 if row['kind'] == 'accept' else 1
    norms = np.linalg.norm(matrix, axis=0)
    denominator = np.outer(norms, norms)
    similarity = np.divide(matrix.T @ matrix, denominator, out=np.zeros_like(matrix), where=denominator != 0)
    np.fill_diagonal(similarity, 0)
    return matrix, similarity, ids


def recommend(member_id, members, interactions, existing_intros=(), k=10, encoder=None, mode='hybrid'):
    encoder = encoder or embedder
    by_id = {m['id']: m for m in members}
    if member_id not in by_id:
        raise KeyError(member_id)
    user = by_id[member_id]
    matrix, sims, ids = cf_matrix(members, interactions)
    u = ids[member_id]
    history = [r for r in interactions if r['member_id'] == member_id]
    excluded = {member_id} | {r['target_id'] for r in history}
    for intro in existing_intros:
        if intro['member_id'] == member_id:
            excluded.add(intro['target_id'])
        if intro['target_id'] == member_id:
            excluded.add(intro['member_id'])
    candidates = [m for m in members if m['id'] not in excluded and m['consent_intros']]
    weight = hybrid_weight(len(history))
    info = dict(n_interactions=len(interactions), member_interactions=len(history), cf_weight=weight, content_weight=1-weight, embedder=encoder.name)
    if not candidates or not user['consent_intros']:
        return dict(member_id=member_id, model=info, items=[])
    liked = np.flatnonzero(matrix[u] > 0)
    raw_cf = matrix[u] @ sims
    texts = [user['wants'], user['speaker_topics']] + [m['builds'] for m in candidates] + [m['speaker_topics'] for m in candidates]
    keys = [member_id, member_id] + [m['id'] for m in candidates] * 2
    vectors = encoder.encode(texts, keys)
    # TF-IDF and transformer rows are L2-normalized.
    raw_content = np.maximum(0, vectors[2:2+len(candidates)] @ vectors[0]) * 0.85 + np.maximum(0, vectors[2+len(candidates):] @ vectors[1]) * 0.15
    cf = normalize([raw_cf[ids[m['id']]] for m in candidates])
    content = normalize(raw_content)
    popularity = normalize([matrix[:, ids[m['id']]].sum() for m in candidates])
    scores = {'cf': cf, 'content': content, 'popularity': popularity, 'hybrid': weight*cf+(1-weight)*content}[mode]
    items = []
    for i, target in enumerate(candidates):
        t = ids[target['id']]
        reasons = []
        contributing = sorted([j for j in liked if sims[j, t] > 0], key=lambda j: sims[j, t], reverse=True)[:2]
        if contributing:
            co_likers = int(np.count_nonzero((matrix[:, t] > 0) & np.any(matrix[:, contributing] > 0, axis=1)))
            names = [{'id': members[j]['id'], 'name': members[j]['name']} for j in contributing]
            reasons.append(dict(kind='cf', text=f'You liked {" and ".join(n["name"] for n in names)}; {co_likers} people who liked them also liked/connected with {target["name"]}.', weight=weight, evidence=dict(liked=names, co_likers=co_likers)))
        if raw_content[i] > 0.01:
            want, build = user['wants'][:200], target['builds'][:200]
            reasons.append(dict(kind='content', text=f'{target["name"]} builds: "{build}"; you want: "{want}".', weight=1-weight, evidence=dict(your_want=want, their_build=build, similarity=float(raw_content[i]))))
        if raw_cf[t] < 0.01 and raw_content[i] < 0.05:
            if mode == 'hybrid':
                scores[i] = 0.05 * popularity[i]
            reasons.append(dict(kind='popularity', text=f'{target["name"]} has {int(np.count_nonzero(matrix[:, t]))} positive community connections; limited personal signal.', weight=0.05, evidence={'positive_members': int(np.count_nonzero(matrix[:, t]))}))
        items.append(dict(member=target, score=float(scores[i]), cf_score=float(cf[i]), content_score=float(content[i]), reasons=reasons))
    items.sort(key=lambda item: (-item['score'], item['member']['id']))
    info['embedder'] = encoder.name
    return dict(member_id=member_id, model=info, items=items[:k])
