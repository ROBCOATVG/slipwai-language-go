"""This package's own generated-variant matrix, against the slipwai it is tested with (FR-036, D100).

Every native-gate variant of each backend this package owns is generated and held to its own `make verify`, and its
production image built and started where Docker is here. That takes minutes and every toolchain, so the case skips
unless `SLIPWAI_MATRIX=1`; `python -m slipwai.matrix <language-dir> go` runs the same cases. The language directory is
the one this package sits in, so the root suite's shims run it against the checkout's pins.

The row only Go has is here: `make mutation` over a service importing a workspace module.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from slipwai import matrix


class Matrix(matrix.MatrixCase):
    language_dir = Path(__file__).resolve().parents[2]
    package = "go"

    def test_a_go_service_importing_a_workspace_module_is_mutation_tested(self) -> None:
        """`make mutation` on the layout `docs/architecture.md` prescribes for shared Go code.

        Gremlins copies only the module it mutates and scores the build failure that follows as a kill, so
        before `scripts/go-mutation.py` this passed with a test that could not fail. Three runs: the sweep,
        whose test kills the mutant in the importing package and whose report has to outlive the staging
        tree; the same sweep scoped to the one changed file; and a run whose test cannot kill the mutant — a
        wrapper that lost the shared module would pass the first and the last alike. Here and nowhere else,
        because `make mutation` is run by no gate in a generated project (docs/backend-obligations.md
        section 2). Moved from the root suite with the rest of Go's matrix (D100)."""
        self.require("go")
        repo = self.generate("mutation-go", "event-modelling", "go", "none", event_store="memory")
        shared = repo / "packages/greeting"
        shared.mkdir()
        (shared / "go.mod").write_text("module example.com/mutation-go/greeting\n\ngo 1.22\n")
        (shared / "greeting.go").write_text(
            'package greeting\n\nfunc Label(ok bool) string {\n\tif ok {\n\t\treturn "ok"\n\t}\n'
            '\treturn "degraded"\n}\n'
        )
        with (repo / "go.work").open("a") as work:
            work.write("use ./packages/greeting\n")
        (repo / "apps/service/health/health.go").write_text(
            'package health\n\nimport "example.com/mutation-go/greeting"\n\n'
            'type Status struct {\n\tStatus string `json:"status"`\n}\n\n'
            'func Check() Status {\n\tlabel := greeting.Label(true)\n\tif label != "ok" {\n'
            '\t\tlabel = "unknown"\n\t}\n\treturn Status{Status: label}\n}\n'
        )
        run = ["make", "mutation"]
        strong = subprocess.run(run, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(strong.returncode, 0, strong.stdout)
        self.assertIn("staged packages/greeting", strong.stdout)
        self.assertIn("KILLED CONDITIONALS_NEGATION at health/health.go", strong.stdout)

        # The report is the stage's evidence, and Gremlins writes it inside the staging tree the wrapper
        # deletes: without the copy out, `make mutation` leaves a scrollback and nothing to re-read.
        report = repo / "apps/service/gremlins.json"
        self.assertTrue(report.is_file(), strong.stdout)
        mutated = json.loads(report.read_text())["files"]
        self.assertIn("health/health.go", {entry["file_name"] for entry in mutated})

        # Scoped to the one changed file. This is the layout Gremlins' own `--diff` cannot serve — a
        # module in a subdirectory, where it matches repository-root paths against module-relative ones
        # and skips everything — so what is proved here is that the scope reaches the right file and
        # that the run is smaller than the sweep above, not merely that the flag is accepted.
        scoped = subprocess.run([*run, "SINCE=HEAD"], cwd=repo, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(scoped.returncode, 0, scoped.stdout)
        self.assertIn("scoped to 1 changed file(s) since HEAD: health/health.go", scoped.stdout)
        self.assertEqual({entry["file_name"] for entry in json.loads(report.read_text())["files"]},
                         {"health/health.go"})
        self.assertLess(sum(len(entry["mutations"]) for entry in json.loads(report.read_text())["files"]),
                        sum(len(entry["mutations"]) for entry in mutated))
        (repo / "apps/service/health/health_test.go").write_text(
            'package health\n\nimport "testing"\n\n'
            'func TestReportsReady(t *testing.T) {\n\t_ = Check().Status\n}\n'
        )
        weak = subprocess.run(run, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotEqual(weak.returncode, 0, weak.stdout)
        self.assertIn("LIVED CONDITIONALS_NEGATION at health/health.go", weak.stdout)
