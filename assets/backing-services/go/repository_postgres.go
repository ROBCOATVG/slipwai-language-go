// Package repositorypostgres holds the Postgres state repository adapter — the only package that
// knows the state table is SQL.
//
// Concurrency is one statement per save, and the statement is the compare-and-swap:
//
//  1. A creation is an INSERT that does nothing when the id already exists. Two concurrent
//     creations both reach the primary key; one inserts, the other waits for it to commit and then
//     inserts nothing, and is told the version the winner wrote.
//  2. An update is an UPDATE ... WHERE version = expected that increments the version. Under READ
//     COMMITTED a second updater at the same version waits on the first's row lock, re-reads the row
//     once the first commits, finds the version moved, and matches nothing.
//
// Neither needs a transaction of its own or a stronger isolation level: the row is the boundary, and
// Postgres already serialises writers to one row. `make test-integration` proves both races with two
// independent connection pools.
//
// The table is created by migrations/001_states.sql, applied by `make migrate`.
package repositorypostgres

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"example.com/delivery-starter/application/ports/repository"
)

const (
	insertState = `INSERT INTO states (id, version, state) VALUES ($1, 0, $2::jsonb)
    ON CONFLICT (id) DO NOTHING RETURNING version`
	updateState = `UPDATE states SET state = $3::jsonb, version = version + 1
    WHERE id = $1 AND version = $2 RETURNING version`
	// state::text so what crosses this boundary is the JSON text every adapter decodes the same way,
	// and the driver's own jsonb mapping is not a thing to know about here.
	selectState   = `SELECT version, state::text FROM states WHERE id = $1`
	selectVersion = `SELECT version FROM states WHERE id = $1`
	countStates   = `SELECT count(*) FROM states`
)

// Repository is the Postgres adapter.
type Repository struct {
	pool *pgxpool.Pool
}

// New returns a repository over pool. It opens nothing: pgxpool connects lazily, so a database that
// cannot be reached shows up as /ready answering 503.
func New(pool *pgxpool.Pool) *Repository {
	return &Repository{pool: pool}
}

// Load returns the current row for id.
func (r *Repository) Load(ctx context.Context, id string) (repository.Versioned, bool, error) {
	var version int64
	var stored string
	err := r.pool.QueryRow(ctx, selectState, id).Scan(&version, &stored)
	if errors.Is(err, pgx.ErrNoRows) {
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
	var row pgx.Row
	if expectedVersion == repository.NoState {
		row = r.pool.QueryRow(ctx, insertState, id, string(encoded))
	} else {
		row = r.pool.QueryRow(ctx, updateState, id, expectedVersion, string(encoded))
	}
	var version int64
	err = row.Scan(&version)
	if err == nil {
		return repository.Saved(version), nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return repository.SaveResult{}, fmt.Errorf("save %s: %w", id, err)
	}
	// Nothing was written, so the row is not where the caller thought: say where it is. Read after
	// the losing statement, so it sees the winner's commit — the losing statement waited for it.
	actual := int64(repository.NoState)
	err = r.pool.QueryRow(ctx, selectVersion, id).Scan(&actual)
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return repository.SaveResult{}, fmt.Errorf("read the version of %s: %w", id, err)
	}
	return repository.VersionConflict(actual), nil
}

// Head is the number of rows held.
func (r *Repository) Head(ctx context.Context) (int64, error) {
	var count int64
	if err := r.pool.QueryRow(ctx, countStates).Scan(&count); err != nil {
		return 0, fmt.Errorf("count states: %w", err)
	}
	return count, nil
}
