-- Runs once, on first boot, against POSTGRES_DB=practice as POSTGRES_USER=postgres.
--
-- The point of this file is ADR 0003's claim: ONE Postgres container holding TWO
-- databases -- the app source DB and PowerSync's bucket storage -- with no MongoDB.
-- Postgres 14+ is required for source and bucket storage to share a server.

-- ---------------------------------------------------------------- bucket storage
-- Second database, same container. PowerSync creates and owns the `powersync`
-- schema inside it (docs' "Option 1": grant CREATE, let the service migrate).
CREATE USER powersync_storage_user WITH PASSWORD 'spike_storage_pw';
CREATE DATABASE powersync_storage OWNER powersync_storage_user;

-- ---------------------------------------------------------------- replication role
-- Reads the source DB over logical replication. BYPASSRLS is in the vendor's
-- recipe; harmless here (no RLS) and needed once row-level security lands.
CREATE ROLE powersync_repl WITH REPLICATION BYPASSRLS LOGIN PASSWORD 'spike_repl_pw';
GRANT CONNECT ON DATABASE practice TO powersync_repl;
GRANT USAGE ON SCHEMA public TO powersync_repl;

-- ---------------------------------------------------------------- app write role
-- The TS API's identity. Server-authoritative writes (ADR 0002) all land here.
CREATE ROLE practice_api WITH LOGIN PASSWORD 'spike_api_pw';
GRANT CONNECT ON DATABASE practice TO practice_api;
GRANT USAGE ON SCHEMA public TO practice_api;

-- ---------------------------------------------------------------- source schema
-- Three tables, deliberately domain-shaped (CONTEXT.md) rather than a todo list,
-- so the spike exercises the real sync surface: a day page, its timed blocks, and
-- an audio attachment whose BYTES live in MinIO and whose ROW syncs (ADR 0002).

CREATE TABLE sessions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id    uuid NOT NULL,
  day         date NOT NULL,
  journal     text NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE blocks (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id    uuid NOT NULL,
  session_id  uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  subject     text,
  goal        text,
  started_at  timestamptz NOT NULL DEFAULT now(),
  minutes     integer NOT NULL DEFAULT 0,
  note        text NOT NULL DEFAULT ''
);

-- Attachment METADATA only. `object_key` points into MinIO; `pinned` drives the
-- SDK's attachment queue.
CREATE TABLE recordings (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id    uuid NOT NULL,
  block_id    uuid REFERENCES blocks(id) ON DELETE SET NULL,
  object_key  text NOT NULL,
  codec       text NOT NULL DEFAULT 'aac',
  duration_ms integer NOT NULL DEFAULT 0,
  checksum    text,
  pinned      boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON blocks (session_id);
CREATE INDEX ON recordings (block_id);

GRANT SELECT ON ALL TABLES IN SCHEMA public TO powersync_repl;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO practice_api;

-- Every table above has a primary key, so the default REPLICA IDENTITY suffices;
-- REPLICA IDENTITY FULL would only be needed for PK-less tables.
CREATE PUBLICATION powersync FOR TABLE sessions, blocks, recordings;
