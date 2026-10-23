"""Generate both rungs through the keel and hold what each service is given to what its rung asks for.

Generation is fast and needs no Go toolchain, so these run with the rest of the package's suite. The native
gates — every rung and store held to its own `make verify`, and Postgres's contract against a real database —
opt in with `SLIPWAI_STATE_NATIVE=1` and a `DATABASE_URL`, because they need Go and a server.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from slipwai.matrix.rows import Row
from slipwai.matrix.run import generate

PACKAGE_PARENT = Path(__file__).resolve().parents[2]


class StateSkeleton(unittest.TestCase):
    def generated(self, rung: str, persistence: str, profile: str = "event-modelling", http: str = "net-http") -> Path:
        parent = Path(tempfile.mkdtemp(prefix="slipwai-go-state-"))
        self.addCleanup(shutil.rmtree, parent, True)
        answers: tuple[tuple[str, str], ...] = (("target", "none"),)
        if profile == "event-modelling":
            answers += (("write-model", rung), ("persistence", persistence), ("http", http))
        repo, said = generate(PACKAGE_PARENT, parent, Row("proof", profile, "go", "none", answers))
        self.assertIsNotNone(repo, said)
        assert repo is not None
        return repo

    def test_state_is_given_a_repository_and_no_log_for_every_store(self) -> None:
        for persistence in ("memory", "sqlite", "postgres"):
            with self.subTest(persistence=persistence):
                service = self.generated("state", persistence) / "apps/service"
                self.assertTrue((service / "application/ports/repository/repository.go").is_file())
                self.assertTrue((service / "repositorycontract/contract.go").is_file())
                self.assertFalse((service / "application/ports/events").exists())
                self.assertFalse((service / "projections").exists())
                entry = (service / "cmd/serve/main.go").read_text(encoding="utf-8")
                self.assertIn("apphttp.Readiness(states)", entry)
                self.assertNotIn("__STORE_", entry)
                if persistence != "memory":
                    self.assertIn(f"// backing-service:{persistence}:begin", entry)
                    self.assertTrue((service / f"adapters/driven/repository{persistence}/repository.go").is_file())
                if persistence == "postgres":
                    self.assertEqual(sorted(path.name for path in (service / "migrations").glob("*.sql")),
                                     ["001_states.sql"])

    def test_standard_keeps_current_state_in_memory(self) -> None:
        service = self.generated("state", "memory", "standard") / "apps/service"
        self.assertTrue((service / "adapters/driven/repositorymemory/repository.go").is_file())
        self.assertFalse((service / "application/ports/events").exists())

    def test_events_keep_the_log_and_the_durable_store_brings_the_seed_door(self) -> None:
        repo = self.generated("events", "postgres")
        service = repo / "apps/service"
        self.assertTrue((service / "application/ports/events/events.go").is_file())
        self.assertFalse((service / "application/ports/repository").exists())
        self.assertIn("eventstorepostgres", (service / "cmd/seed/main.go").read_text(encoding="utf-8"))
        makefile = (repo / "Makefile").read_text(encoding="utf-8")
        self.assertIn("seed-service:", makefile)
        self.assertIn("go run ./cmd/seed $(abspath $(FILE))", makefile)
        bare = self.generated("events", "memory")
        self.assertFalse((bare / "apps/service/cmd/seed").exists())
        self.assertNotIn("seed-service:", (bare / "Makefile").read_text(encoding="utf-8"))

    @unittest.skipUnless(os.environ.get("SLIPWAI_STATE_NATIVE") == "1", "the native rung proof needs Go and Postgres")
    def test_both_rungs_pass_their_gates_and_the_postgres_contract(self) -> None:
        self.assertTrue(os.environ.get("DATABASE_URL"), "DATABASE_URL is required for the Postgres contract")
        for rung in ("state", "events"):
            for persistence in ("memory", "sqlite", "postgres"):
                with self.subTest(rung=rung, persistence=persistence):
                    repo = self.generated(rung, persistence)
                    self.run_gate(["make", "verify"], repo)
                    if persistence == "postgres":
                        # One database for both rungs: a state service's schema and an event log's do not
                        # collide, and the migration ledger is shared, so each rung's runs once.
                        self.run_gate(["go", "run", "./cmd/migrate"], repo / "apps/service")
                        self.run_gate(["go", "test", "-count=1", "-tags=integration", "./..."], repo / "apps/service")
                        if rung == "state":
                            self.run_gate([sys.executable, "scripts/backing-services.py", "--persistence", "memory"],
                                          repo)
                            self.assertFalse((repo / "apps/service/adapters/driven/repositorypostgres").exists())
                            self.run_gate(["make", "verify"], repo)

    def run_gate(self, command: list[str], where: Path) -> None:
        done = subprocess.run(command, cwd=where, text=True, capture_output=True, timeout=600)
        self.assertEqual(done.returncode, 0, done.stdout[-12000:] + done.stderr[-6000:])
