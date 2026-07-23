# PowerSync stack spike — findings

Resolves [#19](https://github.com/danielbaldwin47/practice-app/issues/19). Run on the
live TrueNAS box (SCALE 25.04, i3-14100, 32 GB, Docker 27.5.0), alongside the
production Nextcloud/Immich/Collabora apps, on 2026-07-23.

**Verdict: the ADR 0003 topology holds.** Postgres-only bucket storage works, one
Postgres container serving two databases works, and a row goes client → API →
Postgres → PowerSync → client in about a tenth of a second. Two deployment facts
came out of it that the ADRs did not have, and one of them changes ADR 0004.

## What was stood up

`docker-compose.yaml` here is ADR 0003's topology, verbatim: `postgres` (two
databases, no MongoDB), `powersync-service`, `minio`, a TypeScript `api`, and
`cloudflared`. Ports are all bound to `127.0.0.1` because this is a spike sharing a
NAS with real services.

```
docker compose up -d --build      # bring it up
python3 scripts/verify.py         # 19 protocol-level checks
./client-dart/run.sh              # 7 checks through the real PowerSync SDK
python3 scripts/latency.py        # write-to-sync latency
docker compose down -v            # tear down, volumes included
```

## Results

| Question from the ticket | Answer |
| --- | --- |
| Does the ADR 0003 topology hold? | Yes. All five services run as one Compose file. |
| Postgres-only bucket storage, no MongoDB? | Yes. Verified below. |
| Sync one table end-to-end from a Flutter client? | Partially — see [Flutter caveat](#the-flutter-caveat). |
| How much write-path API code is needed? | 130 lines. See [The API is small](#the-api-is-small). |

### Postgres-only bucket storage

`powersync_storage` is a second database inside the *same* `postgres` container as
the app's `practice` database. After boot it holds the 11 tables PowerSync migrates
for itself:

```
bucket_data  bucket_parameters  connection_report_events  current_data
custom_write_checkpoints  instance  locks  migrations  source_tables
sync_rules  write_checkpoints
```

Source and bucket storage may only share a server from **Postgres 14 up**; the stack
pins `postgres:18`. Replication runs off a `pgoutput` logical slot against a
`powersync` publication. No MongoDB image is pulled and none is running.

Worth knowing: the vendor's own `nodejs-postgres-bucket-storage` demo uses *two*
Postgres containers. One container is supported but is not the path they exercise,
so it is slightly off the beaten track.

### End-to-end sync

`scripts/verify.py` drives the wire protocol directly (19 checks, all passing):
writes through the API, reads back off `POST /sync/stream`, and covers per-user
isolation, deletes, and the MinIO attachment path. It confirmed the audio design
from ADR 0002 concretely — the `recordings` metadata row syncs, and the bytes never
appear in the sync payload.

`client-dart/` then does it again through the actual PowerSync SDK (7 checks, all
passing), which is the part raw HTTP cannot prove: schema mapping, `waitForFirstSync`,
a local-first insert visible before any upload, the `uploadData` hook posting to our
API, and the CRUD queue draining after round trip.

Sync rules use edition 3 `streams` with `auth.user_id()`; user B provably sees none
of user A's rows, and a client that puts someone else's `owner_id` in a write has it
ignored — the API forces `owner_id` from the JWT.

**Write-to-sync latency**, measured on an already-open stream (`scripts/latency.py`,
n=8): **min 92 ms, median 106 ms, max 114 ms**.

### The API is small

`api/src/index.ts` is the whole backend obligation created by ADR 0002/0003/0004:

| Concern | Code lines |
| --- | --- |
| Write path (`PUT /api/data`) | 54 |
| Token minting + JWT verification | 23 |
| JWKS signing-key management | 26 |
| MinIO presigning (up + down) | 17 |
| **Total** | **130** |

Four runtime dependencies: `express`, `jose`, `pg`, `@aws-sdk/client-s3`. The write
path is a table/column allowlist plus three SQL shapes (upsert, update, delete) in
one transaction — the SDK sends `{op, type, id, data}` and everything hard about
offline queueing, ordering and retry stays on the client side of the line.

The "hundreds of lines" estimate in ADR 0003 was pessimistic, but 130 lines is the
floor: it excludes real login (password storage, rate limiting, refresh tokens),
which ADR 0004 requires and which is the bulk of the remaining work.

One thing the write path must get right: return **4xx, not 5xx**, for bad batches. A
5xx makes the SDK retry the same poisoned batch forever.

### Footprint

Idle RSS after a full test run, on a NAS with 31 GiB total:

| Container | RSS |
| --- | --- |
| powersync | 99 MiB |
| api | 82 MiB |
| minio | 80 MiB |
| postgres | 63 MiB |
| **Total** | **~324 MiB** |

Images total roughly 1.4 GB (`powersync-service` 464 MB, `postgres:18` 456 MB, `api`
292 MB, `minio` 175 MB, `cloudflared` 63 MB). The `api` image is fat only because the
spike runs TypeScript through `tsx` with dev dependencies installed; a compiled build
would be a fraction of that.

## Two things the ADRs did not have

### 1. MinIO needs its own tunnel hostname — ADR 0004 is incomplete

ADR 0004 exposes "the API and PowerSync endpoints". That is not enough. A presigned
S3 URL is opened by the **device**, and the hostname is part of what gets signed, so a
URL signed against the compose-internal `http://minio:9000` is unusable off-box. The
spike hit this as a hard failure before `S3_PUBLIC_ENDPOINT` was added.

So either MinIO gets a third hostname on the tunnel, or the API proxies every audio
byte through Node. The tunnel is the better trade — proxying doubles bandwidth through
the smallest component and throws away the reason for presigning. `cloudflared/config.yml`
reflects this and validates (`cloudflared tunnel ingress validate` → OK), with the
MinIO **console** port deliberately left off.

Knock-on for [#18](https://github.com/danielbaldwin47/practice-app/issues/18): the
Cloudflare ~100 MB body cap now applies to the audio upload hostname directly, which
is exactly where the chunked-upload requirement bites.

### 2. TrueNAS runs these containers as non-root uids

`powersync-service` runs as uid 901 (`web`), but TrueNAS `App_Data` datasets are
`770 root:root`. uid 901 cannot even traverse the path, so a bind-mounted config
directory fails with `Config file path /config/service.yaml ... does not exist` —
which reads like a missing file and is actually a permission error. `cloudflared`
hits the same wall.

The spike works around it with `user: "901:0"`. A real install should instead give the
app its own dataset owned by 901, which is a TrueNAS app-setup step that needs to be
written down wherever the install is documented.

Two smaller host facts: port **5432 is already taken** by a production Postgres on this
NAS (the stack publishes 15432 instead), and **`/tmp` is mounted `noexec`**, which blocks
`dlopen` of the PowerSync core extension from anywhere under it.

### Restart behaviour

`docker compose restart` bounces every container at once, so PowerSync cannot release
its storage lock before Postgres goes down. The new process logs `PSYNC_S1003
Replication stream is locked by another process, standing by` and waits for the stale
lock to expire. It **self-heals in about 40 seconds** with no intervention, and all 19
checks pass afterwards. Expect the same on a NAS reboot; it is a nuisance, not a fault.

## The Flutter caveat

There is no Flutter, Dart, or Node toolchain on the NAS, and ADR 0001 makes the client
Mac-first — so "sync one table end-to-end from a Flutter scratch client" was done with
`powersync_core`, the **Dart** SDK, in a container. Same wire protocol, same Rust core
extension, same local SQLite, same connector API.

What that leaves unproven, and what a real Flutter run on a Mac still needs to cover:

- the **attachment queue** — pinning, cache eviction, on-demand fetch. Only the
  metadata sync and presigning were tested here, not the SDK's queue.
- Flutter-specific packaging of the core extension on macOS and iOS.
- `powersync_core` is marked **discontinued** in favour of the Flutter `powersync`
  package. That affects only this scratch client, not the real app — but it does mean
  the spike client should not be grown into anything.

## Files

- `docker-compose.yaml`, `.env` — the stack. Credentials here are throwaway.
- `postgres/init/01-init.sql` — two databases, three roles, domain tables, publication.
- `powersync/service.yaml`, `powersync/sync-config.yaml` — service + edition-3 sync streams.
- `api/` — the TypeScript backend.
- `cloudflared/config.yml` — validated ingress shape (no live tunnel; that needs a credential).
- `scripts/verify.py`, `scripts/latency.py`, `client-dart/` — the checks.
