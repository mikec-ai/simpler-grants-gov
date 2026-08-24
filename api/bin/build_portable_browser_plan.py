"""Write the portable catalog browser plan to an untracked build-artifact path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.form_schema.form_spec.browser_plan import write_browser_plan


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="JSON plan output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        plan = write_browser_plan(args.out)
    except (OSError, TypeError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    sys.stdout.write(
        "browser_plan:\n"
        f"  contract: {plan['contract']}\n"
        f"  forms: {len(plan['forms'])}\n"
        f"  out: {args.out}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
