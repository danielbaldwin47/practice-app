# ADR 0003: TypeScript backend API and single-Compose TrueNAS topology

## Status

Accepted (2026-07-23)

## Context

PowerSync (ADR 0002) does not handle writes: a small backend API must accept client write batches, apply them to Postgres, issue JWTs (ADR 0004), and presign MinIO URLs for audio upload/download. Candidate languages were Dart (fewest project languages, shared model code) and TypeScript (PowerSync's first-party examples, mature libraries). PowerSync also needs a bucket-storage database separate from the source database — MongoDB or Postgres.

## Decision

- **Backend API in TypeScript/Node.** PowerSync's reference backends are TS, so the write path, JWKS endpoint, and presigning patterns transfer nearly verbatim; `jose`, `pg`, and the S3 SDK are battle-tested. The service is small (~hundreds of lines), and the client talks to it through the PowerSync SDK's JSON upload hook, so Dart↔TS code sharing would have bought little.
- **One Postgres container, two databases**: app source DB + PowerSync bucket storage. No MongoDB.
- Full stack as **one Docker Compose file**, installed as a TrueNAS custom app: `postgres`, `powersync-service`, `minio`, `api` (TS), `cloudflared` (ADR 0004).

## Consequences

- Third project language (Dart, Rust, TS) — accepted for robustness; drift surface is limited to table/column names duplicated between Dart models and SQL.
- Single Compose file keeps ops legible on TrueNAS; all app data lands on ZFS datasets, which the backup strategy (ADR 0005) builds on.
- Postgres-only bucket storage should be verified by a deployment spike before the schema work hardens around it.
