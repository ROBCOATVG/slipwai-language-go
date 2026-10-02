"""This package against the conformance suite of the slipwai it is tested with (FR-030, D81).

The language directory is the one this package sits in, so the root suite runs it against the checkout's pins and a copy
under `~/.slipwai/languages` against that directory. Each check is one test, failing with what is missing: `python -m
slipwai.conformance <language-dir> go` prints the same report.
"""
from __future__ import annotations

from pathlib import Path

from slipwai import conformance


class Conformance(conformance.ConformanceCase):
    language_dir = Path(__file__).resolve().parents[2]
    package = "go"
