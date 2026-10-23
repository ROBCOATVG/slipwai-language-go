package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestTheStateRungRefusesGivenEventsWithTheReason(t *testing.T) {
	var stderr bytes.Buffer
	if code := run(&stderr); code != 2 {
		t.Fatalf("expected exit 2, got %d", code)
	}
	if !strings.Contains(stderr.String(), "keeps no event log") {
		t.Fatalf("the refusal did not say why: %q", stderr.String())
	}
}
