// Package repository holds the state repository port: where a service on the state-stored rung keeps
// the current state of each thing it owns, one row per id, and nothing else.
//
// The other rung keeps a log and folds it; this one keeps the fold. Three capabilities, and a store
// that cannot offer all three must not be adopted:
//
//  1. load the current state of one id, with the version it is at
//  2. save a new state for one id, only if it is still at the version the caller decided against
//     (optimistic concurrency, one row at a time)
//  3. answer a cheap question about itself — Head — which is what /ready asks
//
// The version is the whole of the concurrency control. A use case loads, decides, and saves at the
// version it loaded; a second writer that decided against the same version is told it lost, as a
// value, and re-reads and re-decides. Nothing here locks.
//
// Nothing here names Postgres, SQL, or a vendor. Every adapter under adapters/driven implements it,
// and the same contract suite (package repositorycontract) runs against all of them.
//
// What this rung gives up is history: a row says what is true now and not how it came to be, and
// state cannot be turned back into a history it never recorded. An event a slice raises after a
// successful save is a contract with whoever reads it, not the truth this service keeps.
package repository

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"strings"
)

// NoState is the expectedVersion for an id that must not have a row yet, which is how first-write
// races are detected. The first successful save writes version 0.
const NoState = -1

// Versioned is one row as the repository holds it: the id, the version it is at, and the state.
type Versioned struct {
	ID      string
	Version int64
	State   map[string]any
}

// Outcome distinguishes the two ways a save can end.
type Outcome string

const (
	OutcomeSaved           Outcome = "saved"
	OutcomeVersionConflict Outcome = "version-conflict"
)

// SaveResult reports the outcome of a save.
//
// A version conflict is a **value, not an error**, for the reason it is one on the event-sourced
// rung: contention is expected under load, not exceptional, and an error would put ordinary
// concurrency on the path a broken connection takes.
type SaveResult struct {
	Outcome Outcome

	// Version is the row's new version, when the save succeeded.
	Version int64

	// ActualVersion is the version the row is really at, when it did not: NoState where there is
	// no row at all.
	ActualVersion int64
}

// Saved is the result of a save that wrote version.
func Saved(version int64) SaveResult {
	return SaveResult{Outcome: OutcomeSaved, Version: version}
}

// VersionConflict is the result of a save that was refused because the row is at actual.
func VersionConflict(actual int64) SaveResult {
	return SaveResult{Outcome: OutcomeVersionConflict, ActualVersion: actual}
}

// Repository is the port. Every adapter answers it the same way, and the contract proves it.
type Repository interface {
	// Load returns the row for id, and false when there is none. An absent row is not an error:
	// it is the answer a first decision is made against, at NoState.
	Load(ctx context.Context, id string) (Versioned, bool, error)

	// Save writes state for id only if the row is at expectedVersion — NoState for a row that
	// must not exist yet — and reports a conflict as a value otherwise.
	Save(ctx context.Context, id string, expectedVersion int64, state map[string]any) (SaveResult, error)

	// Head is the number of rows held. It is what /ready asks: the cheapest honest question the
	// port already answers, and one that fails exactly when the store cannot be reached.
	Head(ctx context.Context) (int64, error)
}

// ErrInvalidWrite is what every refused write wraps, so a caller can tell a value it should never
// have passed from a store that failed.
var ErrInvalidWrite = errors.New("state repository refused the write")

// Encode checks a write and returns the state as the JSON every adapter stores.
//
// One function for every adapter, so none of them gets its own version of the rule: a value the
// memory fake would keep and Postgres would refuse is a slice that passes its tests and fails in
// production. It is called before anything is touched, so a refused write changes nothing.
//
// Only what JSON can carry unchanged is accepted — nil, booleans, strings, finite numbers, and
// maps and slices of those. A time.Time, a struct, a pointer or a NaN would come back from a SQL
// column as something other than what went in, so each is refused here rather than discovered on
// the next Load. An integer beyond 2^53 is refused for the same reason: encoding/json reads every
// number back as a float64, and that is the largest one a float64 holds exactly.
func Encode(id string, expectedVersion int64, state map[string]any) ([]byte, error) {
	if strings.TrimSpace(id) == "" {
		return nil, fmt.Errorf("%w: an id is required", ErrInvalidWrite)
	}
	if expectedVersion < NoState {
		return nil, fmt.Errorf("%w: expectedVersion must be NoState or a version, not %d",
			ErrInvalidWrite, expectedVersion)
	}
	if state == nil {
		return nil, fmt.Errorf("%w: state must be a JSON object, not nil", ErrInvalidWrite)
	}
	if err := checkJSON(state, "state"); err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidWrite, err)
	}
	encoded, err := json.Marshal(state)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidWrite, err)
	}
	return encoded, nil
}

// Decode reads stored JSON back into state. A fresh value every time, so no caller holds a map the
// repository — or another caller — also holds.
func Decode(stored []byte) (map[string]any, error) {
	var state map[string]any
	if err := json.Unmarshal(stored, &state); err != nil {
		return nil, fmt.Errorf("decode stored state: %w", err)
	}
	if state == nil {
		return nil, errors.New("decode stored state: the stored value is not a JSON object")
	}
	return state, nil
}

// maxExact is 2^53, the largest integer a float64 — which is what encoding/json decodes into —
// holds exactly.
const maxExact = 1 << 53

func checkJSON(value any, path string) error {
	switch typed := value.(type) {
	case nil, bool, string, json.Number:
		return nil
	case float64:
		return checkFloat(typed, path)
	case float32:
		return checkFloat(float64(typed), path)
	case int:
		return checkInteger(int64(typed), path)
	case int8, int16, int32, uint8, uint16:
		return nil
	case int64:
		return checkInteger(typed, path)
	case uint32:
		return nil
	case uint:
		return checkUnsigned(uint64(typed), path)
	case uint64:
		return checkUnsigned(typed, path)
	case map[string]any:
		for key, item := range typed {
			if err := checkJSON(item, path+"."+key); err != nil {
				return err
			}
		}
		return nil
	case []any:
		for index, item := range typed {
			if err := checkJSON(item, fmt.Sprintf("%s[%d]", path, index)); err != nil {
				return err
			}
		}
		return nil
	default:
		return fmt.Errorf("%s is a %T, which is not a JSON value and would not read back as itself", path, value)
	}
}

func checkFloat(value float64, path string) error {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return fmt.Errorf("%s is %v, which JSON cannot carry", path, value)
	}
	return nil
}

func checkInteger(value int64, path string) error {
	if value > maxExact || value < -maxExact {
		return fmt.Errorf("%s is %d, which would not read back exactly", path, value)
	}
	return nil
}

func checkUnsigned(value uint64, path string) error {
	if value > maxExact {
		return fmt.Errorf("%s is %d, which would not read back exactly", path, value)
	}
	return nil
}
