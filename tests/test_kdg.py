import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kdg.store import Store, encode
from kdg.graph import impact, orphans, validate
from kdg.report import render, support_ratio
from kdg.fixtures import generate, EXPECTED_IMPACT, EXPECTED_ORPHANS


def cli(*args):
    return subprocess.run([sys.executable, "-m", "kdg.cli", *map(str, args)], capture_output=True, text=True, encoding="utf-8")


def test_ids_sequential_per_kind(tmp_path):
    store = Store(tmp_path)
    for kind, prefix in [("decision", "d"), ("evidence", "e"), ("assumption", "a"), ("consequence", "c")]:
        assert store.add(kind, "one") == f"kdg-{prefix}1"
        assert store.add(kind, "two") == f"kdg-{prefix}2"
    store.save()
    assert Store(tmp_path).graph == store.graph


@pytest.mark.parametrize("source,target", [("missing-from", "kdg-e1"), ("kdg-d1", "missing-to")])
def test_link_validates_endpoints(tmp_path, source, target):
    store = Store(tmp_path)
    store.add("decision", "D")
    store.add("evidence", "E")
    with pytest.raises(ValueError, match="missing-"):
        store.link(source, target, "supported-by")


def test_link_rejects_illegal_kind(tmp_path):
    store = Store(tmp_path)
    store.add("decision", "D")
    store.add("evidence", "E")
    with pytest.raises(ValueError, match="Illegal supported-by"):
        store.link("kdg-e1", "kdg-d1", "supported-by")
    with pytest.raises(ValueError, match="Self-link"):
        store.link("kdg-d1", "kdg-d1", "depends-on")
    with pytest.raises(ValueError, match="legal kinds: depends-on, leads-to, relies-on, supported-by"):
        store.link("kdg-d1", "kdg-e1", "typo")


def test_link_duplicate_idempotent(tmp_path):
    store = Store(tmp_path)
    store.add("decision", "D")
    store.add("evidence", "E")
    store.save()
    args = ("link", "--from", "kdg-d1", "--to", "kdg-e1", "--kind", "supported-by", "--store", tmp_path)
    assert cli(*args).returncode == 0
    assert "Duplicate link skipped" in cli(*args).stdout
    assert len(Store(tmp_path).graph["edges"]) == 1


def test_impact_transitive_bfs(tmp_path):
    store = Store(tmp_path)
    for _ in range(5):
        store.add("decision", "D")
    for source, target in [(1, 3), (1, 2), (2, 4), (4, 5)]:
        store.link(f"kdg-d{source}", f"kdg-d{target}", "depends-on")
    assert impact(store.graph, "kdg-d1") == [("kdg-d2", 1), ("kdg-d3", 1), ("kdg-d4", 2), ("kdg-d5", 3)]


def test_impact_cycle_safe(tmp_path):
    graph = generate(tmp_path)
    assert impact(graph, "kdg-d1") == [tuple(item) for item in EXPECTED_IMPACT]
    assert len({key for key, _ in impact(graph, "kdg-d2")}) == 2
    assert any("depends-on cycle" in problem for problem in validate(graph))


def test_orphans_exact_set(tmp_path):
    graph = generate(tmp_path)
    assert orphans(graph) == EXPECTED_ORPHANS
    assert support_ratio(graph) == 3 / 6


@pytest.mark.parametrize("shape", ["list", "wrapper", "single"])
def test_import_assumptions_compat(tmp_path, shape):
    entries = [{"id": "kal-0001", "text": "Assumption", "source": "Example", "stakes": "high", "status": "refuted", "extra": 42}]
    data = entries if shape == "list" else {"assumptions": entries} if shape == "wrapper" else entries[0]
    path = tmp_path / "ledger.json"
    path.write_text(encode(data), encoding="utf-8")
    store = Store(tmp_path)
    assert store.import_assumptions(path) == (["kal-0001"], [])
    assert store.import_assumptions(path) == ([], ["kal-0001"])
    assert json.loads(store.graph["nodes"]["kal-0001"]["body"])["status"] == "refuted"
    assert store.add("assumption", "native") == "kdg-a1"


def test_import_atomic_invalid_input(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(encode([{"id": "kal-1", "text": "good"}, {"id": "kdg-a1", "text": "bad"}]), encoding="utf-8")
    store = Store(tmp_path)
    with pytest.raises(ValueError, match="kal-"):
        store.import_assumptions(path)
    assert not store.graph["nodes"]


def test_validate_catches_dangling(tmp_path):
    graph = generate(tmp_path)
    graph["edges"].append({"from": "kdg-d1", "to": "missing", "kind": "depends-on"})
    assert "Dangling edge: kdg-d1 -> missing" in validate(graph)
    with pytest.raises(ValueError, match="missing"):
        impact(graph, "kdg-d1")
    store = Store(tmp_path)
    store.graph = graph
    store.save()
    result = cli("impact", "kdg-d1", "--store", tmp_path)
    assert result.returncode == 2 and "missing" in result.stderr
    assert "missing" in cli("validate", "--store", tmp_path).stdout


def test_validate_duplicate_ids_and_other_corruption(tmp_path):
    node = '{"kind":"decision","title":"D","body":"","created_at":"now"}'
    (tmp_path / "graph.json").write_text('{"nodes":{"kdg-d1":' + node + ',"kdg-d1":' + node + '},"edges":[]}', encoding="utf-8")
    store = Store(tmp_path)
    assert any("Duplicate node id" in item for item in validate(store.graph, store.duplicates))
    with pytest.raises(ValueError, match="Duplicate"):
        store.save()
    graph = {"nodes": {"x": {}}, "edges": [None, {"from": "x", "to": "x", "kind": "typo"}]}
    problems = validate(graph)
    assert any("Invalid node" in item for item in problems)
    assert any("Illegal edge" in item for item in problems)
    assert any("Self-link" in item for item in problems)


def test_report_json_roundtrip(tmp_path):
    graph = generate(tmp_path)
    assert json.loads(render(graph, "json")) == Store(tmp_path).graph
    assert render(graph) == render(graph)
    assert "[cycle]" in render(graph)
    assert "Support ratio (evidence): 0.500000" in render(graph)


def test_fixtures_deterministic(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    generate(first)
    generate(second)
    for file in first.iterdir():
        assert file.read_bytes() == (second / file.name).read_bytes()
        assert "SYNTHETIC" in "\n".join(file.read_text(encoding="utf-8").splitlines()[:3])
    before = (first / "graph.json").read_bytes()
    generate(first)
    assert (first / "graph.json").read_bytes() == before


def test_unicode_and_large_body_roundtrip(tmp_path):
    store = Store(tmp_path)
    title, body = "選択 café 🧭", "界é🧭\n" * 2500
    assert len(body) == 10000
    node_id = store.add("decision", title, body)
    store.save()
    loaded = Store(tmp_path).graph["nodes"][node_id]
    assert loaded["title"].encode("utf-8") == title.encode("utf-8")
    assert loaded["body"].encode("utf-8") == body.encode("utf-8")


def test_impact_non_decision_and_unknown(tmp_path):
    store = Store(tmp_path)
    store.add("evidence", "E")
    for key, message in [("kdg-e1", "requires a decision: kdg-e1"), ("unknown", "Unknown node id: unknown")]:
        with pytest.raises(ValueError, match=message):
            impact(store.graph, key)


def test_500_node_chain(tmp_path):
    store = Store(tmp_path)
    for _ in range(500):
        store.add("decision", "D")
    for index in range(1, 500):
        store.link(f"kdg-d{index}", f"kdg-d{index + 1}", "depends-on")
    start = time.perf_counter()
    result = impact(store.graph, "kdg-d1")
    assert result == [(f"kdg-d{index}", index - 1) for index in range(2, 501)]
    assert time.perf_counter() - start < 2
    assert validate(store.graph) == []
    assert "[depth limit: 8]" in render(store.graph)


@pytest.mark.parametrize("command", ["add-decision", "add-evidence", "add-assumption", "add-consequence", "import-assumptions", "link", "impact", "orphans", "report", "validate", "fixtures"])
def test_cli_help(command):
    result = cli(command, "--help")
    assert result.returncode == 0 and "usage: kdg" in result.stdout


def test_cli_end_to_end(tmp_path):
    for kind, prefix in [("decision", "d"), ("evidence", "e"), ("assumption", "a"), ("consequence", "c")]:
        result = cli("--store", tmp_path, "add-" + kind, "--title", "Example", "--body", "Body")
        assert result.returncode == 0 and result.stdout.strip() == f"kdg-{prefix}1"
    for target, kind in [("kdg-e1", "supported-by"), ("kdg-a1", "relies-on"), ("kdg-c1", "leads-to")]:
        assert cli("link", "--from", "kdg-d1", "--to", target, "--kind", kind, "--store", tmp_path).returncode == 0
    assert cli("validate", "--store", tmp_path).stdout.strip() == "OK"
    assert cli("orphans", "--store", tmp_path).stdout == ""
    assert "1 kdg-c1" in cli("impact", "kdg-d1", "--store", tmp_path).stdout
    assert json.loads(cli("report", "--format", "json", "--store", tmp_path).stdout) == Store(tmp_path).graph
    assert "Support ratio" in cli("report", "--store", tmp_path).stdout
    demo = tmp_path / "demo"
    assert cli("fixtures", "--out", demo).returncode == 0
    result = cli("impact", "kdg-d1", "--store", demo)
    assert result.returncode == 0
    assert [(line.split()[1].rstrip(":"), int(line.split()[0])) for line in result.stdout.splitlines()[1:]] == [tuple(item) for item in EXPECTED_IMPACT]
    assert [line.split(":")[0] for line in cli("orphans", "--store", demo).stdout.splitlines()[1:]] == EXPECTED_ORPHANS
    assert "Imported 1: kal-0001" in cli("import-assumptions", demo / "kal-ledger.json", "--store", tmp_path).stdout
    assert "Skipped 1 existing ids: kal-0001" in cli("import-assumptions", demo / "kal-ledger.json", "--store", tmp_path).stdout
    assert cli("validate", "--store", demo).returncode == 1
    result = cli("link", "--from", "kdg-d1", "--to", "kdg-e1", "--kind", "typo", "--store", tmp_path)
    assert result.returncode == 2 and "legal kinds" in result.stderr


def test_no_em_dash_in_project():
    root = Path(__file__).resolve().parents[1]
    for path in [*root.glob("kdg/*.py"), *root.glob("tests/*.py"), root / "README.md", root / "pyproject.toml"]:
        assert chr(0x2014) not in path.read_text(encoding="utf-8")


def test_shipped_fixtures_match_generator(tmp_path):
    generate(tmp_path)
    shipped = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
    for path in tmp_path.iterdir():
        assert path.read_bytes() == (shipped / path.name).read_bytes()


def test_validate_legal_edges_and_duplicate_edge(tmp_path):
    store = Store(tmp_path)
    store.add("decision", "D")
    store.add("evidence", "E")
    store.link("kdg-d1", "kdg-e1", "supported-by")
    assert validate(store.graph) == []
    store.graph["edges"].append(store.graph["edges"][0].copy())
    assert any("Duplicate edge" in item for item in validate(store.graph))


def test_empty_graph_queries(tmp_path):
    graph = Store(tmp_path).graph
    assert orphans(graph) == []
    assert validate(graph) == []
    assert support_ratio(graph) == 0
    assert json.loads(render(graph, "json")) == graph


def test_cli_malformed_store(tmp_path):
    (tmp_path / "graph.json").write_text("not JSON", encoding="utf-8")
    result = cli("validate", "--store", tmp_path)
    assert result.returncode == 2 and "Error:" in result.stderr
    (tmp_path / "graph.json").write_text('{"nodes": [], "edges": {}}', encoding="utf-8")
    result = cli("validate", "--store", tmp_path)
    assert result.returncode == 2 and "nodes object and an edges list" in result.stderr
