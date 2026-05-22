import argparse
import importlib
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="gradelab_runner")
    parser.add_argument("--context", required=True, help="Path to context JSON file")
    parser.add_argument("--entry-module", required=True, help="Dotted module path to import")
    parser.add_argument("--entry-function", required=True, help="Function name to call in the module")
    args = parser.parse_args()

    context_path = Path(args.context)
    if not context_path.exists():
        print(json.dumps({"error": f"context file not found: {args.context}"}))
        print(f"context file not found: {args.context}", file=sys.stderr)
        sys.exit(1)

    try:
        context = json.loads(context_path.read_text())
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON in context file: {exc}"}))
        print(f"invalid JSON in context file: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        module = importlib.import_module(args.entry_module)
    except ImportError as exc:
        print(json.dumps({"error": f"cannot import module '{args.entry_module}': {exc}"}))
        print(f"cannot import module '{args.entry_module}': {exc}", file=sys.stderr)
        sys.exit(1)

    func = getattr(module, args.entry_function, None)
    if func is None:
        msg = f"function '{args.entry_function}' not found in module '{args.entry_module}'"
        print(json.dumps({"error": msg}))
        print(msg, file=sys.stderr)
        sys.exit(1)

    try:
        result = func(context)
    except Exception as exc:
        print(json.dumps({"error": f"pipeline raised an exception: {exc}"}))
        print(f"pipeline raised an exception: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
