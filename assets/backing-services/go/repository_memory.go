// Package repositorymemory holds the in-memory state repository adapter.
//
// For a quickstart with no infrastructure, and for tests that do not need to prove concurrency.
// `make verify` runs the shared contract suite against this one, which is why the repository gate
// needs no Docker.
//
// It satisfies the port's contract, but understand what it cannot do: it serialises every call
// behind one mutex, so two writers at one version never genuinely race here. The rule they are held
// to is the same — exactly one wins — and the contract checks it, but the guarantee that matters in
// production lives in a real store's single compare-and-swap statement, and `make test-integration`
// is where that is proved with two independent connections. Ship on Postgres, demo on memory.
//
// It keeps each row as the JSON the port encodes, not as the caller's map, so what it hands back is
// exactly what a SQL column would — and a caller that mutates a map after saving it changes nothing
// here. Data is lost when the process ends. Never production.
package repositorymemory

import (
	"context"
	"sync"

	"example.com/delivery-starter/application/ports/repository"
)

type row struct {
	version int64
	state   []byte
}

// Repository is the in-memory adapter.
type Repository struct {
	mutex sync.Mutex
	rows  map[string]row
}

// New returns an empty repository.
func New() *Repository {
	return &Repository{rows: map[string]row{}}
}

// Load returns the current row for id, decoded afresh.
func (r *Repository) Load(_ context.Context, id string) (repository.Versioned, bool, error) {
	r.mutex.Lock()
	defer r.mutex.Unlock()
	current, ok := r.rows[id]
	if !ok {
		return repository.Versioned{}, false, nil
	}
	state, err := repository.Decode(current.state)
	if err != nil {
		return repository.Versioned{}, false, err
	}
	return repository.Versioned{ID: id, Version: current.version, State: state}, true, nil
}

// Save writes state at the next version, if the row is still at expectedVersion.
func (r *Repository) Save(
	_ context.Context,
	id string,
	expectedVersion int64,
	state map[string]any,
) (repository.SaveResult, error) {
	encoded, err := repository.Encode(id, expectedVersion, state)
	if err != nil {
		return repository.SaveResult{}, err
	}
	r.mutex.Lock()
	defer r.mutex.Unlock()
	actual := int64(repository.NoState)
	if current, ok := r.rows[id]; ok {
		actual = current.version
	}
	if actual != expectedVersion {
		return repository.VersionConflict(actual), nil
	}
	r.rows[id] = row{version: actual + 1, state: encoded}
	return repository.Saved(actual + 1), nil
}

// Head is the number of rows held.
func (r *Repository) Head(context.Context) (int64, error) {
	r.mutex.Lock()
	defer r.mutex.Unlock()
	return int64(len(r.rows)), nil
}
