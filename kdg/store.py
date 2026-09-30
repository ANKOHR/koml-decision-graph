"""UTF-8 JSON persistence and graph mutations."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

KINDS = {"decision": "d", "evidence": "e", "assumption": "a", "consequence": "c"}
LEGAL = {
    "supported-by": ("decision", "evidence"),
    "relies-on": ("decision", "assumption"),
    "leads-to": ("decision", "consequence"),
    "depends-on": ("decision", "decision"),
}


def encode(graph):
    return json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


class Store:
    def __init__(self, directory=None):
        self.path = Path(directory).expanduser() / "graph.json" if directory else Path.home() / ".kdg" / "graph.json"
        self.duplicates = []
        self.graph = {"nodes": {}, "edges": []}
        if self.path.exists():
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        self.duplicates.append(key)
                    result[key] = value
                return result
            self.graph = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
        if not isinstance(self.graph, dict) or not isinstance(self.graph.get("nodes"), dict) or not isinstance(self.graph.get("edges"), list):
            raise ValueError("Store requires a nodes object and an edges list")

    def save(self):
        if self.duplicates:
            raise ValueError("Duplicate JSON keys: " + ", ".join(self.duplicates))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(encode(self.graph))
        os.replace(temporary, self.path)

    def add(self, kind, title, body="", node_id=None, created_at=None):
        if kind not in KINDS:
            raise ValueError(f"Unknown node kind: {kind}")
        nodes = self.graph["nodes"]
        if node_id is None:
            prefix = f"kdg-{KINDS[kind]}"
            numbers = [int(key[len(prefix):]) for key in nodes if key.startswith(prefix) and key[len(prefix):].isdigit()]
            node_id = prefix + str(max(numbers, default=0) + 1)
        if node_id in nodes:
            raise ValueError(f"Node already exists: {node_id}")
        nodes[node_id] = {"kind": kind, "title": title, "body": body, "created_at": created_at or datetime.now(timezone.utc).isoformat()}
        return node_id

    def link(self, source, target, kind):
        for node_id in (source, target):
            if node_id not in self.graph["nodes"]:
                raise ValueError(f"Unknown node id: {node_id}")
        if kind not in LEGAL:
            raise ValueError(f"Unknown edge kind: {kind}; legal kinds: {', '.join(sorted(LEGAL))}")
        if source == target:
            raise ValueError(f"Self-link rejected: {source}")
        actual = tuple(self.graph["nodes"][key]["kind"] for key in (source, target))
        if actual != LEGAL[kind]:
            raise ValueError(f"Illegal {kind} edge: {source} -> {target}; requires {' -> '.join(LEGAL[kind])}")
        edge = {"from": source, "to": target, "kind": kind}
        if edge in self.graph["edges"]:
            return False
        self.graph["edges"].append(edge)
        return True

    def import_assumptions(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = data if isinstance(data, list) else data.get("assumptions") if isinstance(data, dict) else None
        if entries is None and isinstance(data, dict) and "id" in data:
            entries = [data]
        if not isinstance(entries, list):
            raise ValueError("Expected a kal entry, list, or object with assumptions list")
        # Validate the entire input before changing the graph.
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].startswith("kal-") or not isinstance(entry.get("text"), str):
                raise ValueError("Each assumption requires a kal- prefixed id and text")
            if entry["id"] in self.graph["nodes"] and self.graph["nodes"][entry["id"]]["kind"] != "assumption":
                raise ValueError(f"Import id collision: {entry['id']} is not an assumption")
        added, skipped = [], []
        for entry in entries:
            node_id = entry["id"]
            if node_id in self.graph["nodes"]:
                skipped.append(node_id)
                continue
            body = json.dumps({key: value for key, value in entry.items() if key not in ("id", "text")}, ensure_ascii=False, sort_keys=True)
            self.add("assumption", entry["text"], body, node_id=node_id, created_at=entry.get("created_at"))
            added.append(node_id)
        return added, skipped
