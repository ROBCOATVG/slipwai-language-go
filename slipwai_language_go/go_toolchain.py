"""Go's toolchain: how a service in this language installs, starts, checks and formats itself.

These are the language's answers to the toolchain members of the backend protocol (slipwai's `registry` module,
whose shapes are fixed in its backend-protocol contract). `BACKEND` is
what the `go` backend answers and `FAMILY` what the family does. `go.py`'s `LANGUAGE` takes both in, and its
verify script runs the same gate lines as the Makefile, named once here. A command spells a service's path
`APP`, which `tooling.for_app` stamps per service.
"""
from __future__ import annotations

from typing import Any

from slipwai import registry as protocol
from slipwai.backends import APP, Tooling
from slipwai.tooling import for_app

from .go_project import GO_MUTATION_SCRIPT

# The coverage gate `make test` holds a Go service to, and the script that is the gate. The test line writes
# a profile with `-coverpkg=./...`, because without it Go credits a package only with its own tests and the
# domain package — tested through every adapter, holding no `_test.go` of its own — reads 0%; the script
# reads the profile back, leaves entry points and integration-tagged suites out of the count (its docstring
# says why), and fails below the minimum. Spelled as one command and one gate line so the Makefile recipe
# and the verify script in `go.py` run the same thing.
GO_COVERAGE_SCRIPT = "scripts/go-coverage.py"
GO_TEST_COMMAND = "go test -coverpkg=./... -coverprofile=coverage.out ./..."
GO_TEST = f"cd {APP} && {GO_TEST_COMMAND}"
# The skeleton itself measures 78-83% in this gate's scope on every variant — memory, SQLite and Postgres
# stores, with and without a transport and an identity provider (2026-09-09) — so 70 is below what a fresh
# service starts at by a margin a first slice can spend, not a number the first test has to chase. It is on
# the Makefile line so a project raises it there as the suite earns it.
GO_COVERAGE_MINIMUM = 70
GO_COVERAGE_GATE = f"python3 {GO_COVERAGE_SCRIPT} {APP} {GO_COVERAGE_MINIMUM}"

# Build `covdata` before anything races to exec it, and run this ahead of every `go test -cover` this
# backend writes — the Makefile's `test` target through `native_commands`, and the verify script in `go.py`.
#
# Go 1.24 and later stopped shipping the toolchain's own commands prebuilt and build them on demand into
# the build cache instead. `go test -cover` then execs the resulting `covdata` once per package that has no
# test files — several at a time, moments after the same `go` process wrote that file — and on a cold cache
# one of those execs loses the race to the write that created it and dies with `text file busy`. That fails
# the gate while naming a package with no tests in it, and nothing about the project is wrong. Every CI
# runner starts cold, which is where it bites. A separate process that has exited before the parallel run
# begins leaves that run a finished binary and nothing to write.
#
# `percent` over a directory holding no coverage data is the cheapest invocation that exits zero, and it is
# spelled with no `$` so that one line serves a Makefile recipe and a `/bin/sh` script unchanged. `|| true`
# is deliberate: a warm-up must never become the thing that fails a gate, so a later toolchain that spells
# this differently leaves a project where it stands today rather than breaking it.
GO_COVDATA_READY = "go tool covdata percent -i=. >/dev/null 2>&1 || true"

# The third analyser in this backend's lint gate, after `gofmt` and `go vet`. `go vet` is deliberately
# narrow — it reports what is almost certainly a mistake and nothing arguable — which leaves a large class
# of real findings nobody sees: a value assigned and never read, a `defer` inside a loop, an error compared
# with `==` where the chain has to be unwrapped, an `errors.New` built with a format string. staticcheck's
# SA checks are those, and they are the ones a Go reviewer would raise by hand.
#
# `go tool` and not an installed binary: the module's `tool` directive pins it (`modules/base/go.mod`), so
# `go mod download` fetches it with every other dependency and the gate needs no second install step on a
# laptop, in the Compose container or in CI — and the version moves through `make locks` like the rest.
GO_STATICCHECK = "go tool staticcheck ./..."

TOOLING: Tooling = {
    "install": f"cd {APP} && go mod download",
    "migrate": f"cd {APP} && go run ./cmd/migrate",
    "integration": f"cd {APP} && go test -tags=integration ./...",
    "ci_image": "golang:1.26-bookworm",
    "ci_install": f"cd {APP} && go mod download",
    "container_setup": "",
    "container_environment": {},
}

# The eight targets every service answers (`native_commands.TARGETS`), in that order.
NATIVE_COMMANDS = {
    "install": f"cd {APP} && go mod download",
    "typecheck": f"cd {APP} && go test -run '^$$' ./...",
    # Three analysers, widening as they go: the formatter, the compiler's own narrow vet, and
    # staticcheck for what vet deliberately leaves alone (`GO_STATICCHECK` says which).
    "lint": f"test -z \"$$(gofmt -l $(GO_MODULES))\"\n\tcd {APP} && go vet ./...\n\tcd {APP} && {GO_STATICCHECK}",
    # The suite, then the coverage gate over the profile it wrote: `-coverpkg=./...` so a package
    # is credited with every test that reaches it, and the script's minimum on the line (above).
    "test": f"{GO_COVDATA_READY}\n\t{GO_TEST}\n\t{GO_COVERAGE_GATE}",
    "integration": f"cd {APP} && go test -tags=integration ./...",
    "adversarial": f"cd {APP} && go test -run Adversarial ./...",
    "audit": f"@command -v govulncheck >/dev/null 2>&1 || {{ echo 'install govulncheck to run dependency audit' >&2; exit 2; }}; cd {APP} && govulncheck ./...",
    # Gremlins through the wrapper, which stages the service beside the workspace modules it imports
    # and fails a run Gremlins would pass on nothing. The gate is the service's `.gremlins.yaml`:
    # Gremlins 0.6.0 ignores a threshold given as a flag, so none is given here (see `go_project.py`).
    #
    # `make mutation SINCE=main` scopes the run to what differs from that ref, which is the whole
    # module's price against one change's. Written as a conditional rather than read from a variable
    # the Makefile defines, because an undefined `SINCE` has to mean the full sweep and `$(if ...)`
    # says that in the one place the flag is built — nothing to prune, nothing to leave dangling.
    "mutation": f"python3 {GO_MUTATION_SCRIPT} {APP} $(if $(SINCE),--since $(SINCE))",
}


def native_commands(path: str, verify: str) -> dict[str, str]:
    """One service's eight commands, spelled for its own directory."""
    return {target: for_app(command, path, verify) for target, command in NATIVE_COMMANDS.items()}


def dev_command(qualifier: str, path: str, verify: str) -> str:
    """How one service starts in the foreground, pretty-logged."""
    return f"cd {path} && LOG_FORMAT=pretty go run ./cmd/serve"


def event_store_directory(path: str) -> str:
    """Where one service's driven adapters live, for prose that has to point at them."""
    return f"{path}/adapters/driven/"


BACKEND: dict[protocol.Member[Any], object] = {
    protocol.TOOLING: TOOLING,
    protocol.FEATURE_TOOLING: {},
    # The gate scripts a Go service runs through; `go.py` writes them, `go_project.py` says why.
    protocol.EXECUTABLES: frozenset({GO_COVERAGE_SCRIPT, GO_MUTATION_SCRIPT}),
    protocol.DEV_COMMAND: dev_command,
    protocol.COMPOSE_CACHES: ("/root/go", "/root/.cache"),
    protocol.EVENT_STORE_DIRECTORY: event_store_directory,
    protocol.NATIVE_COMMANDS: native_commands,
}
# Over `$(GO_MODULES)`, the one list `lint` reads too (`makefile.py`), so the two can never cover different
# paths: a project whose gate checked two directories while its formatter rewrote one had a `make format`
# that exited 0 and left the files `make lint` was about to fail.
FAMILY: dict[protocol.Member[Any], object] = {protocol.FORMATTER: "gofmt -w $(GO_MODULES)"}
