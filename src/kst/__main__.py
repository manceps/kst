"""``python -m kst`` entry point. Routes to :mod:`kst.cli`."""

from __future__ import annotations

import sys

from kst.cli import main


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
