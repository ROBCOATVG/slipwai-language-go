"""The `go` language package: the Go backend slipwai loads from its language directory.

`LANGUAGE` is the object core's loader reads: the `go` family and its one backend, answering the backend
protocol. Everything else in this package is what those answers are made of, and the files they read are the
ones under `assets/` beside it.
"""
from __future__ import annotations

from .go import LANGUAGE

__all__ = ["LANGUAGE"]
