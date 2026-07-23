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

## Amendments

- **2026-07-23**, from the [stack spike](https://github.com/danielbaldwin47/practice-app/issues/19): topology confirmed on the live NAS. Postgres-only bucket storage works with source and storage databases in one container (Postgres 14+ is required for that; the stack pins 18). Write-to-sync latency measured at ~106 ms median; the whole stack idles at ~324 MiB. The API came out at **130 lines**, not the "hundreds" estimated above — though that excludes the login/refresh-token work ADR 0004 requires. Two deployment constraints surfaced: TrueNAS `App_Data` datasets are `770 root:root` while `powersync-service` runs as uid 901, so the app needs its own dataset owned by 901; and host port 5432 is already taken by another app. Details in `spike/powersync-stack/README.md`.
