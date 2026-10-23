MINOR

**A slice's story may be given its inputs, through the service's own seed door.** A service on the durable
store gains `cmd/seed`, run by `make seed-<service> FILE=<json>`: it appends the events a slice's
`try-it.json` *gives* — the ones an unbuilt upstream slice would have written — through the event-store port,
at the stream's current version, as a system actor, with an identity hashed from stream, type and data so a
replay records nothing twice. With no `DATABASE_URL` it says so and exits 2. Never an HTTP route: the door
is a process with the store's credentials. slipwai's Try it runs it before a story's first step. On the
state-stored rung the target refuses with exit 2 and the reason, because there is no log to append to.

**Catch-up:** `slipwai language upgrade go`, then `slipwai migrate`; the service gains `cmd/seed` and the
Makefile target. Until then a story's `given` is validated by `check-try` and not applied, and Try it says
*no seed door yet*.
