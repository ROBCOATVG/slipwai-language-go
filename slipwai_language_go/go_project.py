"""The Go backend's answers about the project around its services: what git ignores, what an agent may run, what
the gate is called, where the event model's code lives, and what `make mutation` is.

Moved here from core's per-backend tables (S05), keyed by the protocol's member constants, so the Go family is one
place to read and to change. `go.py` merges `ANSWERS` into its backend."""
from __future__ import annotations

from typing import Any

from slipwai import registry as protocol
from slipwai.project.renovate import RenovateRules

# Gremlins, pinned to a release and run through `go run`, so the tool is never a dependency of the module it
# mutates and the same build runs on every machine. It replaced go-mutesting, whose package loader was
# golang.org/x/tools from 2019 and crashed inside `go/types` on any package importing a module outside the
# standard library — every adapter — so `./...` never reached a project's tests and the target was a
# placeholder. Gremlins loads with a current x/tools; 0.6.0 was run against the generated service with and
# without third-party imports on Go 1.26.5 before this pin was written, and a deliberately weakened test was
# checked to leave survivors and a red target. It requires Go 1.25 or newer: an older `go` with the default
# `GOTOOLCHAIN=auto` downloads one for the run and leaves the project's own toolchain alone.
GO_GREMLINS = "github.com/go-gremlins/gremlins/cmd/gremlins@v0.6.0"

# Where a Go service's mutation gate is written, relative to the service: the threshold Gremlins reads.
GO_GREMLINS_CONFIG = ".gremlins.yaml"

# Where a Go service's mutation run leaves its report, relative to the service. Named here because the note
# points at it per service and `gitignore.py` keeps it out of the history: one run, one machine, replaced by
# the next run.
GO_GREMLINS_REPORT = "gremlins.json"

# The script `make mutation` runs Gremlins through, written once per project by `languages/go.py` from the
# asset of the same name. It exists because of two things verified against 0.6.0 on 2026-09-09 (the marches
# review of the Gremlins migration raised the first):
#
#   1. Gremlins copies the module it mutates — the nearest go.mod upwards, never the workspace — to a
#      temporary directory and tests there, where no `go.work` and no `packages/<name>` exist. A service
#      that imports a shared module the way `guidance.py` tells it to cannot build in that copy, and
#      Gremlins scores the build failure as KILLED because `go test` exits 1 for a failed build and a failed
#      test alike: every mutant in the importing package "killed", 100% efficacy, exit 0, with a test that
#      could not fail. The script stages the service beside the workspace modules it imports, with an
#      absolute `replace` for each, and runs with GOWORK=off.
#   2. Gremlins passes two runs the Spring backend's `failWhenNoMutations` would fail: a module with nothing
#      to mutate ("No results to report.", exit 0), and a run whose mutants timed out — a timed-out mutant is
#      left out of the score, and at the default coefficient half the skeleton's were. The script fails both.
#
# It carries two more things, both verified against 0.6.0 on 2026-09-21. It copies the report out of the
# staging tree before deleting it, so the target leaves evidence rather than a scrollback. And it takes
# `--since <ref>`, scoping the run to the production files that differ from that ref by generating the
# complement of exclusions — because Gremlins' own `--diff` is unusable from a module in a subdirectory: it
# resolves changed paths against the repository root, matches them against paths within the module, finds no
# overlap, and reports every mutant SKIPPED and the run successful. That is the shape of failure this backend
# keeps producing, so it is named here rather than discovered again.
GO_MUTATION_SCRIPT = "scripts/go-mutation.py"


# Emitted above the `mutation:` target so the next person to read a score, or a red run, knows what was run
# and where the gate is before trusting either. Make comments do not match the `help` grep, so this stays out
# of `make help`. `__APP__/<file>` is rewritten to the project's own Go services by `mutation_notes` — here the gate's
# yaml and the report the run leaves.
GO_MUTATION_NOTE = """\
# Wired up: Gremlins, pinned to a release and run through `go run` by `scripts/go-mutation.py`, so it is
# never a dependency of the module it mutates. It needs Go 1.25 or newer; an older `go` with the default
# GOTOOLCHAIN=auto downloads one for the run. It replaced go-mutesting, whose 2019 package loader crashed on
# any package importing a module outside the standard library — that is, on every adapter — so the old
# target never reached the tests.
#
# The script stages the service beside the workspace modules it imports before Gremlins runs. Gremlins
# copies only the module it mutates to a temporary directory — no `go.work` above it, no `packages/<name>`
# beside it — and scores the build failure that follows as a kill, because `go test` exits 1 for a failed
# build and a failed test alike: run naked on a service that imports shared code it reported every such
# mutant killed, 100% efficacy and a green target, with tests that could not fail. The staged copy gets a
# `require` and an absolute `replace` per imported module and runs with GOWORK=off. The shared module is
# built there and never mutated; run this against it as a service of its own if its rules need a gate.
#
# The report lands at `__APP__/gremlins.json`, copied out of that staging tree before it is deleted, and is
# ignored by git: it is one run on one machine, and the next run replaces it. It is written whether the run
# passed or failed, because a red run's report is the one worth reading.
#
# `make mutation SINCE=<branch-or-commit>` scopes the run to the production files that differ from that ref
# and leaves the unscoped target as the full sweep. That is the difference between a stage priced per
# repository and one priced per change: every mutant costs a run of this module's suite, so an unscoped run
# re-proves every file that shipped weeks ago at full price, and a stage that expensive gets routed around
# rather than read. The scope is computed from git before staging, not handed to Gremlins' own `--diff`:
# `--diff` resolves changed paths against the repository root and matches them against paths within the
# module, so from a service directory it skips every mutant and reports success having mutated nothing. Gremlins has no
# include list either, so a scope is a complement of exclusions, generated per run — and since
# `--exclude-files` replaces the yaml's list rather than adding to it, the script reads that list and passes
# it back rather than dropping the exclusions below.
#
# The gate is in `__APP__/.gremlins.yaml`, not on this line: a run with a surviving mutant fails. The
# value there is 99.99 and it lives in a file for two reasons the file records — in Gremlins 0.6.0 the
# `--threshold-efficacy` flag and the GREMLINS_* environment variables are read as strings and silently
# gate nothing, and a threshold of 100 fails a perfect run because the comparison is `<=`. A recipe that
# grows a `--threshold` flag here gates nothing; change the file.
#
# The scope is that file's `integration: true` — Gremlins' word for running the whole module's tests against
# every mutant and gathering coverage across packages, so domain code that only an adapter's tests reach is
# covered and mutated rather than reported "not covered". It is not Go's `-tags=integration`: no run here
# sets that tag, so a test behind it is `make test-integration`'s, and a store adapter is mutated only as far
# as its in-process tests reach. Only mutants a test reaches are run — "not covered" is reported, never
# failed — so this fails on a weak test and not on a missing one; `make test`'s coverage gate
# (`scripts/go-coverage.py`) is where the missing one fails.
#
# Two runs Gremlins passes are red here, for the reason `failWhenNoMutations` is true in the Spring
# service's pom — a silent pass on a target no gate runs is worse than a red one. A run that found nothing
# to mutate ("No results to report.", exit 0) exits 1. And a timed-out mutant, which Gremlins leaves out of
# the score, fails the run: the fix is `timeout-coefficient` in the yaml, not a lower threshold.
#
# A survivor is a test to write or an equivalent mutant. Gremlins excludes files, not mutants, so an
# equivalent mutant means lowering the threshold deliberately, named in the commit that lowers it. No gate
# in this repository runs this target (docs/backend-obligations.md section 2); the factory's own suite runs
# it once, on a service importing a workspace module, to hold the staging to what this note says.
# `/mutation` runs it after an accepted slice and classifies what it reports.
"""


# Every Go module `gofmt` covers, named once and read by `lint` and `format` alike, so the two cannot drift. A
# project whose gate checked two directories while its formatter rewrote one had a `make format` that exited 0
# and left the files `make lint` was about to fail — twice, and diagnosed as delegate negligence both times,
# because formatting drift only ever surfaces downstream of the delegate that caused it.
GO_MODULES = """
# The Go modules `gofmt` formats and `make lint` checks, once, so the two never cover different paths. A Go
# module added under packages/ belongs on this line; both targets follow.
GO_MODULES := {paths}
"""



def go_modules(paths: list[str]) -> str:
    """The `GO_MODULES` definition for the Makefile, naming every Go service's module."""
    return GO_MODULES.format(paths=" ".join(paths))


# Said in `commands/mutation.md` and only where a Go service exists, because `SINCE` is the Go target's: the
# skill teaches diff-scoped runs as the posture at this gate and the other backends reach for their own tool's
# way of doing it. Without this line the scoped run is a flag in a Makefile nobody reading the command knows to
# pass, and the unscoped run is the one that gets skipped for costing an hour.
GO_MUTATION_SCOPING = """
`make mutation SINCE=<review-base>` scopes the Go run to the production files that differ from that ref;
without `SINCE` it mutates the whole module, which is a sweep rather than a check on this change. Either way
the run leaves its report at `<service>/gremlins.json` — read that, not the scrollback.
"""

FAMILY_ANSWERS: dict[protocol.Member[Any], object] = {
    protocol.PIN_FILES: {},  # `go.mod`'s own `go` directive pins the toolchain
    protocol.MAKEFILE_VARIABLES: go_modules,
    protocol.RENOVATE_RULES: RenovateRules(
        ("gomod",), ("go", ("gomod",), "the Go modules, and the checksums that come with them"), None
    ),
}
ANSWERS: dict[protocol.Member[Any], object] = {
    # A binary built by ko needs no start command written beside it.
    protocol.PROCFILE: None,
    protocol.OPT_IN_FLAG_TRANSPORTS: frozenset(),
    # `coverage.out` is what `make test` writes beside the service; `gremlins.json` is what
    # `make mutation` now copies out of its staging tree, for the same reason and with the same
    # lifetime — a report of one run on one machine, read once and regenerated by the next run.
    protocol.GITIGNORE: "coverage.out\ngremlins.json\n",
    protocol.AGENT_PERMISSIONS: ["go test *", "go vet *", "gofmt *"],
    protocol.GATE_DESCRIPTION: (
        "gofmt, `go vet`, `go tool staticcheck`, and `go test -coverpkg=./...` held to a minimum by "
        "`scripts/go-coverage.py`"
    ),
    protocol.EVENT_MODEL_PATHS: lambda project_name, service: {
        "events": f"{service}/domain/<context>/events.go",
        "domain": f"{service}/domain/<context>/decider.go",
        "usecase": f"{service}/application/<context>/usecase.go",
        "test": f"{service}/domain/<context>/<slice>_test.go (testing)",
    },
    protocol.MUTATION_TOOL: "Gremlins",
    protocol.MUTATION_NOTE: GO_MUTATION_NOTE,
    protocol.MUTATION_SCOPING: GO_MUTATION_SCOPING,
}
