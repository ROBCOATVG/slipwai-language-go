"""Go's service-layout answers: which committed asset lands where under a service, per feature.

The other half of `go.py`'s `LANGUAGE`, apart for the reason the tables it came from were apart from
`backing_services.py`: most of the bytes and none of the behaviour, and `go.py` has no room left under the line
budget. `ANSWERS` is this backend's, keyed by the member constants, and `LANGUAGE` takes it whole.

Sources are relative to `assets/backing-services/go/`, and a `../` reaches the material shared between
backends. Core merges the two sides feature by feature (`backing_services.service_layout`).
"""
from __future__ import annotations

from typing import Any

from ... import registry as protocol
from ..entry_stores import EntryStore, tab_marked
from ..flag_route import EntryWiring
from ..flags import FlagReader

# The write side: the event port, the adapters behind it, their contract suites and the migrations, and each
# transport's and identity provider's own files.
# Go keeps a package's tests beside its code, so there is no separate tests/ tree here. The
# `.sql` migrations come from `../sql/`, shared with the Python backend: one schema, one
# copy, because two copies of an event-log schema drift and nothing would notice.
WRITE_SIDE: dict[str, dict[str, str]] = {
    "memory": {
        "application/ports/events/events.go": "events.go",
        "adapters/driven/eventstorememory/store.go": "event_store_memory.go",
        "adapters/driven/eventstorememory/store_test.go": "event_store_memory_test.go",
        "eventstorecontract/contract.go": "event_store_contract.go",
    },
    "sqlite": {
        "adapters/driven/eventstoresqlite/store.go": "event_store_sqlite.go",
        "adapters/driven/eventstoresqlite/store_test.go": "event_store_sqlite_test.go",
    },
    "postgres": {
        "adapters/driven/eventstorepostgres/store.go": "event_store_postgres.go",
        "adapters/driven/eventstorepostgres/store_integration_test.go": "event_store_postgres_integration_test.go",
        "cmd/migrate/main.go": "migrate_main.go",
        "cmd/migrate/main_test.go": "migrate_main_test.go",
        # embed.go (+ keep) is what puts the .sql files into the ko-built migrate image; without
        # it the command reads an empty working directory even when the repository has .sql files.
        # `keep` lets //go:embed compile when there are not yet any migrations.
        "migrations/embed.go": "migrations_embed.go",
        "migrations/keep": "migrations_keep",
        "migrations/001_events.sql": "../sql/001_events.sql",
        "migrations/002_events_append_only.sql": "../sql/002_events_append_only.sql",
    },
    "net-http": {
        "adapters/driving/http/app.go": "http_app.go",
        "adapters/driving/http/app_test.go": "http_app_test.go",
        # What a browser meets before any route does. A wrapper rather than part of the mux:
        # a preflight is a question about a request, and no route has an answer to it.
        "adapters/driving/http/security.go": "http_security.go",
        "adapters/driving/http/security_test.go": "http_security_test.go",
        # The contract the routes above make, published as a file — there is no generator on this
        # backend and buying one would cost the dependency it exists without. `openapi_test.go` is
        # what holds the two together.
        "adapters/driving/http/openapi_test.go": "http_openapi_test.go",
        "openapi.yaml": "openapi.yaml",
        # The environment's one struct. A package rather than a block in `cmd/serve`, because
        # checking the environment is a rule with values that pass and values that do not, and
        # `cmd/serve` is the one package in the service that has no test.
        "config/config.go": "config.go",
        "config/config_test.go": "config_test.go",
        # The SDK's wiring, under the transport for the same reason: a span per request is the
        # one thing only a transport can produce.
        "observability/tracing.go": "tracing.go",
        "observability/tracing_test.go": "tracing_test.go",
        "cmd/serve/main.go": "serve_main.go",
    },
    "keycloak": {
        "adapters/driving/http/auth/oidckeycloak/oidckeycloak.go": "oidc_keycloak.go",
        "adapters/driving/http/auth/oidckeycloak/oidckeycloak_test.go": "oidc_keycloak_test.go",
    },
    "users-keycloak": {
        "adapters/driving/http/users/userskeycloak/userskeycloak.go": "users_oidc_keycloak.go",
        "adapters/driving/http/users/userskeycloak/userskeycloak_test.go": "users_oidc_keycloak_test.go",
    },
}

# The read side: the checkpoint port and its adapters, the catch-up runner, and the migrations that create the
# checkpoint table and the tag index. Every backend covers the same ground (`docs/backend-obligations.md` §3).
# Go keeps a package's tests beside its code, so there is no separate tests/ tree here.
READ_SIDE: dict[str, dict[str, str]] = {
    "memory": {
        # The timer that drives an async projection. Go has no framework to own a loop, so this
        # is the loop and the context that ends it: `Ticker.Run` blocks like everything
        # long-running in the standard library, and `cmd/serve` starts it beside the server under
        # the same cancelled context. In the runner's own package, and importing no transport.
        "projections/ticker.go": "projections_ticker.go",
        "projections/ticker_test.go": "projections_ticker_test.go",
        "application/ports/readmodels/readmodels.go": "read_models.go",
        "projections/projections.go": "projections.go",
        "projections/projections_test.go": "projections_test.go",
        "adapters/driven/checkpointstorememory/store.go": "checkpoint_store_memory.go",
        "adapters/driven/checkpointstorememory/store_test.go": "checkpoint_store_memory_test.go",
        "checkpointstorecontract/contract.go": "checkpoint_store_contract.go",
    },
    "sqlite": {
        "adapters/driven/checkpointstoresqlite/store.go": "checkpoint_store_sqlite.go",
        "adapters/driven/checkpointstoresqlite/store_test.go": "checkpoint_store_sqlite_test.go",
    },
    "postgres": {
        "adapters/driven/checkpointstorepostgres/store.go": "checkpoint_store_postgres.go",
        "adapters/driven/checkpointstorepostgres/store_integration_test.go": (
            "checkpoint_store_postgres_integration_test.go"
        ),
        "migrations/003_projection_checkpoints.sql": "../sql/003_projection_checkpoints.sql",
        "migrations/004_event_tags.sql": "../sql/004_event_tags.sql",
    },
}

# Where this backend's feature-flag reader is committed, where it lands in a service, and how a slice asks
# it. Emitted only under a managed target (`flags.flag_reader`).
READER = FlagReader(
    tree="go/flags",
    source="flags/flags.go",
    tests="flags/flags_test.go",
    call='flags.Enabled("checkout-v2")',
)

# How the flag source is wired into this backend's entry point, keyed by the HTTP option whose app takes it
# (`flag_route.wire_entry`). No `flag_resource`: this backend's transports are handed the source, and
# discover no route.
# Go imports by module path rather than relatively, so the line carries the template spelling of the
# module — `name_service` renames it along with every other `example.com/delivery-starter` here, for
# the same reason the flag reader keeps its paths in the template spelling. The placeholder sits
# between `config` and `observability` in `serve_main.go` because `gofmt` sorts the group's paths,
# and a block that puts `flags` after `observability` is the first lint a production Go project fails.
WIRING = {
    "net-http": EntryWiring(
        entry="cmd/serve/main.go",
        line='\t"example.com/delivery-starter/flags"',
        argument="flags.DefaultSource()",
        absent="nil",
    ),
}

# What this backend's entry point writes for each event-store answer: `entry_stores.py` says what the fields
# mean, and `composition.wire_store`, which reads it, the three rules every string here follows.
GO_MEMORY_IMPORT = '\t"example.com/delivery-starter/adapters/driven/eventstorememory"\n'
GO_PORT_IMPORT = '\t"example.com/delivery-starter/application/ports/events"\n'
GO_FALLBACK = """	// The event store this project answered the event-store question with, opened once and handed to
	// whatever needs it — from the checked environment rather than from os.Getenv, because `config` is
	// where this service's variables are held to a shape.
	//
	// The marked block is the answer; delete it — which is what `./init --event-store memory` does —
	// and the in-memory store it starts as is what is left — no nil check a marked block makes never-true (SA4023).
	var store events.Store = eventstorememory.New()
"""
# Go has no `*_OR_MEMORY` tail: its fallback is the declaration *above* the region, already assigned.

STORE = EntryStore(
    entry="cmd/serve/main.go",
    imports={
        None: f"\n{GO_MEMORY_IMPORT}",
        "sqlite": "\n"
        + GO_MEMORY_IMPORT
        + tab_marked(
            '\t"example.com/delivery-starter/adapters/driven/eventstoresqlite"',
        )
        + GO_PORT_IMPORT,
        "postgres": "\n"
        + GO_MEMORY_IMPORT
        + tab_marked(
            '\t"example.com/delivery-starter/adapters/driven/eventstorepostgres"',
        )
        + GO_PORT_IMPORT
        + tab_marked('\t"github.com/jackc/pgx/v5/pgxpool"'),
    },
    open={
        None: (
            "\t// The event store this project answered the event-store question with, opened once, here,\n"
            "\t// and handed to whatever needs it. Nothing else in this service constructs one.\n"
            "\tstore := eventstorememory.New()\n\n"
        ),
        "sqlite": GO_FALLBACK
        + tab_marked(
            "\tsqliteStore, err := eventstoresqlite.Open(settings.EventStorePath)\n"
            "\tif err != nil {\n"
            "\t\treturn err\n"
            "\t}\n"
            "\tdefer sqliteStore.Close()\n"
            "\tstore = sqliteStore",
        ),
        "postgres": GO_FALLBACK
        + tab_marked(
            "\t// pgxpool connects lazily, so this opens no socket while the process is starting: an\n"
            "\t// unreachable database shows up as /ready answering 503, which is what it is. A bad\n"
            "\t// connection string is a different thing and does stop the process, because nothing\n"
            "\t// about it will get better on its own — though `config` has already refused the\n"
            "\t// shapes it can name.\n"
            "\tpool, err := pgxpool.New(ctx, settings.DatabaseURL)\n"
            "\tif err != nil {\n"
            "\t\treturn err\n"
            "\t}\n"
            "\tdefer pool.Close()\n"
            "\tstore = eventstorepostgres.New(pool)",
        ),
    },
    argument="store",
    absent="nil",
)


# What "code shared between services" is in this family, and what sharing it would ask of the build: the
# architecture page's paragraph. The family's answer rather than a backend's, because the unit of sharing is
# the build tool's rather than the framework's.
SHARED = (
    "a Go module under `packages/<name>`, added to `go.work` beside the services and imported by its module "
    "path — inside the workspace no `replace` directive is needed. `make mutation` stages the service beside "
    "the workspace modules it imports before Gremlins runs (`scripts/go-mutation.py`), because Gremlins copies "
    "only the module it mutates and would not find them; the shared module is built there, never mutated"
)

ANSWERS: dict[protocol.Member[Any], object] = {
    protocol.WRITE_SIDE_FILES: WRITE_SIDE,
    protocol.READ_SIDE_FILES: READ_SIDE,
    protocol.FLAG_READER: READER,
    protocol.ENTRY_WIRING: WIRING,
    protocol.FLAG_RESOURCE: {},
    protocol.ENTRY_STORE: STORE,
}

# The family's own: `shared_code` is read by family name (`guidance.architecture`).
FAMILY_ANSWERS: dict[protocol.Member[Any], object] = {protocol.SHARED_CODE: SHARED}
