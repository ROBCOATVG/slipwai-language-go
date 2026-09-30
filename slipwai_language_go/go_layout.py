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

ANSWERS: dict[protocol.Member[Any], object] = {
    protocol.WRITE_SIDE_FILES: WRITE_SIDE,
    protocol.READ_SIDE_FILES: READ_SIDE,
}
