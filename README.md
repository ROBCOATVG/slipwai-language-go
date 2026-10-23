# slipwai-language-go
slipwai 2.0 language addon: slipwai-language-go

## Service write model

This binding answers the keel's phase 15.6 service-write-model protocol: `language.json` offers the
`persistence` axis (`memory`, `sqlite`, `postgres`) and the `write-model` axis (`events`, `state`), and the
backend answers `persistence_directory` and an `event_model_paths` that names the `repository` port.

`--write-model events` keeps the event store: the log port, its adapters and shared contract, the
projections and their checkpoints, and the Postgres migrations for the log.

`--write-model state` is given a versioned state repository instead (`slipwai_language_go/go_state.py`):
`application/ports/repository` (`Load`, `Save` at an expected version, `Head` for `/ready`), an in-memory
adapter always, a SQLite or Postgres adapter for the store chosen, one contract suite in
`repositorycontract` that all of them run, and on Postgres `migrations/001_states.sql`. A missing row is
`NoState`; a stale save is a `VersionConflict` value, not an error. Each save is one compare-and-swap
statement, and `make test-integration` races two independent Postgres pools at one id to prove exactly
one winner. The standard profile, which keeps current state without asking the persistence axis, is
given the in-memory repository.

## Seed door

On the event-sourced rung with Postgres, `make seed-<service> FILE=<json>` runs `cmd/seed`, which appends
the events a slice's `try-it.json` gives through the event-store port, at each stream's current version,
as the `systems/seed-door` actor. An event already on its stream with the same stream, type and data is
skipped, so a replay records nothing twice; with no `DATABASE_URL` it says so and exits 2. It is a
process with the store's credentials, never an HTTP route. On the state-stored rung the same target
refuses with exit 2, because there is no log to append to.

`SLIPWAI_STATE_NATIVE=1 DATABASE_URL=... python -m unittest discover -s tests -p test_state_skeleton.py -v`
generates both rungs on all three stores, runs each one's `make verify`, and runs the Postgres contracts.
Ordinary conformance needs no database or Go toolchain.
