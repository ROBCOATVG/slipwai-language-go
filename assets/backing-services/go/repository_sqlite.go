// Package repositorysqlite holds the SQLite state repository adapter — one versioned row per id in
// one file, with no container to run.
//
// Chosen when durability matters and infrastructure does not: a single-process service, a CLI, or a
// demo that must survive a restart.
//
// Understand the one thing it cannot do before adopting it: SQLite serialises writers, and this
// adapter holds one connection, so two saves at one version never genuinely race. The rule is the
// same as Postgres' and the contract holds it — each save is one compare-and-swap statement — but if
// the exactly-one-winner guarantee matters to your product, prove it on Postgres, where
// `make test-integration` races two independent connections.
//
// modernc.org/sqlite is a pure-Go translation of SQLite, so this adapter needs no cgo. The schema
// ships with the adapter rather than as a migration, as the event store's does: an embedded database
// is created by the process that opens it. The table is the one migrations/001_states.sql creates on
// Postgres, because two spellings of one schema drift and nothing notices.
package repositorysqlite

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	// Registers the "sqlite" driver with database/sql.
	_ "modernc.org/sqlite"

	"example.com/delivery-starter/application/ports/repository"
)

const schema = `
  CREATE TABLE IF NOT EXISTS states (
    id      TEXT    PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version >= 0),
    state   TEXT    NOT NULL CHECK (json_type(state) = 'object')
  )
`

// Each save is one statement, so the comparison and the write cannot be separated by another writer:
// an insert that does nothing when the id exists, or an update that matches only the version read.
const (
	insertState = `INSERT INTO states (id, version, state) VALUES (?, 0, ?)
    ON CONFLICT (id) DO NOTHING RETURNING version`
	updateState = `UPDATE states SET state = ?, version = version + 1
    WHERE id = ? AND version = ? RETURNING version`
	selectState   = `SELECT version, state FROM states WHERE id = ?`
	selectVersion = `SELECT version FROM states WHERE id = ?`
	countStates   = `SELECT count(*) FROM states`
)

// Repository is the SQLite adapter.
type Repository struct {
	db *sql.DB
}

// Open opens — creating where it must — the database at location. ":memory:" is a database that
// lives as long as the repository does.
func Open(location string) (*Repository, error) {
	db, err := sql.Open("sqlite", location)
	if err != nil {
		return nil, fmt.Errorf("open sqlite at %s: %w", location, err)
	}
	// One connection, deliberately. SQLite serialises writers anyway, and for ":memory:" a second
	// connection would open a second, empty database — which reads as data loss.
	db.SetMaxOpenConns(1)
	for _, statement := range []string{"PRAGMA journal_mode = WAL", schema} {
		if _, err := db.Exec(statement); err != nil {
			db.Close()
			return nil, fmt.Errorf("prepare sqlite at %s: %w", location, err)
		}
	}
	return &Repository{db: db}, nil
}

// Close releases the database.
func (r *Repository) Close() error { return r.db.Close() }

// Load returns the current row for id.
func (r *Repository) Load(ctx context.Context, id string) (repository.Versioned, bool, error) {
	var version int64
	var stored string
	err := r.db.QueryRowContext(ctx, selectState, id).Scan(&version, &stored)
	if errors.Is(err, sql.ErrNoRows) {
		return repository.Versioned{}, false, nil
	}
	if err != nil {
		return repository.Versioned{}, false, fmt.Errorf("load %s: %w", id, err)
	}
	state, err := repository.Decode([]byte(stored))
	if err != nil {
		return repository.Versioned{}, false, err
	}
	return repository.Versioned{ID: id, Version: version, State: state}, true, nil
}

// Save writes state at the next version, if the row is still at expectedVersion.
func (r *Repository) Save(
	ctx context.Context,
	id string,
	expectedVersion int64,
	state map[string]any,
) (repository.SaveResult, error) {
	encoded, err := repository.Encode(id, expectedVersion, state)
	if err != nil {
		return repository.SaveResult{}, err
	}
	var row *sql.Row
	if expectedVersion == repository.NoState {
		row = r.db.QueryRowContext(ctx, insertState, id, string(encoded))
	} else {
		row = r.db.QueryRowContext(ctx, updateState, string(encoded), id, expectedVersion)
	}
	var version int64
	err = row.Scan(&version)
	if err == nil {
		return repository.Saved(version), nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return repository.SaveResult{}, fmt.Errorf("save %s: %w", id, err)
	}
	// Nothing was written, so the row is not where the caller thought: say where it is.
	actual := int64(repository.NoState)
	err = r.db.QueryRowContext(ctx, selectVersion, id).Scan(&actual)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return repository.SaveResult{}, fmt.Errorf("read the version of %s: %w", id, err)
	}
	return repository.VersionConflict(actual), nil
}

// Head is the number of rows held.
func (r *Repository) Head(ctx context.Context) (int64, error) {
	var count int64
	if err := r.db.QueryRowContext(ctx, countStates).Scan(&count); err != nil {
		return 0, fmt.Errorf("count states: %w", err)
	}
	return count, nil
}
