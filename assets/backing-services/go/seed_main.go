// Command seed is the seed door: it appends the events a slice's `try-it.json` *gives*, through this
// service's own event-store port.
//
//	make seed-service FILE=<json>
//	cd apps/service && DATABASE_URL=postgres://app:app@localhost:5433/app go run ./cmd/seed given.json
//
// The file is a list of `{"stream", "event", "data"}` — the events a story needs that the slice which
// would have written them has not been built yet, so a view can be seeded to a state and judged before
// its producers exist. They go in the way every event goes in: through the port, at the stream's
// current version, each written by a system actor with a correlation id of its own. Never through an
// HTTP route — this is a process with the store's credentials, and the app serves no door.
//
// **A replay records nothing twice.** An event's identity here is the hash of its stream, its type and
// its data; one already on the stream with the same identity is skipped, so seeding the same stories
// into the same database again adds nothing. **It needs the durable store**: with no DATABASE_URL there
// is no log to append to, and this says so and exits 2 rather than seeding an in-memory store the next
// process would never see.
package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"example.com/delivery-starter/adapters/driven/eventstorepostgres"
	"example.com/delivery-starter/application/ports/events"
)

// The actor every seeded event is written by: system work names itself, and a seeded fact is one no
// person decided.
var seedActor = events.Actor{Kind: "system", ID: "systems/seed-door"}

// Given is one event a story gives. `slice` is carried by the file for the reader and not used here.
type Given struct {
	Stream string         `json:"stream"`
	Event  string         `json:"event"`
	Data   map[string]any `json:"data"`
	Slice  string         `json:"slice,omitempty"`
}

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.LookupEnv, os.Stdout, os.Stderr))
}

// run is the command with its edges handed in, so a test can drive every refusal without a database.
func run(
	ctx context.Context,
	args []string,
	lookup func(string) (string, bool),
	stdout, stderr io.Writer,
) int {
	if len(args) != 1 {
		fmt.Fprintln(stderr, "seed: give the file of events to append — make seed-<service> FILE=<json>")
		return 1
	}
	url, _ := lookup("DATABASE_URL")
	if strings.TrimSpace(url) == "" {
		fmt.Fprintln(stderr, "seed: DATABASE_URL is unset, so there is no durable store to append to. The seed "+
			"door needs the database `make services-up` starts; an in-memory store would be gone before the app "+
			"read it.")
		return 2
	}
	given, err := read(args[0])
	if err != nil {
		fmt.Fprintf(stderr, "seed: %v\n", err)
		return 1
	}
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		fmt.Fprintf(stderr, "seed: %v\n", err)
		return 1
	}
	defer pool.Close()
	appended, skipped, err := seed(ctx, eventstorepostgres.New(pool), given, time.Now)
	if err != nil {
		fmt.Fprintf(stderr, "seed: %v\n", err)
		return 1
	}
	fmt.Fprintf(stdout, "seed: %d event(s) appended, %d already there\n", appended, skipped)
	return 0
}

// read parses the file a story's givens were written to, refusing anything that is not one.
func read(path string) ([]Given, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var given []Given
	if err := json.Unmarshal(raw, &given); err != nil {
		return nil, fmt.Errorf("%s is a list of {stream, event, data}: %w", path, err)
	}
	for index, one := range given {
		switch {
		case strings.TrimSpace(one.Stream) == "":
			return nil, fmt.Errorf("given %d names no stream", index+1)
		case strings.TrimSpace(one.Event) == "":
			return nil, fmt.Errorf("given %d names no event", index+1)
		case one.Data == nil:
			return nil, fmt.Errorf("given %d's data is an object in the model's shape", index+1)
		}
	}
	return given, nil
}

// seed appends each given event that is not already on its stream, at the stream's current version.
// Against the port rather than the adapter, so the rule is tested on the in-memory store.
func seed(ctx context.Context, store events.Store, given []Given, now func() time.Time) (int, int, error) {
	correlation, err := freshCorrelationID()
	if err != nil {
		return 0, 0, err
	}
	appended, skipped := 0, 0
	for _, one := range given {
		existing, err := store.Read(ctx, one.Stream)
		if err != nil {
			return appended, skipped, err
		}
		wanted := identity(one.Stream, one.Event, one.Data)
		if holds(existing, wanted) {
			skipped++
			continue
		}
		version := events.NoStream
		if len(existing) > 0 {
			version = existing[len(existing)-1].Version
		}
		result, err := store.Append(ctx, one.Stream, version, []events.DomainEvent{{
			Type:          one.Event,
			SchemaVersion: 1,
			StreamID:      one.Stream,
			Payload:       one.Data,
			OccurredAt:    now().UTC().Format(time.RFC3339Nano),
			Actor:         seedActor,
			CorrelationID: correlation,
		}})
		if err != nil {
			return appended, skipped, err
		}
		if result.Outcome != events.OutcomeAppended {
			return appended, skipped, fmt.Errorf("%s on %s was not appended: the stream moved to version %d "+
				"while this ran. Run it again", one.Event, one.Stream, result.ActualVersion)
		}
		appended++
	}
	return appended, skipped, nil
}

func holds(existing []events.CommittedEvent, wanted string) bool {
	for _, event := range existing {
		if identity(event.StreamID, event.Type, event.Payload) == wanted {
			return true
		}
	}
	return false
}

// identity is the hash of an event's stream, type and data. encoding/json writes a map's keys sorted,
// so the same data hashes the same however its keys were ordered in the file or the store.
func identity(stream, eventType string, data map[string]any) string {
	encoded, err := json.Marshal(data)
	if err != nil {
		// Data that came out of JSON always goes back into it; anything else is a bug here.
		panic(err)
	}
	sum := sha256.Sum256([]byte(stream + "\x00" + eventType + "\x00" + string(encoded)))
	return hex.EncodeToString(sum[:])
}

// freshCorrelationID is a random (version 4) UUID: one business transaction per run. The standard
// library has no UUID, and a dependency for sixteen random bytes would be the wrong trade.
func freshCorrelationID() (events.CorrelationID, error) {
	buffer := make([]byte, 16)
	if _, err := rand.Read(buffer); err != nil {
		return "", errors.Join(errors.New("seed: no randomness for a correlation id"), err)
	}
	buffer[6] = buffer[6]&0x0f | 0x40
	buffer[8] = buffer[8]&0x3f | 0x80
	text := hex.EncodeToString(buffer)
	return events.NewCorrelationID(text[0:8] + "-" + text[8:12] + "-" + text[12:16] + "-" + text[16:20] + "-" + text[20:])
}
