MINOR

**Go is now a language package of its own.** The Go backend that was built into slipwai — its service
skeleton, event-store adapters, HTTP transport, identity wiring, Gremlins mutation gate, module variants and
toolchain — lives here, with the history it had there, and slipwai loads it from its language directory
(`$SLIPWAI_LANGUAGES`, or `~/.slipwai/languages`). The projects it generates are byte for byte those slipwai
generated with Go built in. It declares the catalog schema it loads on, `core >=9.0,<10`, in `language.json`.
