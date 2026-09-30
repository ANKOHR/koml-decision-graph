"""argparse command-line interface."""

import argparse
import sys
from .store import Store, KINDS, LEGAL
from .graph import impact, orphans, validate
from .report import render
from .fixtures import generate, HEADER


def parser():
    root = argparse.ArgumentParser(prog="kdg", description="Every decision mapped: what supports it, what it assumes, what breaks if it changes.")
    root.add_argument("--store", metavar="DIR", help="Store directory (default: ~/.kdg)")
    commands = root.add_subparsers(dest="command", required=True)
    for kind in KINDS:
        child = commands.add_parser("add-" + kind, help="Add a " + kind)
        child.add_argument("--title", required=True)
        child.add_argument("--body", default="")
    child = commands.add_parser("import-assumptions", help="Import kal JSON assumptions")
    child.add_argument("path")
    child = commands.add_parser("link", help="Link graph nodes")
    child.add_argument("--from", dest="source", required=True)
    child.add_argument("--to", dest="target", required=True)
    child.add_argument("--kind", required=True, help="Legal kinds: " + ", ".join(sorted(LEGAL)))
    child = commands.add_parser("impact", help="List downstream nodes in BFS order")
    child.add_argument("node_id")
    commands.add_parser("orphans", help="Find decisions without evidence or assumptions")
    child = commands.add_parser("report", help="Render graph")
    child.add_argument("--format", choices=("text", "json"), default="text")
    commands.add_parser("validate", help="Check integrity and depends-on cycles")
    child = commands.add_parser("fixtures", help="Generate SYNTHETIC fixtures with seed 21")
    child.add_argument("--out", required=True)
    for child in commands.choices.values():
        child.add_argument("--store", metavar="DIR", default=argparse.SUPPRESS, help="Store directory")
    return root


def main(argv=None):
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "fixtures":
            generate(arguments.out)
            print(HEADER)
            print("Seed decision: kdg-d1")
            return 0
        store = Store(arguments.store)
        command = arguments.command
        if command.startswith("add-"):
            node_id = store.add(command[4:], arguments.title, arguments.body)
            store.save()
            print(node_id)
        elif command == "link":
            added = store.link(arguments.source, arguments.target, arguments.kind)
            store.save()
            print("Linked" if added else "Duplicate link skipped (no-op)")
        elif command == "import-assumptions":
            added, skipped = store.import_assumptions(arguments.path)
            store.save()
            print(f"Imported {len(added)}: {', '.join(added)}")
            print(f"Skipped {len(skipped)} existing ids: {', '.join(skipped)}")
        elif command == "report":
            print(render(store.graph, arguments.format), end="")
        elif command == "validate":
            problems = validate(store.graph, store.duplicates)
            print("\n".join(problems) if problems else "OK")
            return 1 if problems else 0
        else:
            if store.graph.get("_header"):
                print(store.graph["_header"])
            if command == "impact":
                for node_id, depth in impact(store.graph, arguments.node_id):
                    print(f"{depth} {node_id}: {store.graph['nodes'][node_id]['title']}")
            elif command == "orphans":
                for node_id in orphans(store.graph):
                    print(f"{node_id}: {store.graph['nodes'][node_id]['title']}")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
