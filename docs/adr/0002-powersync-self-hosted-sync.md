# ADR 0002: PowerSync (self-hosted Open Edition) as sync engine

## Status

Accepted (2026-07-23)

## Context

Every device must be fully offline-capable; structured data syncs everywhere; audio is on-demand/pinnable. Backend self-hosted on TrueNAS SCALE. [Sync engine research](../research/sync-engine.md) recommended PowerSync with CouchDB + PouchDB as fallback. The Flutter decision (ADR 0001) removed the fallback's viability: PouchDB is JavaScript with no first-party Flutter client, while PowerSync's Flutter SDK is production-status.

## Decision

- **PowerSync self-hosted "Open Edition"** (`journeyapps/powersync-service` Docker image).
- Clients hold a **local SQLite** database via the PowerSync Flutter SDK; per-user subsets defined by Sync Streams.
- Writes are **server-authoritative**: clients queue locally and upload through our backend API (ADR 0003), which writes to Postgres; PowerSync syncs results back down.
- Audio recordings use PowerSync's **official attachments pattern**: only metadata rows (id, session id, duration, codec, checksum, object key, pinned flag) go through sync; bytes live in **MinIO** on the NAS, fetched on demand and cached/pinned locally via the SDK's attachment queue.

## Consequences

- Offline queue, resume, conflict loop, and the on-demand/pinnable audio behavior come from the SDK rather than hand-rolled code.
- FSL-1.1 license (source-available, → Apache-2.0 per release after two years): unrestrictive for personal self-hosting, but not OSI open source.
- Highest container count of the candidates (see ADR 0003 for the topology that contains this).
- PowerSync requires a JWT issuer (ADR 0004) and a small write-path API (ADR 0003) — these are obligations created by this choice.
