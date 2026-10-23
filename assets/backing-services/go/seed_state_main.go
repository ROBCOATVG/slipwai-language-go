// Command seed is the seed door's place on the state-stored rung, and it refuses.
//
//	make seed-service FILE=<json>
//
// A slice's `try-it.json` may *give* the events an unbuilt upstream would have written, and on the
// event-sourced rung this command appends them to the log. This service keeps current state and no log,
// so there is nothing a given event could be appended to — and inventing rows from events would be a
// fold this service does not have. The Makefile target is there because the durable store is, so it is
// answered here with the reason rather than with a missing package.
//
// Exit 2, the code the event-sourced door gives when there is no store to append to: the request was
// well formed, and this service cannot honour it. Seed a state-stored service through its own use cases.
package main

import (
	"fmt"
	"io"
	"os"
)

func main() {
	os.Exit(run(os.Stderr))
}

func run(stderr io.Writer) int {
	fmt.Fprintln(stderr, "seed: this service is on the state-stored rung and keeps no event log, so a story's "+
		"given events have nothing to be appended to. Seed it through its own use cases instead.")
	return 2
}
