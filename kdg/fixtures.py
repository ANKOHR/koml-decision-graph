"""SYNTHETIC fixtures only. Fixed seed 21, no real decision records."""

import json
import random
from pathlib import Path
from .store import Store, encode

HEADER = "SYNTHETIC: fixed seed 21; illustrative graph, not real decision history."
STAMP = "2026-09-30T00:00:00+00:00"
EXPECTED_IMPACT = [["kdg-c1", 1], ["kdg-d2", 1], ["kdg-d3", 1], ["kdg-c2", 2], ["kdg-d4", 2], ["kdg-d5", 3]]
EXPECTED_ORPHANS = ["kdg-d5", "kdg-d6"]


def generate(directory):
    directory = Path(directory)
    rng = random.Random(21)
    store = Store(directory)
    store.graph = {"_header": HEADER, "nodes": {}, "edges": []}
    store.duplicates = []
    for kind, count in (("decision", 6), ("evidence", 3), ("assumption", 1), ("consequence", 2)):
        for index in range(1, count + 1):
            store.add(kind, f"SYNTHETIC {kind} {index}", f"SYNTHETIC illustrative item; sample={rng.randrange(1000)}", created_at=STAMP)
    ledger = {"_header": HEADER, "assumptions": [{"id": "kal-0001", "text": "SYNTHETIC refuted assumption", "source": "SYNTHETIC example", "stakes": "high", "status": "refuted", "created_at": STAMP}]}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "kal-ledger.json").write_bytes(encode(ledger).encode("utf-8"))
    store.import_assumptions(directory / "kal-ledger.json")
    for source, target, kind in [
        ("kdg-d1", "kdg-e1", "supported-by"), ("kdg-d2", "kdg-e2", "supported-by"),
        ("kdg-d3", "kdg-e3", "supported-by"), ("kdg-d4", "kal-0001", "relies-on"),
        ("kdg-d1", "kdg-a1", "relies-on"), ("kdg-d1", "kdg-c1", "leads-to"),
        ("kdg-d1", "kdg-d3", "depends-on"), ("kdg-d1", "kdg-d2", "depends-on"),
        ("kdg-d2", "kdg-d4", "depends-on"), ("kdg-d3", "kdg-c2", "leads-to"),
        ("kdg-d4", "kdg-d5", "depends-on"), ("kdg-d5", "kdg-d2", "depends-on"),
    ]:
        store.link(source, target, kind)
    store.save()
    expected = {"_header": HEADER, "seed": 21, "seed_decision": "kdg-d1", "impact": EXPECTED_IMPACT, "orphans": EXPECTED_ORPHANS}
    (directory / "expected.json").write_bytes(encode(expected).encode("utf-8"))
    (directory / "README.txt").write_bytes((HEADER + "\nSeed decision: kdg-d1\nOrphans: kdg-d5, kdg-d6\nCycle: kdg-d2 -> kdg-d4 -> kdg-d5 -> kdg-d2\n").encode("utf-8"))
    return store.graph
