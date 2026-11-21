"""A small task list: `python src/cli.py add "text"` and `python src/cli.py list`."""
import argparse
import json
import sys
from pathlib import Path

STORE = Path.home() / ".tasks.json"


def load(store):
    if not store.exists():
        return []
    return json.loads(store.read_text(encoding="utf-8"))


def save(store, tasks):
    store.write_text(json.dumps(tasks, indent=2), encoding="utf-8")


def main(argv=None, store=STORE, out=sys.stdout):
    parser = argparse.ArgumentParser(prog="tasks")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="add a task")
    add.add_argument("text")
    commands.add_parser("list", help="list the tasks, oldest first")
    args = parser.parse_args(argv)
    tasks = load(store)
    if args.command == "add":
        tasks.append(args.text)
        save(store, tasks)
    elif args.command == "list":
        for number, text in enumerate(tasks, start=1):
            print(f"{number}. {text}", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
