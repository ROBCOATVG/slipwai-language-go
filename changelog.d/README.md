# The entry being written

One file per change. Together they are the `CHANGELOG.md` entry for the release `VERSION` is a snapshot of,
and they are assembled into it when that release is cut. `CHANGELOG.md` holds released entries only.

A fragment is a level and the prose, and the prose is the entry's, verbatim:

```md
MINOR

**One sentence saying what changed for whoever runs this.** Then as much as it takes.

**Catch-up.** What this asks of a repository already generated. Leave it out where a merge brings the change whole.
```

The first line is the level the change claims — `PATCH`, `MINOR` or `MAJOR` — by the same table as slipwai's own
(`AGENTS.md` in the factory's repository: an answer that stops being answerable is MAJOR, something newly given is
MINOR, the same answers generated better is PATCH). The highest level among the fragments is the entry's, and it is
the number `VERSION` has to carry. This package is versioned apart from slipwai's core: `language.json`'s `core`
range says which core it loads on, and that is independent of the number here.

Until the first release there is no entry to bump from: `VERSION` is `1.0.0.dev0`, and the fragments say what ships.
