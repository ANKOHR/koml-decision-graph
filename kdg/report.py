"""JSON export and bounded text trees."""

from collections import defaultdict
from .store import encode

MAX_DEPTH = 8


def support_ratio(graph):
    decisions = {key for key, node in graph["nodes"].items() if node.get("kind") == "decision"}
    supported = {edge.get("from") for edge in graph["edges"] if isinstance(edge, dict) and edge.get("kind") == "supported-by" and graph["nodes"].get(edge.get("to"), {}).get("kind") == "evidence"}
    return len(decisions & supported) / len(decisions) if decisions else 0.0


def render(graph, format="text"):
    if format == "json":
        return encode(graph)
    if format != "text":
        raise ValueError(f"Unknown report format: {format}")
    nodes = graph["nodes"]
    decisions = sorted(key for key, node in nodes.items() if node.get("kind") == "decision")
    adjacency = defaultdict(list)
    incoming = set()
    for edge in graph["edges"]:
        if isinstance(edge, dict) and edge.get("from") in nodes and edge.get("to") in nodes:
            adjacency[edge["from"]].append((edge["to"], edge.get("kind", "?")))
            if edge.get("kind") == "depends-on":
                incoming.add(edge["to"])
    lines = []
    if graph.get("_header"):
        lines.append(graph["_header"])
    lines.append(f"Support ratio (evidence): {support_ratio(graph):.6f}")
    covered = set()
    roots = [key for key in decisions if key not in incoming]
    # A cycle may have no root. Include uncovered components explicitly.
    for root in roots + decisions:
        if root in covered:
            continue
        stack = [(root, 0, frozenset(), "")]
        while stack:
            key, depth, path, label = stack.pop()
            covered.add(key)
            lines.append("  " * depth + label + key + ": " + nodes[key]["title"])
            if key in path:
                lines.append("  " * (depth + 1) + "[cycle]")
                continue
            children = sorted(adjacency[key])
            if depth >= MAX_DEPTH:
                if children:
                    lines.append("  " * (depth + 1) + "[depth limit: 8]")
                continue
            for target, kind in reversed(children):
                stack.append((target, depth + 1, path | {key}, kind + " -> "))
    return "\n".join(lines) + "\n"
