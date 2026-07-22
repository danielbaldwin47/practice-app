# Local-first sync engine options for practice-app

Date: 2026-07-22
Research for [issue #4](https://github.com/danielbaldwin47/practice-app/issues/4)

Constraints recap: 2–3 users, self-hosted in Docker on TrueNAS SCALE, offline-first structured data on phones and desktop, large audio recordings synced on demand (pinnable, not force-replicated), remote access off the home LAN.

---

## TL;DR / recommendation

**Best fit: PowerSync (self-hosted "Open Edition").** It is the only candidate that ticks every box more or less as-designed: a self-hostable sync service shipped as a Docker image ([docs](https://docs.powersync.com/self-hosting/getting-started)), production-status client SDKs for Flutter, React Native, and web JS backed by a local SQLite database ([SDK list](https://docs.powersync.com/client-sdk-references/introduction)), server-authoritative sync with partial sync via Sync Streams/Rules, and — critically for the audio-recordings constraint — an official, documented attachments pattern where only small metadata records sync through PowerSync while the binary files live in external storage (S3-compatible, e.g. MinIO on the NAS) and are fetched/queued on demand ([attachments docs](https://docs.powersync.com/usage/use-case-examples/attachments-files)). The trade-offs: the service is FSL-1.1 licensed (source-available, converts to Apache-2.0 per release after two years — fine for internal/personal use, but not OSI open source) ([LICENSE](https://github.com/powersync-ja/powersync-service/blob/main/LICENSE)), and the deployment has real moving parts: the service container, your source Postgres, a *separate* bucket-storage database (MongoDB or Postgres), a JWKS/JWT auth setup, and a small backend API of your own to accept writes ([setup docs](https://docs.powersync.com/self-hosting/installation/powersync-service-setup)).

**Simplest fully-open-source alternative: CouchDB + PouchDB.** One official Apache-maintained Docker container ([Docker Hub](https://hub.docker.com/_/couchdb)), a battle-tested master-master replication protocol with built-in filtered/selective replication and checkpointed resume ([replication docs](https://docs.couchdb.org/en/stable/replication/intro.html)), everything Apache-2.0. This is the lowest ops burden of any option here and the conflict model (revision trees) is well understood. The costs: PouchDB is maintained but slow-moving (last release 9.0.0, June 2024 — [repo](https://github.com/pouchdb/pouchdb)), phones would be served as a PWA rather than a native app (React Native support is via community adapters), and CouchDB's own docs steer you away from large attachments (base64 transfer overhead, "not recommended for large attachment sizes" in views/changes — [views API](https://docs.couchdb.org/en/stable/api/ddoc/views.html)), so the audio blobs should live outside the database here too.

**Eliminated:** cr-sqlite (no release since Jan 2024 — effectively dormant), the old `electric-sql` full-stack client (superseded; today's Electric is read-path-only, so it's half a sync engine for this use case unless you want to build the write path yourself), Automerge/Yjs as the *primary* store (document-CRDT model is a poor shape for a growing library of practice-log rows + a blob catalog, and their sync servers do nothing for blobs), and SQLite session extension / roll-your-own (it's a changeset toolkit, not a sync engine — you'd be building conflict handling, transport, and auth from scratch for a 3-user app).

---

## Comparison table

| Dimension | PowerSync (self-hosted) | Electric | CouchDB + PouchDB (/RxDB) | Automerge + sync server | Yjs + Hocuspocus / y-sweet | cr-sqlite / SQLite session |
|---|---|---|---|---|---|---|
| Server open source / license | Source-available **FSL-1.1**, → Apache-2.0 after 2 yrs; free self-host "Open Edition" | **Apache-2.0** | **Apache-2.0** (CouchDB, PouchDB); RxDB core Apache-2.0 but key storages paid | **MIT** (lib + sync server) | **MIT** (Yjs, Hocuspocus, y-sweet) | MIT / public-domain SQLite |
| Docker self-host | Yes, `journeyapps/powersync-service` | Yes | Yes, official `couchdb` image | Yes, ghcr image, but server is "a very simple… unsecured Express app" | Hocuspocus: Node app; y-sweet: binary/npx, S3-backed | No server exists; build your own |
| Data model / conflicts | Server-authoritative; local SQLite; writes via your API | Read-path sync of Postgres "Shapes"; **no write-path** — you build it | Master-master doc replication; revision trees, app resolves conflicts (RxDB: client-side conflict handlers) | CRDT, automatic merge, full history | CRDT, automatic merge | Changesets + manual conflict callbacks |
| Partial / selective sync | Yes — Sync Streams / Sync Rules per user | Yes — Shapes (where-clause subsets) | Yes — filtered/selector replication; per-user DBs idiomatic | Per-document granularity only | Per-document granularity only | Whatever you build |
| Large blobs | **Official pattern**: metadata in sync, files in S3-compatible store, on-demand queue + helpers in all major SDKs | Not handled; bytea in Postgres not sensible → external store | Attachments exist but docs warn on large sizes; external store recommended | Not handled (docs: keep docs small; store blobs elsewhere) | Not handled (y-sweet persists *doc state* to S3, not user files) | Not handled |
| Mobile clients | Flutter, React Native, Kotlin, Swift: production; Web: production | TS client (web); native mobile = DIY over HTTP | PouchDB: browser/Node (PWA on phones); RN via adapters | JS/WASM; Rust core with C API for iOS; RN rough | JS-first; native ports exist | DIY |
| Maturity (as of 2026-07) | Active; SDKs GA | Active; sync-service 1.7.8 (Jul 2026), 1.0+ stable | CouchDB 3.5.x active; PouchDB last release Jun 2024 | Automerge v3.3.2 (Jul 2026) active; sync server last release Jul 2024 | Yjs v13.6.31 (May 2026); Hocuspocus v4.4.0 (Jul 2026); y-sweet 0.9.1 (Sep 2025) | cr-sqlite last release Jan 2024 |
| Ops burden @ 3 users | Medium–high: service + Postgres + bucket-storage DB + JWT auth + your write API | Medium: Electric + Postgres + your whole write path | **Low: one container** | Low but DIY auth; server is demo-grade | Low–medium; auth via hooks | High: you are the sync engine |

---

## Candidate details

### 1. PowerSync

**Self-hosting.** The sync service is published to Docker Hub as `journeyapps/powersync-service`; self-hosting is a documented first-class path ("Open Edition"), with the caveat that the web Dashboard is cloud-only ([self-hosting docs](https://docs.powersync.com/self-hosting/getting-started)). A self-hosted deployment needs: the service container; a **source database** (Postgres — "only 1 connection is currently supported"); a **separate bucket-storage database** (MongoDB or Postgres) for sync-bucket data; JWT auth via a JWKS endpoint or static key; and a YAML/JSON config defining Sync Streams/Rules ([service setup docs](https://docs.powersync.com/self-hosting/installation/powersync-service-setup)). Writes do not go through PowerSync — clients queue them locally and upload through **your own backend API**, which writes to Postgres; PowerSync then syncs the result back down (server-authoritative loop). The service repo also lists MongoDB/MySQL source modules ([repo](https://github.com/powersync-ja/powersync-service)).

**License.** `powersync-service` is **FSL-1.1-Apache-2.0**: free to use, copy, modify, and self-host for any "Permitted Purpose" (internal use explicitly included); the prohibition is only on offering a *competing* commercial sync service; each release converts to plain Apache-2.0 two years after that release ([LICENSE file](https://github.com/powersync-ja/powersync-service/blob/main/LICENSE)). For a 3-user hobby app this is unrestrictive in practice, but it is not OSI-approved open source.

**Data model / partial sync.** Clients hold a local SQLite database; the service replicates a per-user subset defined by Sync Streams (recommended) or legacy Sync Rules ([service setup docs](https://docs.powersync.com/self-hosting/installation/powersync-service-setup)). Conflict handling is effectively server-authoritative: your backend API is the arbiter of accepted writes.

**Blobs.** Exactly the pattern issue #4 wants, and it's official: "sync small metadata records through PowerSync while storing actual files in purpose-built storage systems (S3, Supabase Storage, Cloudflare R2, etc.)" — binary data never goes through the sync engine; attachment helpers with background upload/download queues are built into the JS/Web, React Native, Node, Flutter, Swift, Kotlin, and .NET SDKs (older standalone `@powersync/attachments` packages are deprecated in favor of built-ins) ([attachments docs](https://docs.powersync.com/usage/use-case-examples/attachments-files)). On a NAS this maps to MinIO or any S3-compatible container; on-demand/pinnable behavior is the default shape of the helper (download when referenced/requested).

**Clients.** Production status: Flutter, React Native & Expo, JavaScript Web, Kotlin, Swift. Beta: Node.js, .NET, Capacitor. Alpha: Tauri, Rust ([SDK reference](https://docs.powersync.com/client-sdk-references/introduction)). Best mobile story of any candidate.

**Ops @ 3 users.** Highest container count of the realistic options: powersync-service + Postgres + (Mongo or second Postgres for bucket storage) + MinIO + your small API. All deployable as one Docker Compose stack via TrueNAS "Install via YAML" ([TrueNAS custom apps](https://apps.truenas.com/managing-apps/installing-custom-apps/)), but it is the most YAML of any option here.

### 2. Electric (ElectricSQL)

**Current state — important.** Today's Electric is a rewrite: "a read-path sync engine for Postgres" that syncs subsets of Postgres data ("Shapes") to clients over plain HTTP ([intro docs](https://electric.ax/docs/intro), served from the project's docs domain; canonical repo [github.com/electric-sql/electric](https://github.com/electric-sql/electric)). The old batteries-included `electric-sql` client with two-way sync no longer represents the project. The repo is **Apache-2.0**, marked 1.0/stable, and very actively released (`@core/sync-service@1.7.8`, July 2026) ([repo](https://github.com/electric-sql/electric)).

**Writes.** The docs are explicit: "Electric does not do write-path sync. It doesn't provide (or prescribe) a built-in solution for getting data back into Postgres." Their writes guide describes four patterns you implement yourself, from plain online API calls up to "through-the-database sync" with an embedded PGlite ([writes guide](https://electric.ax/docs/guides/writes)). So for an offline-first app with writes from phones, Electric gives you half the engine; the offline write queue, conflict policy, and upload path are on you (or on a companion layer like TanStack DB, listed among its sync integrations).

**Partial sync.** Shapes are exactly partial sync (per-table, where-clause-filtered) ([intro docs](https://electric.ax/docs/intro)).

**Blobs.** Nothing; you'd use the external-object-store pattern regardless.

**Clients.** Official TypeScript client plus framework bindings (React etc.); no official native mobile SDKs — phones would use the web/TS client in a PWA or a hand-rolled client over the HTTP protocol ([repo](https://github.com/electric-sql/electric)).

**Verdict.** Excellent, genuinely open-source read-path tech, but for this app it means building the hardest part (offline writes + conflicts) yourself. Only preferable if a Postgres-centric stack plus DIY write path sounds appealing.

### 3. CouchDB + PouchDB (with RxDB as optional client layer)

**Self-hosting.** Official Apache-maintained Docker image, currently 3.5.x; single container, admin user via env vars, port 5984 ([Docker Hub](https://hub.docker.com/_/couchdb), [image source](https://github.com/apache/couchdb-docker)). By far the lowest ops burden: the database *is* the sync server, auth included.

**Data model / conflicts / partial sync.** Master-master replication between any two CouchDB-protocol databases (including PouchDB in the browser); checkpointed, resumable, continuous replication; conflicts surface as revision-tree branches the app resolves. Selective replication is built in via selector objects or filter functions (selectors recommended for performance) ([replication intro](https://docs.couchdb.org/en/stable/replication/intro.html)). Per-user or per-device databases are the idiomatic partial-sync pattern.

**Blobs/attachments.** CouchDB has native attachments, so it's the one candidate that *could* replicate audio in-band — but its own docs discourage it at size: including attachments in views or the changes feed "is not recommended for large attachment sizes"; base64 encoding in those paths adds ~33% transfer overhead ([views API](https://docs.couchdb.org/en/stable/api/ddoc/views.html), [changes API](https://docs.couchdb.org/en/stable/api/database/changes.html)). `max_document_size` (default 8 MB) excludes attachments, and attachment streaming is separately configured ([config docs](https://docs.couchdb.org/en/stable/config/couchdb.html)). PouchDB supports attachments and recommends Blob/Buffer form over base64 for memory/performance ([attachments guide](https://pouchdb.com/guides/attachments.html)). Practical read: fine for waveform thumbnails or short clips; multi-MB practice recordings still belong in a file store with metadata docs — and note that *not* attaching blobs is also how you get "pinnable" semantics, since normal replication would drag attachments along with their documents.

**Clients.** PouchDB: Apache-2.0, browser-first JavaScript, last release 9.0.0 (June 2024); maintained but slow cadence ([repo](https://github.com/pouchdb/pouchdb)). Phones = PWA (IndexedDB) or community React Native adapters. **RxDB** adds a nicer reactive client layer with a CouchDB replication plugin plus HTTP/GraphQL/custom, WebRTC, and other backends; its protocol is client-resolves-conflicts against an authoritative master ([replication docs](https://rxdb.info/replication.html)). Caution: RxDB core is Apache-2.0 but the storages you'd actually want on mobile/desktop (SQLite, OPFS, IndexedDB) and encryption are **paid**, Pro tier "from $99/month" ([premium page](https://rxdb.info/premium/)) — hard to justify for a 3-user hobby app, so treat RxDB as "free tier with Dexie storage or skip."

### 4. Automerge (automerge-repo + sync server)

**Model.** MIT-licensed CRDT library; concurrent changes merge automatically with full history, git-like branching; core is network-agnostic, with `automerge-repo` supplying storage/network adapters (WebSocket client/server among them) ([docs](https://automerge.org/docs/hello/)). Very actively developed: v3.3.2 released July 2026 ([releases](https://github.com/automerge/automerge/releases)).

**Server.** `automerge-repo-sync-server` is MIT, has a Dockerfile and a ghcr image — but describes itself as "a very simple automerge-repo synchronization server," "an unsecured Express app… partly for demonstration purposes"; last release v0.2.8, July 2024 ([repo](https://github.com/automerge/automerge-repo-sync-server)). Workable behind a VPN for 3 users, but you're adding your own auth story.

**Fit.** Sync granularity is the document; no query language over a large collection, no selective row-level sync, and nothing for blobs (Automerge's own guidance is to keep documents small). Mobile means WASM in a webview/RN or the Rust core's C API for iOS ([docs](https://automerge.org/docs/hello/)). Great for a future collaborative-notes/setlist-editing feature; wrong shape as the app's primary structured store.

### 5. Yjs (Hocuspocus, y-sweet, y-websocket)

**Model.** MIT CRDT framework with shared Map/Array/Text types; state-vector diff sync; extremely widely used; v13.6.31 (May 2026) ([repo](https://github.com/yjs/yjs)). Offline persistence on clients via y-indexeddb.

**Servers.** Best-maintained option is **Hocuspocus**: MIT, self-hostable Node server, `@hocuspocus/extension-sqlite` persistence, auth via `onConnect`/hooks; v4.4.0 released July 2026, very active ([repo](https://github.com/ueberdosis/hocuspocus)). **y-sweet**: MIT Rust server persisting Yjs doc state to filesystem or S3-compatible storage; self-hostable; last release 0.9.1, Sept 2025 — slower pulse, verify before committing ([repo](https://github.com/jamsocket/y-sweet)). `y-websocket` is the minimal reference provider ([Yjs README](https://github.com/yjs/yjs)).

**Fit.** Same structural mismatch as Automerge: document-granular sync, no partial sync within a growing dataset, no blob story (y-sweet's S3 persistence is for *Yjs document state*, not user files). Strong candidate later for real-time collaborative surfaces; not the backbone for practice logs + a recordings catalog.

### 6. Custom SQLite-based sync (cr-sqlite, session extension, roll-your-own)

- **cr-sqlite** (MIT): loadable SQLite extension adding CRDT-based multi-master replication — conceptually the dream (local SQLite that merges). But the last release is **v0.16.3, January 2024**, ~2.5 years ago, and the README warns main may not be stable ([repo](https://github.com/vlcn-io/cr-sqlite)). Dormant; eliminate for new work.
- **SQLite session extension**: official mechanism to record changes into changesets/patchsets and apply them elsewhere, with conflict *callbacks* (omit/abort/apply) you implement; requires declared primary keys; no transport, auth, or ordering framework ([sessionintro](https://www.sqlite.org/sessionintro.html)). It's a building block for a sync engine, not one itself.
- **Roll-your-own server DB + client cache**: always possible, never free. At 2–3 users the engineering cost dwarfs every option above.

---

## Cross-cutting: blob strategy for practice recordings

None of the structured-data sync engines force-replicates large binaries well, and the two that touch binaries at all (CouchDB attachments, PowerSync) both point the same direction: **keep audio out of the sync engine**. The convergent pattern:

1. A `recordings` table/collection syncs everywhere: id, session id, duration, size, codec, checksum, object key, and a per-device "pinned" flag.
2. Bytes live in an S3-compatible object store (MinIO container on the NAS) or a plain filesystem share, fetched over HTTP on demand and cached/pinned locally.
3. Upload is a background queue keyed off the metadata row.

PowerSync ships this as a documented helper ("sync small metadata records through PowerSync while storing actual files in purpose-built storage systems") ([attachments docs](https://docs.powersync.com/usage/use-case-examples/attachments-files)); with any other engine you write the ~same queue yourself. This design *is* the "pinnable, not force-replicated" requirement — pinning is just "download and retain this object key locally."

## Cross-cutting: remote access

Two standard patterns for reaching the TrueNAS box off-LAN:

- **Overlay VPN (recommended at this scale): Tailscale** — WireGuard-based mesh; the free Personal plan covers up to 6 users with unlimited devices, comfortably fitting 2–3 users, and nothing is exposed to the public internet ([pricing](https://tailscale.com/pricing)). Plain WireGuard achieves the same with more manual config.
- **Reverse proxy with public exposure** (Caddy/Traefik/nginx + TLS + auth) — only worth it if a PWA must be reachable from devices you can't enroll in the VPN; otherwise it adds attack surface (and remember the Automerge sync server is explicitly unsecured, and CouchDB warns against exposure before auth is configured ([Docker Hub](https://hub.docker.com/_/couchdb))).

TrueNAS itself runs all of this fine: current TrueNAS uses Docker as the apps backend and supports custom apps installed from Docker Compose YAML ([TrueNAS custom apps docs](https://apps.truenas.com/managing-apps/installing-custom-apps/)).

## Open questions / what to prototype next

1. **PowerSync spike**: Compose stack (powersync-service + Postgres + Postgres-as-bucket-storage + MinIO) on TrueNAS; one synced `practice_sessions` table; measure how much backend-API code the write path actually needs for a 3-user app. Verify Postgres-only bucket storage avoids running MongoDB.
2. **CouchDB counter-spike**: single container + PouchDB PWA; per-user DB + shared DB; recordings as metadata docs + files on a NAS share. Is the PWA experience on phones good enough to skip native SDKs entirely? (This is the main fork in the road: if PWA suffices, CouchDB's one-container simplicity is very compelling.)
3. **Conflict semantics**: for practice logs (mostly append-only per user), how often do real conflicts even occur with 2–3 users? If ~never, server-authoritative (PowerSync) vs revision-tree (CouchDB) vs CRDT matters much less than ops burden.
4. **Auth reality check**: PowerSync needs a JWKS/JWT issuer — what's the lightest self-hosted issuer acceptable here? CouchDB has auth built in.
5. **Watch list**: Electric's ecosystem (TanStack DB) for a maintained off-the-shelf write path, which would change Electric's verdict; y-sweet maintenance pulse before using it for any future collab feature.
