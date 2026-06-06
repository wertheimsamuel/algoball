"""Tiny Railway-ready web server for AlgoBall.

On startup it generates the latest pre-game dashboard, then serves `public/`.
While the process stays alive, a background scheduler refreshes once each
morning before the slate. This keeps v1 simple: no Flask, no database, no worker
queue, just the standard library and the same pipeline the CLI uses.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from .pipeline import run

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIR = PROJECT_ROOT / "public"
NY = ZoneInfo("America/New_York")


def _write_error_page(exc: BaseException) -> None:
    PUBLIC_DIR.mkdir(exist_ok=True)
    (PUBLIC_DIR / "index.html").write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AlgoBall unavailable</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #0b0e11; color: #e6edf3; }}
    main {{ max-width: 760px; margin: 12vh auto; padding: 24px; }}
    code {{ color: #f85149; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <main>
    <h1>AlgoBall</h1>
    <p>The dashboard could not refresh. The service is still online, but the
    data pipeline failed.</p>
    <p><code>{type(exc).__name__}: {str(exc)}</code></p>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def refresh_dashboard(*, refresh_odds: bool = False) -> None:
    try:
        ctx = run(refresh_odds=refresh_odds)
        print(
            f"[server] refreshed {ctx['date']}: {ctx['n_games']} games, "
            f"{ctx['n_edges']} watchlist edges",
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001 - keep the web process alive
        print(f"[server] refresh failed: {type(exc).__name__}: {exc}", flush=True)
        _write_error_page(exc)


def _next_refresh(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(NY)
    hour = int(os.environ.get("ALGOBALL_REFRESH_HOUR_ET", "10"))
    minute = int(os.environ.get("ALGOBALL_REFRESH_MINUTE_ET", "30"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def scheduler_loop() -> None:
    while True:
        target = _next_refresh()
        sleep_for = max(1.0, (target - datetime.now(NY)).total_seconds())
        print(f"[server] next refresh at {target.isoformat()}", flush=True)
        time.sleep(sleep_for)
        refresh_dashboard(refresh_odds=True)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def do_GET(self):  # noqa: N802 - stdlib hook
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        return super().do_GET()


def main() -> None:
    refresh_dashboard(refresh_odds=False)
    threading.Thread(target=scheduler_loop, daemon=True).start()

    port = int(os.environ.get("PORT", "8000"))
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"[server] serving public/ on port {port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
