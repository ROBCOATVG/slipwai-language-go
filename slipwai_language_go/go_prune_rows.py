"""The Go family's rows for the generated pruning script (`prune_rows`, S06).

Written into a project's `scripts/backing-services.py` when it has a Go service, and read by the factory's own
pruner. The shape is fixed in `specs/001-slipwai-2-language-addons/contracts/backend-protocol.md`.
"""
from __future__ import annotations

PRUNE_ROWS = {
    "marked_files": ("config/config.go", "cmd/serve/main.go"),
    "owned_files": {
        "sqlite": ("adapters/driven/eventstoresqlite", "adapters/driven/checkpointstoresqlite"),
        "postgres": (
            "adapters/driven/eventstorepostgres",
            "adapters/driven/checkpointstorepostgres",
            "cmd/migrate",
            # embed.go (+ keep) is what puts the .sql files into the ko-built migrate image; without it the
            # command reads an empty working directory even when the repository has .sql files.
            "migrations/embed.go",
            "migrations/keep",
            "migrations/001_events.sql",
            "migrations/002_events_append_only.sql",
            "migrations/003_projection_checkpoints.sql",
            "migrations/004_event_tags.sql",
        ),
        "net-http": (
            "adapters/driving/http/app.go",
            "adapters/driving/http/app_test.go",
            "adapters/driving/http/security.go",
            "adapters/driving/http/security_test.go",
            "adapters/driving/http/openapi_test.go",
            "openapi.yaml",
            "config",
            "observability",
            "cmd/serve",
        ),
        "keycloak": ("adapters/driving/http/auth/oidckeycloak",),
        "users-keycloak": ("adapters/driving/http/users/userskeycloak",),
    },
    # Go derives its requirements from the imports, so removing the adapter is the removal and `go mod tidy`
    # writes it down. Naming the modules here is what tells the pruner there is a module to tidy.
    "package_edits": {
        "postgres": {"packages": ("github.com/jackc/pgx/v5",), "scripts": ()},
        "sqlite": {"packages": ("modernc.org/sqlite",), "scripts": ()},
        # The instrumentation and the SDK behind it, which only a transport can use: one span per request.
        "net-http": {
            "packages": (
                "go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp",
                "go.opentelemetry.io/otel",
                "go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp",
                "go.opentelemetry.io/otel/sdk",
            ),
            "scripts": (),
        },
    },
    "manifest": "go.mod",
}
