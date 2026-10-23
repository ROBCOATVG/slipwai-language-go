package repositorymemory_test

import (
	"testing"

	"example.com/delivery-starter/adapters/driven/repositorymemory"
	"example.com/delivery-starter/application/ports/repository"
	"example.com/delivery-starter/repositorycontract"
)

// The contract, against the fake. This runs in `make verify` and needs no Docker, which is the
// whole reason the fake exists. `make test-integration` runs the same contract against Postgres.
func TestInMemoryRepositorySatisfiesThePort(t *testing.T) {
	repositorycontract.Run(t, func(*testing.T) repository.Repository {
		return repositorymemory.New()
	})
}
