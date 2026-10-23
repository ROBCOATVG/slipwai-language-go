//go:build integration

// The state repository against real Postgres.
//
// Behind the `integration` build tag, so `make verify` never compiles it and the repository gate
// stays runnable with no infrastructure. `make test-integration` is the target that needs a
// database:
//
//	make services-up migrate test-integration
//
// It runs the same contract the infrastructure-free adapters pass, plus the one thing only a real
// store can prove: that two independent connections creating one id, or updating it at one version,
// produce exactly one winner.
package repositorypostgres_test

import (
	"context"
	"os"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"example.com/delivery-starter/adapters/driven/repositorypostgres"
	"example.com/delivery-starter/application/ports/repository"
	"example.com/delivery-starter/repositorycontract"
)

// openPool turns a refused connection or a missing table into the instruction that fixes it.
func openPool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	url := os.Getenv("DATABASE_URL")
	if strings.TrimSpace(url) == "" {
		t.Fatal("DATABASE_URL is unset, so there is no database to test against. Run " +
			"`make test-integration`, which sets it, after `make services-up migrate`.")
	}
	pool, err := pgxpool.New(context.Background(), url)
	if err != nil {
		t.Fatalf("cannot reach the database at %s: %v\nStart it first:  make services-up migrate", url, err)
	}
	if _, err := pool.Exec(context.Background(), "SELECT 1 FROM states LIMIT 1"); err != nil {
		pool.Close()
		t.Fatalf("cannot read the states table: %v\nApply the schema first:  make services-up migrate", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func TestPostgresRepositorySatisfiesThePort(t *testing.T) {
	pool := openPool(t)
	repositorycontract.Run(t, func(*testing.T) repository.Repository {
		return repositorypostgres.New(pool)
	})
}

// Two pools, so the two writers are two sessions the database has to order, not two calls one
// connection would run one after the other.
func TestIndependentConnectionsSeeExactlyOneWinner(t *testing.T) {
	ctx := context.Background()
	writers := map[string]*repositorypostgres.Repository{
		"one": repositorypostgres.New(openPool(t)),
		"two": repositorypostgres.New(openPool(t)),
	}
	id := repositorycontract.FreshID(t)

	created := repositorycontract.Race(t, func(writer string) (repository.SaveResult, error) {
		return writers[writer].Save(ctx, id, repository.NoState, map[string]any{"writer": writer})
	})
	repositorycontract.RequireOneWinner(t, created, 0)

	updated := repositorycontract.Race(t, func(writer string) (repository.SaveResult, error) {
		return writers[writer].Save(ctx, id, 0, map[string]any{"writer": writer})
	})
	repositorycontract.RequireOneWinner(t, updated, 1)

	winner := "two"
	if updated[0].Outcome == repository.OutcomeSaved {
		winner = "one"
	}
	row, found, err := writers["one"].Load(ctx, id)
	if err != nil || !found || row.Version != 1 || row.State["writer"] != winner {
		t.Fatalf("expected %s's state at version 1, got %+v found=%v err=%v", winner, row, found, err)
	}
}
