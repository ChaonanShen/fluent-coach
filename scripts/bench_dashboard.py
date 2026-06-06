#!/usr/bin/env python3
"""Start the read-only conversation bench dashboard."""

from __future__ import annotations

import os

try:
    from scripts import _bootstrap  # noqa: F401
except ModuleNotFoundError:
    import _bootstrap  # noqa: F401
import uvicorn

from backend.app.testkit.dashboard import dashboard_app


def main() -> int:
    host = os.environ.get("BENCH_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.environ.get("BENCH_DASHBOARD_PORT", "8100"))
    uvicorn.run(dashboard_app, host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
