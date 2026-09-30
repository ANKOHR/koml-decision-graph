"""Deterministic, cycle-safe graph queries."""

from collections import defaultdict
from .store import KINDS, LEGAL


def impact(graph, seed):
    nodes = graph["nodes"]
    if seed not in nodes:
        raise ValueError(f"Unknown node id: {seed}")
    if nodes[seed].get("kind") != "decision":
        raise ValueError(f"Impact requires a decision: {seed}")
    adjacency = defaultdict(set)
    for edge in graph["edges"]:
        if isinstance(edge, dict) and edge.get("kind") in ("leads-to", "depends-on"):
            source, target = edge.get("from"), edge.get("to")
            if source not in nodes or target not in nodes:
                raise ValueError(f"Dangling edge: {source} -> {target}")
            adjacency[source].add(target)
    seen, frontier, result, depth = {seed}, [seed], [], 0
    while frontier:
        following = sorted({target for source in frontier for target in adjacency[source]} - seen)
        depth += 1
        result.extend((node_id, depth) for node_id in following)
        seen.update(following)
        frontier = following
    return result


def orphans(graph):
    supported = {edge.get("from") for edge in graph["edges"] if isinstance(edge, dict) and edge.get("kind") in ("supported-by", "relies-on") and edge.get("to") in graph["nodes"]}
    return sorted(key for key, node in graph["nodes"].items() if node.get("kind") == "decision" and key not in supported)


def validate(graph, duplicates=()):
    problems = [f"Duplicate node id or JSON key: {key}" for key in sorted(set(duplicates))]
    nodes = graph["nodes"]
    for key, node in sorted(nodes.items()):
        if not isinstance(node, dict) or node.get("kind") not in KINDS or any(not isinstance(node.get(field), str) for field in ("title", "body", "created_at")):
            problems.append(f"Invalid node: {key}")
    adjacency = defaultdict(set)
    seen_edges = set()
    for edge in graph["edges"]:
        if not isinstance(edge, dict) or any(not isinstance(edge.get(field), str) for field in ("from", "to", "kind")):
            problems.append(f"Invalid edge: {edge!r}")
            continue
        source, target, kind = edge["from"], edge["to"], edge["kind"]
        signature = (source, target, kind)
        if signature in seen_edges:
            problems.append(f"Duplicate edge: {source} -> {target} ({kind})")
        seen_edges.add(signature)
        if source not in nodes or target not in nodes:
            problems.append(f"Dangling edge: {source} -> {target}")
            continue
        if kind not in LEGAL or tuple(nodes[key].get("kind") if isinstance(nodes[key], dict) else None for key in (source, target)) != LEGAL.get(kind):
            problems.append(f"Illegal edge kind: {kind}: {source} -> {target}")
        if source == target:
            problems.append(f"Self-link: {source}")
        if kind == "depends-on":
            adjacency[source].add(target)
    # Iterative DFS avoids Python's recursion limit on long chains.
    colour = {}
    for root in sorted(nodes):
        if colour.get(root):
            continue
        colour[root] = 1
        stack = [(root, iter(sorted(adjacency[root])))]
        while stack:
            source, children = stack[-1]
            target = next(children, None)
            if target is None:
                colour[source] = 2
                stack.pop()
            elif colour.get(target) == 1:
                problems.append(f"depends-on cycle: {source} -> {target}")
            elif not colour.get(target):
                colour[target] = 1
                stack.append((target, iter(sorted(adjacency[target]))))
    return sorted(problems)
