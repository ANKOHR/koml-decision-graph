# KOML Decision Graph

Every decision mapped: what supports it, what it assumes, what breaks if it changes.

`kdg` is a working Python CLI with a standalone UTF-8 JSON store. It maps decisions to evidence, assumptions, and consequences, and answers blast-radius and unsupported-decision queries. It uses the Python standard library, CPU only, with no network calls or model APIs.

## Quickstart

Python 3.10+ is required. Install from this checkout using locally available setuptools and pip, without accessing the network:

```powershell
python -m pip install --no-deps --no-build-isolation --no-index -e .
kdg add-decision --title "Example project choice" --body "Reasoning and any kcm score"
kdg add-evidence --title "Example measurement" --body "Measurement details"
kdg link --from kdg-d1 --to kdg-e1 --kind supported-by
kdg orphans
kdg validate
```

Without installation, use `python -m kdg.cli` in place of `kdg`. If a Windows user install puts Scripts outside PATH, the same module command works; add the Scripts directory reported by pip to PATH to use `kdg` directly. For development, run `python -m pytest -q` with pytest installed locally. No runtime dependencies are required.

## Architecture

```text
argparse CLI
    |
    +--> Store: JSON load, node IDs, link legality, kal import, atomic save
    |
    +--> Graph queries: BFS impact, orphans, integrity and cycle checks
    |
    +--> Report: full JSON export, bounded text trees, support ratio
    |
    +--> Fixtures: fixed-seed SYNTHETIC graph and hand-computed expectations
```

Modules are `kdg/cli.py`, `store.py`, `graph.py`, `report.py`, and `fixtures.py`. Data is stored at `~/.kdg/graph.json`. `--store DIR` selects `DIR/graph.json` and works before or after the subcommand. Commands that mutate the graph save by replacing a temporary file. Use one writer at a time; concurrent updates are not locked.

## Node and edge schema

```json
{
  "nodes": {
    "kdg-d1": {
      "kind": "decision",
      "title": "Example choice",
      "body": "Reasoning",
      "created_at": "2026-09-30T00:00:00+00:00"
    }
  },
  "edges": []
}
```

Nodes have string `kind`, `title`, `body`, and `created_at` fields. IDs are sequential independently per kind, beginning with `kdg-d1`, `kdg-e1`, `kdg-a1`, and `kdg-c1` for decision, evidence, assumption, and consequence. New IDs use the largest existing native suffix plus one. Edges have string `from`, `to`, and `kind` fields.

| Edge kind | From kind | To kind |
| --- | --- | --- |
| supported-by | decision | evidence |
| relies-on | decision | assumption |
| leads-to | decision | consequence |
| depends-on | decision | decision |

Self-links are rejected. Duplicate links are a reported no-op. Unknown endpoints and invalid kinds produce named errors. Imported IDs retain a `kal-` prefix, so they cannot collide with generated `kdg-aN` IDs. Fixtures add a top-level `_header` field to label JSON as synthetic while preserving parseable JSON.

## Traversal and structural risks

Impact follows outgoing `leads-to` and `depends-on` edges. The direction is literal: `A depends-on B` traverses from A to B. Enter downstream links in the direction you want impact to follow. The seed is excluded; each reachable node appears once with its shortest depth. IDs are sorted lexicographically within each complete depth level, including across branches. A visited set makes cycles safe. Graph traversal is linear before deterministic sorting, which adds a sorting cost per frontier.

Orphans are decisions with neither an outgoing evidence edge nor an outgoing assumption edge. A refuted assumption still counts as an assumption link; its status remains visible in the node body and full JSON report. Orphan detection measures presence of support, not truth or adequacy of support.

Validation reports all detected integrity problems: invalid nodes and edges, dangling endpoints, illegal kind combinations, self-links, duplicate edges, duplicate JSON keys including node IDs, and back edges identifying `depends-on` cycles. JSON duplicate keys are detected during loading before they can silently disappear. Cycles are reported as structural risks even though traversal safely handles them. Invalid JSON or an invalid top-level schema returns a named load error. Impact returns a named error for any dangling downstream edge, rather than silently omitting it.

Text reports render sorted outgoing links as indented trees, beginning with root decisions. Components containing only cycles receive a fallback root. Paths stop at a cycle marker and at depth 8 with `[depth limit: 8]`; this bounds display depth for large graphs. Shared nodes may appear under multiple paths. JSON reports export the complete graph, with sorted object keys and stored edge order, without pruning or adding computed metrics.

## kal import format

Compatibility is with assumption-ledger JSON, using either a list of entries, an object with an `assumptions` list, or a single entry:

```json
{
  "assumptions": [
    {
      "id": "kal-0001",
      "text": "SYNTHETIC illustrative assumption",
      "source": "SYNTHETIC example",
      "stakes": "high",
      "status": "refuted"
    }
  ]
}
```

Each entry requires a string `kal-` prefixed ID and string text. Text becomes the title; all remaining metadata, including source, stakes, and status, is stored as JSON in the body. The original ID is preserved. The original `created_at` is used when supplied; otherwise import time is recorded. Re-import skips existing assumption IDs and reports them; it does not update their values. A collision with a non-assumption node is an error. The full input is checked before adding entries.

## CLI reference

Every subcommand supports `--help` and `--store DIR`.

| Command | Arguments and behavior |
| --- | --- |
| add-decision | `--title TEXT [--body TEXT]`, prints new decision ID |
| add-evidence | `--title TEXT [--body TEXT]`, prints new evidence ID |
| add-assumption | `--title TEXT [--body TEXT]`, prints new assumption ID |
| add-consequence | `--title TEXT [--body TEXT]`, prints new consequence ID |
| import-assumptions | `PATH`, prints added and skipped IDs |
| link | `--from ID --to ID --kind KIND`, validates and saves link |
| impact | `ID`, prints `depth id: title` in BFS order |
| orphans | Prints unsupported decision IDs and titles sorted by ID |
| report | `--format text|json`, defaults to text |
| validate | Prints `OK` or every problem |
| fixtures | `--out DIR`, writes synthetic fixture files, replacing same-named files |

Exit codes: 0 for success, 1 for validation problems, 2 for command or input errors. Text fixture reports, impact, and orphans include the synthetic banner. JSON keeps the banner in `_header` so it remains machine-readable.

## Fixtures and hand computation

```powershell
kdg fixtures --out demo
kdg impact kdg-d1 --store demo
kdg orphans --store demo
kdg report --store demo
kdg import-assumptions demo/kal-ledger.json --store imported-demo
```

Seed 21 and a fixed timestamp make generation byte-identical across repeats. The shipped fixture directory `fixtures/synthetic` contains `graph.json`, `kal-ledger.json`, `expected.json`, and `README.txt`. Every file has a SYNTHETIC header, using `_header` as the first JSON field. All fixture titles and bodies are also labelled SYNTHETIC. There are six decisions, three evidence nodes, two assumption nodes including imported `kal-0001` marked refuted, and two consequences.

Hand-computed impact from `kdg-d1`:

| Depth | IDs in exact order |
| --- | --- |
| 1 | kdg-c1, kdg-d2, kdg-d3 |
| 2 | kdg-c2, kdg-d4 |
| 3 | kdg-d5 |

The edges from d1 lead to c1, d2, and d3. d2 reaches d4, and d3 reaches c2. d4 reaches d5. d5 returns to d2, which is already visited. d6 is disconnected. The planted cycle is `kdg-d2 -> kdg-d4 -> kdg-d5 -> kdg-d2`; fixture validation therefore reports a cycle and exits 1 by design.

The exact orphan set is `kdg-d5`, `kdg-d6`. d1, d2, and d3 have evidence; d4 relies on the refuted `kal-0001` assumption. After the first fixture orphan query, the derived report metric is the evidence support ratio: decisions with at least one evidence edge divided by all decisions. The fixture baseline is **3/6 = 0.5**, printed as `0.500000`. Assumption-only d4 does not increase this metric. Empty graphs have ratio 0. Future real graphs can be compared against this baseline without claiming that synthetic results describe a real organisation.

## HONESTY BOUNDARY

Fixture graphs are synthetic examples, not records of real decisions. Import compatibility is with the assumption-ledger JSON format, not a claim of integration with any real system. No fixture decision, measurement, assumption, or consequence represents real organisational history. No companies, people, or outcomes are invented as evidence.

Real data is not shipped. Henry's own project decisions can be entered in future with add and link commands. Decision bodies can cite confidence-model `kcm` scores as text; no live confidence-model integration is claimed. This project is maintained as KOML infrastructure, with a JSON import path for the assumption ledger. Commercialisation as part of a decision-hygiene bundle remains a future candidate.

## Verification and operational habit

The pytest suite checks every command, fixture determinism, original kal IDs, idempotent import, exact hand-computed BFS and orphan sets, cycle safety, corruption diagnostics, Unicode and 10,000-character body round trips, and a 500-node chain. The installed console script and end-to-end demo can also be exercised locally without network access.

Decision logs become useful when choices link to their support and downstream consequences. Run impact before changing consequential decisions and use orphans as an operational habit. A support link is a starting point for review, not a guarantee of a sound decision.
