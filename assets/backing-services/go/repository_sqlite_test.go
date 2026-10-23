package repositorysqlite_test

import (
	"context"
	"path/filepath"
	"testing"

	"example.com/delivery-starter/adapters/driven/repositorysqlite"
	"example.com/delivery-starter/application/ports/repository"
	"example.com/delivery-starter/repositorycontract"
)

// The shared contract, against SQLite. This runs in `make verify` and needs no Docker. ":memory:"
// for the contract, because the contract is about behaviour and a fresh database per case is what
// keeps them independent.
func TestSqliteRepositorySatisfiesThePort(t *testing.T) {
	repositorycontract.Run(t, func(t *testing.T) repository.Repository {
		store, err := repositorysqlite.Open(":memory:")
		if err != nil {
			t.Fatalf("open sqlite: %v", err)
		}
		t.Cleanup(func() { store.Close() })
		return store
	})
}

// The whole reason to choose SQLite over the in-memory adapter.
func TestKeepsTheRowAndItsVersionAcrossACloseAndReopen(t *testing.T) {
	ctx := context.Background()
	location := filepath.Join(t.TempDir(), "states.sqlite3")
	first, err := repositorysqlite.Open(location)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	if _, err := first.Save(ctx, "order-1", repository.NoState, map[string]any{"status": "draft"}); err != nil {
		t.Fatalf("save: %v", err)
	}
	first.Close()

	reopened, err := repositorysqlite.Open(location)
	if err != nil {
		t.Fatalf("reopen: %v", err)
	}
	defer reopened.Close()
	row, found, err := reopened.Load(ctx, "order-1")
	if err != nil || !found || row.Version != 0 || row.State["status"] != "draft" {
		t.Fatalf("the row did not survive the reopen: %+v found=%v err=%v", row, found, err)
	}
	// A caller that has not noticed the restart is still refused, by the same rule as before it.
	result, err := reopened.Save(ctx, "order-1", repository.NoState, map[string]any{"status": "raced"})
	if err != nil {
		t.Fatalf("save: %v", err)
	}
	if result != repository.VersionConflict(0) {
		t.Fatalf("expected VersionConflict(0), got %+v", result)
	}
}

// A store that cannot be reached is an error from every call, never an absent row or a conflict —
// which is what lets /ready answer 503 rather than ready.
func TestAClosedDatabaseIsAnErrorNotAnAnswer(t *testing.T) {
	ctx := context.Background()
	store, err := repositorysqlite.Open(":memory:")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	store.Close()
	if _, _, err := store.Load(ctx, "order-1"); err == nil {
		t.Fatal("load on a closed database succeeded")
	}
	if _, err := store.Save(ctx, "order-1", repository.NoState, map[string]any{}); err == nil {
		t.Fatal("save on a closed database succeeded")
	}
	if _, err := store.Head(ctx); err == nil {
		t.Fatal("head on a closed database succeeded")
	}
}

func TestRefusesALocationItCannotOpen(t *testing.T) {
	if _, err := repositorysqlite.Open(filepath.Join(t.TempDir(), "missing", "states.sqlite3")); err == nil {
		t.Fatal("opened a database in a directory that does not exist")
	}
}
