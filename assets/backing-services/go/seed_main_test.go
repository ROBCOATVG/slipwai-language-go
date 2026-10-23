package main

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"example.com/delivery-starter/adapters/driven/eventstorememory"
	"example.com/delivery-starter/application/ports/events"
)

func fixedClock() time.Time { return time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC) }

func write(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "given.json")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatalf("write: %v", err)
	}
	return path
}

func environment(values map[string]string) func(string) (string, bool) {
	return func(name string) (string, bool) {
		value, ok := values[name]
		return value, ok
	}
}

// The door's whole promise: seeding the same stories twice appends them once, at the version each
// stream is really at — including a stream that already held an event this door did not write.
func TestAReplayRecordsNothingTwice(t *testing.T) {
	ctx := context.Background()
	store := eventstorememory.New()
	if _, err := store.Append(ctx, "course-1", events.NoStream, []events.DomainEvent{{
		Type: "CourseOpened", SchemaVersion: 1, StreamID: "course-1", Payload: map[string]any{"title": "Go"},
		OccurredAt: "2024-01-01T00:00:00Z", Actor: seedActor, CorrelationID: "018f3a2b-6c41-7c9d-9f0e-2a5b7c1d4e83",
	}}); err != nil {
		t.Fatalf("append: %v", err)
	}
	given, err := read(write(t, `[
		{"stream": "course-1", "event": "StudentEnrolled", "data": {"studentId": "s-1", "seats": 1}, "slice": "enrol"},
		{"stream": "course-2", "event": "CourseOpened", "data": {"title": "Rust"}}
	]`))
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	for run, want := range [][2]int{{2, 0}, {0, 2}} {
		appended, skipped, err := seed(ctx, store, given, fixedClock)
		if err != nil || appended != want[0] || skipped != want[1] {
			t.Fatalf("run %d: expected %v, got appended=%d skipped=%d err=%v", run+1, want, appended, skipped, err)
		}
	}
	course, err := store.Read(ctx, "course-1")
	if err != nil {
		t.Fatalf("read back: %v", err)
	}
	if len(course) != 2 || course[1].Version != 1 || course[1].Actor != seedActor {
		t.Fatalf("expected the given event appended after the existing one, by the seed actor: %+v", course)
	}
}

func TestTheSameDataHasOneIdentityWhateverItsKeyOrder(t *testing.T) {
	one := identity("s", "E", map[string]any{"a": 1.0, "b": "x"})
	two := identity("s", "E", map[string]any{"b": "x", "a": 1.0})
	if one != two {
		t.Fatal("key order changed an event's identity")
	}
	if one == identity("s", "F", map[string]any{"a": 1.0, "b": "x"}) {
		t.Fatal("two event types shared an identity")
	}
}

func TestRefusesWhatItCannotSeed(t *testing.T) {
	ctx := context.Background()
	durable := environment(map[string]string{"DATABASE_URL": "postgres://nobody@localhost:1/none"})
	for name, attempt := range map[string]struct {
		args   []string
		lookup func(string) (string, bool)
		code   int
		said   string
	}{
		"no file":           {nil, durable, 1, "give the file"},
		"no durable store":  {[]string{"given.json"}, environment(nil), 2, "DATABASE_URL is unset"},
		"a missing file":    {[]string{filepath.Join(t.TempDir(), "none.json")}, durable, 1, "no such file"},
		"not a list":        {[]string{write(t, `{"stream": "x"}`)}, durable, 1, "is a list of"},
		"no stream":         {[]string{write(t, `[{"event": "E", "data": {}}]`)}, durable, 1, "names no stream"},
		"no event":          {[]string{write(t, `[{"stream": "s", "data": {}}]`)}, durable, 1, "names no event"},
		"no data":           {[]string{write(t, `[{"stream": "s", "event": "E"}]`)}, durable, 1, "data is an object"},
		"a malformed store": {[]string{write(t, `[]`)}, environment(map[string]string{"DATABASE_URL": "::"}), 1, "seed:"},
	} {
		var stdout, stderr bytes.Buffer
		if code := run(ctx, attempt.args, attempt.lookup, &stdout, &stderr); code != attempt.code {
			t.Fatalf("%s: expected exit %d, got %d (%s)", name, attempt.code, code, stderr.String())
		}
		if !strings.Contains(stderr.String(), attempt.said) {
			t.Fatalf("%s: expected %q in %q", name, attempt.said, stderr.String())
		}
	}
}
