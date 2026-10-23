-- The state table: one current row per id, for a service on the state-stored rung. The version column
-- IS the optimistic concurrency control — a save compares it and increments it in one statement, so a
-- writer that decided against a version another writer has already moved past writes nothing.
--
-- There is deliberately no down migration here. A file applied by `cmd/migrate` is executed whole, so a
-- rollback kept in the same file would run in the same breath as the migration that created the table.
CREATE TABLE states (
  id      TEXT    PRIMARY KEY,
  version INTEGER NOT NULL,
  -- JSONB, and only an object: the port's state is a map, and a column that would take a bare string
  -- or an array is one a hand-written fix could fill with something no adapter can read back.
  state   JSONB   NOT NULL,
  CONSTRAINT states_version_non_negative CHECK (version >= 0),
  CONSTRAINT states_state_is_object CHECK (jsonb_typeof(state) = 'object')
);
