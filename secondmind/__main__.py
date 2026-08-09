"""Entry point for ``python3 -m secondmind`` and the ``secondmind`` console script."""

from __future__ import annotations

import sys

from secondmind.cli import run


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
