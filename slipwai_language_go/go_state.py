"""The state-stored rung: the files a Go service answered `write-model: state` is given, and how its entry
point opens them.

`write_side_files` is read at the rung (core's `rungs.rung_rows`): a service on `state` is given the rows under
the `state` key *instead* of the feature rows beside it, so the block repeats the transport's and the identity
providers' rows — they do not depend on what the store is asked to hold — and swaps the event store, its contract
and its migrations for the repository port, its adapters, their one contract suite and the versioned state table.
There is no `state` block on the read side: a state-stored service has no projection to be behind, so a read
model is a query over the write table and there is no checkpoint to keep.

The entry point is composed here rather than by `composition.wire_store`, because `entry_store` describes the
event store's opening and that is the one answer core reads. Same placeholders, same rules — each placeholder
owns its line, a store a later `./init` could prune sits in its marked region, and the in-memory fallback is the
declaration *above* that region, already assigned — so a pruned project reads exactly as one generated on memory.
"""
from __future__ import annotations

from pathlib import Path

from slipwai.assets import source_text
from slipwai.project.entry_stores import FEATURE, tab_marked
from slipwai.selection import Selection

ASSETS = Path(__file__).resolve().parents[1] / "assets"

# What every state-stored service is given, whichever store it chose: the port, the in-memory adapter the
# contract runs against in `make verify`, and the contract itself. Relative to `assets/backing-services/go/`.
BASE = {
    "application/ports/repository/repository.go": "repository.go",
    "adapters/driven/repositorymemory/repository.go": "repository_memory.go",
    "adapters/driven/repositorymemory/repository_test.go": "repository_memory_test.go",
    "repositorycontract/contract.go": "repository_contract.go",
}

# The store rows of the `state` block, keyed by feature as the event store's are. `memory` is the axis's
# `always` feature, so it is what every answer carries; the transport's rows are added in `go_layout.py`.
STATE_WRITE: dict[str, dict[str, str]] = {
    "memory": BASE,
    "sqlite": {
        "adapters/driven/repositorysqlite/repository.go": "repository_sqlite.go",
        "adapters/driven/repositorysqlite/repository_test.go": "repository_sqlite_test.go",
    },
    "postgres": {
        "adapters/driven/repositorypostgres/repository.go": "repository_postgres.go",
        "adapters/driven/repositorypostgres/repository_integration_test.go": (
            "repository_postgres_integration_test.go"
        ),
        # The same migration runner the event store uses, embedded for the same reason (`go_layout.py`):
        # the ko-built migrate image carries a binary and nothing beside it.
        "cmd/migrate/main.go": "migrate_main.go",
        "cmd/migrate/main_test.go": "migrate_main_test.go",
        "migrations/embed.go": "migrations_embed.go",
        "migrations/keep": "migrations_keep",
        "migrations/001_states.sql": "../sql/001_states.sql",
        # The Makefile's seed door is emitted for the durable store whatever the rung (core reads the
        # `seed` tooling line per feature), so this rung answers it — with a refusal that says why.
        "cmd/seed/main.go": "seed_state_main.go",
        "cmd/seed/main_test.go": "seed_state_main_test.go",
    },
}

MEMORY_IMPORT = '\t"example.com/delivery-starter/adapters/driven/repositorymemory"\n'
PORT_IMPORT = '\t"example.com/delivery-starter/application/ports/repository"\n'
# Spelled `states` rather than `repository`, which is the port's package name and would shadow it.
FALLBACK = """	// The state repository this project selected, opened once and handed to whatever needs it — from
	// the checked environment rather than from os.Getenv, because `config` is where this service's
	// variables are held to a shape.
	//
	// The marked block is the answer; delete it — which is what `./init --persistence memory` does —
	// and the in-memory repository it starts as is what is left.
	var states repository.Repository = repositorymemory.New()
"""

# Keyed like `entry_store`'s tables: `None` for the in-memory answer, then each feature that answers the axis.
IMPORTS: dict[str | None, str] = {
    None: f"\n{MEMORY_IMPORT}",
    "sqlite": "\n" + MEMORY_IMPORT
    + tab_marked('\t"example.com/delivery-starter/adapters/driven/repositorysqlite"') + PORT_IMPORT,
    "postgres": "\n" + MEMORY_IMPORT
    + tab_marked('\t"example.com/delivery-starter/adapters/driven/repositorypostgres"') + PORT_IMPORT
    + tab_marked('\t"github.com/jackc/pgx/v5/pgxpool"'),
}
OPEN: dict[str | None, str] = {
    None: (
        "\t// The state repository this project selected, opened once, here, and handed to whatever\n"
        "\t// needs it. Nothing else in this service constructs one.\n"
        "\tstates := repositorymemory.New()\n"
    ),
    "sqlite": FALLBACK + tab_marked(
        "\tsqliteStates, err := repositorysqlite.Open(settings.EventStorePath)\n"
        "\tif err != nil {\n"
        "\t\treturn err\n"
        "\t}\n"
        "\tdefer sqliteStates.Close()\n"
        "\tstates = sqliteStates",
    ),
    "postgres": FALLBACK + tab_marked(
        "\t// pgxpool connects lazily, so this opens no socket while the process is starting: an\n"
        "\t// unreachable database shows up as /ready answering 503, which is what it is.\n"
        "\tpool, err := pgxpool.New(ctx, settings.DatabaseURL)\n"
        "\tif err != nil {\n"
        "\t\treturn err\n"
        "\t}\n"
        "\tdefer pool.Close()\n"
        "\tstates = repositorypostgres.New(pool)",
    ),
}
ENTRY = "cmd/serve/main.go"


def state_files(files: dict[str, str], selection: Selection) -> None:
    """Give a state-stored service its repository, and open it in the entry point, in place.

    The base set is written whether or not the persistence axis was asked: the standard profile never asks it,
    and its services keep current state all the same, so they are given the in-memory repository rather than
    nothing. Where the axis was asked, `backing_service_service_files` has already written the same files.
    """
    for destination, source in BASE.items():
        files[destination] = source_text(ASSETS, f"backing-services/go/{source}", ASSETS.parent)
    if ENTRY not in files:
        return
    store = selection.feature_of("persistence") if selection.has("memory") else None
    imported, opened = IMPORTS[store], OPEN[store].rstrip("\n") + "\n\n"
    if store is not None:
        imported, opened = imported.replace(FEATURE, store), opened.replace(FEATURE, store)
    content = files[ENTRY]
    content = content.replace("__STORE_IMPORT__\n", imported)
    content = content.replace("__STORE_OPEN__\n", opened)
    content = content.replace("__STORE_ARGUMENT__", "states")
    files[ENTRY] = content.replace("whose event store has gone away", "whose state repository has gone away")
