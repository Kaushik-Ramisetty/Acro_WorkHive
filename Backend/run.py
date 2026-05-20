"""Run the HRMS backend without needing to remember uvicorn flags.

    python run.py                     # http://127.0.0.1:8000, --reload
    python run.py --host 0.0.0.0      # listen on all interfaces
    python run.py --port 8080         # custom port
    python run.py --no-reload         # disable auto-reload
"""
import argparse
import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    # Make sure imports resolve regardless of where the user invoked python.
    here = Path(__file__).resolve().parent
    os.chdir(here)
    sys.path.insert(0, str(here))

    parser = argparse.ArgumentParser(description="HRMS backend launcher")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        # Watch both `app/` (core) and `api/` (onboarding) so dev reload picks
        # up edits in either subtree.
        reload_dirs=(
            [str(here / "app"), str(here / "api"), str(here / "utils")]
            if not args.no_reload else None
        ),
    )


if __name__ == "__main__":
    main()
