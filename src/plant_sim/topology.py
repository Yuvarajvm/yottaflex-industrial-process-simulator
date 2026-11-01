from collections import defaultdict, deque

def connectivity(nodes, pipes):
    by_fac=defaultdict(set); adj=defaultdict(set)
    for n in nodes: by_fac[n["facility_id"]].add(n["node_id"])
    for p in pipes:
        if p["from_node_id"]==p["to_node_id"]: raise ValueError(f"self connection: {p['pipe_id']}")
        if p["from_node_id"] not in by_fac[p["facility_id"]] or p["to_node_id"] not in by_fac[p["facility_id"]]: raise ValueError(f"invalid node reference: {p['pipe_id']}")
        adj[p["from_node_id"]].add(p["to_node_id"]); adj[p["to_node_id"]].add(p["from_node_id"])
    result={}
    for fac, ns in by_fac.items():
        if not ns: result[fac]=False; continue
        seen=set(); q=deque([next(iter(ns))])
        while q:
            cur=q.popleft()
            if cur in seen: continue
            seen.add(cur); q.extend(adj[cur]-seen)
        result[fac]=seen==ns
    return result
