"""AlgoBall — an MLB model-vs-market measurement system.

See docs/ARCHITECTURE.md for the full design. The package is deliberately
layered so the same code runs locally with a SQLite database today and on
Railway with Postgres + object storage later (a config change, not a rewrite).
"""

__version__ = "0.1.0"
