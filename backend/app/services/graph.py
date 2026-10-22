def graph(members, interactions):
    neighbors = {m['id']: set() for m in members}
    edges = []
    seen = set()
    for row in interactions:
        a, b = row['member_id'], row['target_id']
        if a not in neighbors or b not in neighbors:
            continue
        key = (a, b, row['kind'])
        if key not in seen:
            edges.append(dict(source=a, target=b, kind=row['kind']))
            seen.add(key)
        if row['kind'] in ('like', 'accept'):
            neighbors[a].add(b)
            neighbors[b].add(a)
    nodes = [dict(id=m['id'], name=m['name'], degree=len(neighbors[m['id']]), isolated=not neighbors[m['id']], is_seed=m['is_seed']) for m in members]
    n = len(nodes)
    degree_sum = sum(node['degree'] for node in nodes)
    return dict(nodes=nodes, edges=edges, metrics=dict(density=degree_sum/(n*(n-1)) if n > 1 else 0.0, n_isolated=sum(node['isolated'] for node in nodes), avg_degree=degree_sum/n if n else 0.0))
