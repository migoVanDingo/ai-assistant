"""Module entrypoint for `python -m briefbot`.

Delegates to `briefbot.cli.main`, which parses CLI commands and runs
collect/export workflows.
"""

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency at import time
    load_dotenv = None

from .cli import main


if __name__ == "__main__":
    if load_dotenv:
        load_dotenv()
    raise SystemExit(main())
