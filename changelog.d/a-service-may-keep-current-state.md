MINOR

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
