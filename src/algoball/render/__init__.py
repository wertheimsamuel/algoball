"""Static dashboard rendering for AlgoBall.

Pure standard-library HTML rendering (no templating engine). The public entry
point is :func:`render_html`, which turns a prepared context dict into a single
self-contained, dark-themed HTML string ready to write to disk and serve.
"""
from __future__ import annotations

from .renderer import render_html

__all__ = ["render_html"]
