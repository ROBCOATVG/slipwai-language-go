# Changelog

No releases yet. Release notes are recorded here newest first, one entry per released version; the entry being
written is `changelog.d/`.

## 1.1.1 — PATCH

**A generated Go service is on Go 1.27, and its gate passes on a machine that has it.** Go 1.27 writes export
data the pinned staticcheck could not read, so `make lint` failed every Go project on a machine with the newest
Go — `export data version 5 is greater than maximum supported version 4` — while passing on 1.26. staticcheck
moves to 2026.2.2 (`honnef.co/go/tools` v0.8.2) with the `golang.org/x/tools` it needs, the modules' `go`
directive to 1.27.0 and the CI image to `golang:1.27-bookworm`. A machine with an older `go` and the default
`GOTOOLCHAIN=auto` downloads 1.27 for the run.

**Catch-up:** `slipwai language upgrade go`, then `slipwai migrate`; a service's `go.mod` takes the new
directive and tool pins.

## 1.1.0 — MINOR

**A Go service answered `--write-model state` is given a versioned state repository instead of an event log.**
The port is `application/ports/repository` — `Load`, `Save` at an expected version with a conflict returned as
a value, and `Head` for `/ready` — with an in-memory adapter always, a SQLite or Postgres adapter for the store
chosen, one contract suite all of them run, and on Postgres a `states` table whose version column is the
optimistic concurrency, compared and incremented in one statement. `make test-integration` races two
independent Postgres pools at one id and requires exactly one winner. `cmd/serve` opens the repository and hands
it to `/ready`; `./init --persistence memory` prunes the durable adapter and its migration as it does the log's.
The standard profile is given the in-memory repository. `language.json` answers the axes by the names the core
now uses, `persistence` and `write-model`, and the backend answers `persistence_directory` and a `repository`
path in `event_model_paths`. `--write-model events` projects are generated as before.

**Catch-up:** none for a project on `--write-model events`. A project generated on the state rung before this
release has no store at all; regenerate the service, or copy the repository files from a fresh one.

**A slice's story may be given its inputs, through the service's own seed door.** A service on the durable
store gains `cmd/seed`, run by `make seed-<service> FILE=<json>`: it appends the events a slice's
`try-it.json` *gives* — the ones an unbuilt upstream slice would have written — through the event-store port,
at the stream's current version, as a system actor, with an identity hashed from stream, type and data so a
replay records nothing twice. With no `DATABASE_URL` it says so and exits 2. Never an HTTP route: the door
is a process with the store's credentials. slipwai's Try it runs it before a story's first step. On the
state-stored rung the target refuses with exit 2 and the reason, because there is no log to append to.

**Catch-up:** `slipwai language upgrade go`, then `slipwai migrate`; the service gains `cmd/seed` and the
Makefile target. Until then a story's `given` is validated by `check-try` and not applied, and Try it says
*no seed door yet*.

## 1.0.0

**Go is now a language package of its own.** The Go backend that was built into slipwai — its service
skeleton, event-store adapters, HTTP transport, identity wiring, Gremlins mutation gate, module variants and
toolchain — lives here, with the history it had there, and slipwai loads it from its language directory
(`$SLIPWAI_LANGUAGES`, or `~/.slipwai/languages`). The projects it generates are byte for byte those slipwai
generated with Go built in. It declares the catalog schema it loads on, `core >=9.0,<10`, in `language.json`.

