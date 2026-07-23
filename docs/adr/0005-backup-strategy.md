# ADR 0005: Backup strategy — snapshots, pg_dump, offsite

## Status

Accepted (2026-07-23)

## Context

All app state lives on the TrueNAS box: Postgres (every practice log) and MinIO (every recording), on ZFS datasets. ZFS snapshots alone are same-pool: they survive mistakes, not pool loss or house-level events.

## Decision

Three layers:

1. **Scheduled ZFS snapshots** on the app datasets (fast, frequent, local restore).
2. **Nightly `pg_dump`** to a dataset — a guaranteed-consistent logical restore point independent of snapshot crash-consistency.
3. **Offsite via TrueNAS Cloud Sync**: dumps + the MinIO bucket pushed to an S3-compatible cloud target (Backblaze B2 / Cloudflare R2 — pennies at this data size).

## Consequences

- Survives fat-fingers (snapshots), corrupt-but-running Postgres (dumps), and pool/site loss (offsite).
- Offsite target credentials and the Cloud Sync schedule become part of backend provisioning.
- Restore procedure (compose up → restore dump → re-point MinIO at synced bucket) should be written down once the stack exists.
