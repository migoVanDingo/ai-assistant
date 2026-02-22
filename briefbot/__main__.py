"""Module entrypoint for `python -m briefbot`.

Delegates to `briefbot.cli.main`, which parses CLI commands and runs
collect/export workflows.
"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
