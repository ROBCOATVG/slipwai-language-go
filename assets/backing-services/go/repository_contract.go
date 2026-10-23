// Package repositorycontract holds one contract, run against every state repository adapter.
//
// The infrastructure-free adapters run it in `make test`; Postgres runs it in
// `make test-integration`. Two adapters that pass different tests are two different ports wearing
// one name, and the day they diverge is the day a slice that worked on the fake stops working in
// production — so no adapter gets its own version of the business rule.
//
// Every case works under a freshly generated id and asserts only about that id, because a real
// store's table is shared with every earlier run and nothing here deletes from it.
package repositorycontract

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"math"
	"reflect"
	"sync"
	"testing"
	"time"

	"example.com/delivery-starter/application/ports/repository"
)

// NewRepository builds the adapter under test. Called once per case.
type NewRepository func(t *testing.T) repository.Repository

// FreshID is an id no earlier run can have written.
func FreshID(t *testing.T) string {
	t.Helper()
	buffer := make([]byte, 8)
	if _, err := rand.Read(buffer); err != nil {
		t.Fatalf("random id: %v", err)
	}
	return "contract-" + hex.EncodeToString(buffer)
}

// Run holds an adapter to the port's contract.
func Run(t *testing.T, newRepository NewRepository) {
	t.Helper()
	ctx := context.Background()

	t.Run("reads an unknown row as absent", func(t *testing.T) {
		store := newRepository(t)
		if _, found, err := store.Load(ctx, FreshID(t)); err != nil || found {
			t.Fatalf("expected no row and no error, got found=%v err=%v", found, err)
		}
	})

	t.Run("creates at NoState and updates only at the version it read", func(t *testing.T) {
		store, id := newRepository(t), FreshID(t)
		mustSave(t, store, id, repository.NoState, map[string]any{"status": "draft"}, repository.Saved(0))
		mustSave(t, store, id, 0, map[string]any{"status": "confirmed"}, repository.Saved(1))
		want := repository.Versioned{ID: id, Version: 1, State: map[string]any{"status": "confirmed"}}
		if got := mustLoad(t, store, id); !reflect.DeepEqual(got, want) {
			t.Fatalf("expected %+v, got %+v", want, got)
		}
	})

	t.Run("refuses a stale decision and leaves the winning state alone", func(t *testing.T) {
		store, id := newRepository(t), FreshID(t)
		mustSave(t, store, id, repository.NoState, map[string]any{"status": "draft"}, repository.Saved(0))
		mustSave(t, store, id, 0, map[string]any{"status": "confirmed"}, repository.Saved(1))
		mustSave(t, store, id, 0, map[string]any{"status": "cancelled"}, repository.VersionConflict(1))
		if got := mustLoad(t, store, id).State["status"]; got != "confirmed" {
			t.Fatalf("a refused save changed the row to %v", got)
		}
	})

	t.Run("refuses a second creation of one id", func(t *testing.T) {
		store, id := newRepository(t), FreshID(t)
		mustSave(t, store, id, repository.NoState, map[string]any{"writer": "first"}, repository.Saved(0))
		mustSave(t, store, id, repository.NoState, map[string]any{"writer": "second"}, repository.VersionConflict(0))
	})

	t.Run("cannot manufacture a missing row from a noninitial expected version", func(t *testing.T) {
		store, id := newRepository(t), FreshID(t)
		mustSave(t, store, id, 0, map[string]any{"status": "confirmed"}, repository.VersionConflict(repository.NoState))
		if _, found, err := store.Load(ctx, id); err != nil || found {
			t.Fatalf("a refused save created a row: found=%v err=%v", found, err)
		}
	})

	t.Run("gives exactly one of two same-version decisions the win", func(t *testing.T) {
		store, id := newRepository(t), FreshID(t)
		mustSave(t, store, id, repository.NoState, map[string]any{"writer": "original"}, repository.Saved(0))
		results := Race(t, func(writer string) (repository.SaveResult, error) {
			return store.Save(ctx, id, 0, map[string]any{"writer": writer})
		})
		RequireOneWinner(t, results, 1)
		if got := mustLoad(t, store, id).Version; got != 1 {
			t.Fatalf("expected the row at version 1, got %d", got)
		}
	})

	t.Run("refuses values that would change when stored as JSON", func(t *testing.T) {
		store, id := newRepository(t), FreshID(t)
		for name, state := range map[string]map[string]any{
			"nil state":       nil,
			"not a number":    {"bad": math.NaN()},
			"an infinity":     {"bad": math.Inf(1)},
			"a time":          {"bad": time.Unix(0, 0)},
			"a struct":        {"bad": struct{ Name string }{"x"}},
			"nested deep":     {"items": []any{map[string]any{"at": time.Unix(0, 0)}}},
			"an inexact int":  {"bad": int64(1<<53 + 1)},
			"an inexact uint": {"bad": uint64(1<<53 + 1)},
		} {
			if _, err := store.Save(ctx, id, repository.NoState, state); !errors.Is(err, repository.ErrInvalidWrite) {
				t.Fatalf("%s: expected ErrInvalidWrite, got %v", name, err)
			}
		}
		if _, err := store.Save(ctx, " ", repository.NoState, map[string]any{}); !errors.Is(err, repository.ErrInvalidWrite) {
			t.Fatalf("a blank id: expected ErrInvalidWrite, got %v", err)
		}
		if _, err := store.Save(ctx, id, -2, map[string]any{}); !errors.Is(err, repository.ErrInvalidWrite) {
			t.Fatalf("a version below NoState: expected ErrInvalidWrite, got %v", err)
		}
		if _, found, err := store.Load(ctx, id); err != nil || found {
			t.Fatalf("a refused write created a row: found=%v err=%v", found, err)
		}
	})

	t.Run("hands back what JSON holds, the same on every adapter", func(t *testing.T) {
		store, id := newRepository(t), FreshID(t)
		state := map[string]any{
			"count": 3, "small": int32(2), "ratio": float32(0.5), "big": uint(7), "wide": int64(9),
			"ok": true, "none": nil, "tags": []any{"a", "b"},
		}
		mustSave(t, store, id, repository.NoState, state, repository.Saved(0))
		want := map[string]any{
			"count": 3.0, "small": 2.0, "ratio": 0.5, "big": 7.0, "wide": 9.0,
			"ok": true, "none": nil, "tags": []any{"a", "b"},
		}
		if got := mustLoad(t, store, id).State; !reflect.DeepEqual(got, want) {
			t.Fatalf("expected %#v, got %#v", want, got)
		}
	})

	t.Run("does not share mutable state with the caller", func(t *testing.T) {
		store, id := newRepository(t), FreshID(t)
		state := map[string]any{"nested": map[string]any{"count": 1}}
		mustSave(t, store, id, repository.NoState, state, repository.Saved(0))
		state["nested"].(map[string]any)["count"] = 10
		loaded := mustLoad(t, store, id)
		loaded.State["nested"].(map[string]any)["count"] = 20
		if got := mustLoad(t, store, id).State["nested"].(map[string]any)["count"]; got != 1.0 {
			t.Fatalf("the stored row changed with a caller's map: %v", got)
		}
	})

	t.Run("counts its rows for readiness", func(t *testing.T) {
		store := newRepository(t)
		before, err := store.Head(ctx)
		if err != nil {
			t.Fatalf("head: %v", err)
		}
		mustSave(t, store, FreshID(t), repository.NoState, map[string]any{}, repository.Saved(0))
		after, err := store.Head(ctx)
		if err != nil {
			t.Fatalf("head: %v", err)
		}
		if after < before+1 {
			t.Fatalf("expected the head to grow past %d, got %d", before, after)
		}
	})
}

// Race runs two saves at once, one per writer, and returns both results. Exported so an adapter's own
// suite can race two independent connections with the same assertion the contract makes.
func Race(t *testing.T, save func(writer string) (repository.SaveResult, error)) []repository.SaveResult {
	t.Helper()
	writers := []string{"one", "two"}
	results := make([]repository.SaveResult, len(writers))
	failures := make([]error, len(writers))
	var group sync.WaitGroup
	start := make(chan struct{})
	for index, writer := range writers {
		group.Add(1)
		go func() {
			defer group.Done()
			<-start
			results[index], failures[index] = save(writer)
		}()
	}
	close(start)
	group.Wait()
	for _, err := range failures {
		if err != nil {
			t.Fatalf("a racing save failed rather than conflicting: %v", err)
		}
	}
	return results
}

// RequireOneWinner holds two racing results to the rule: exactly one saved, and the other was told
// the version the winner left the row at.
func RequireOneWinner(t *testing.T, results []repository.SaveResult, winnerVersion int64) {
	t.Helper()
	saved, refused := 0, 0
	for _, result := range results {
		switch result {
		case repository.Saved(winnerVersion):
			saved++
		case repository.VersionConflict(winnerVersion):
			refused++
		}
	}
	if saved != 1 || refused != 1 {
		t.Fatalf("expected one save and one conflict at version %d, got %+v", winnerVersion, results)
	}
}

func mustSave(
	t *testing.T,
	store repository.Repository,
	id string,
	expected int64,
	state map[string]any,
	want repository.SaveResult,
) {
	t.Helper()
	got, err := store.Save(context.Background(), id, expected, state)
	if err != nil {
		t.Fatalf("save %s at %d: %v", id, expected, err)
	}
	if got != want {
		t.Fatalf("save %s at %d: expected %+v, got %+v", id, expected, want, got)
	}
}

func mustLoad(t *testing.T, store repository.Repository, id string) repository.Versioned {
	t.Helper()
	got, found, err := store.Load(context.Background(), id)
	if err != nil || !found {
		t.Fatalf("load %s: found=%v err=%v", id, found, err)
	}
	return got
}
