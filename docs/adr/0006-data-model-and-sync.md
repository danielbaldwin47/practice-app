# ADR 0006: Data model and sync rules for the practice domain

## Status

Accepted (2026-07-23)

## Context

The domain model (CONTEXT.md: Routine → Focus → Session, Area → Subject, Journal vs Whiteboard, Progress) needs concrete schemas: Postgres source tables, the client SQLite shape via PowerSync (ADR 0002), per-user Sync Streams, and the recordings metadata table. Later specs added requirements: per-Subject tool memory and take metadata (sound tools spec, #6), and the librarian's card catalog, aliases, and link storage (AI auto-linking, #14). Decided via grilling on ticket #17.

## Conventions

- **Primary keys**: client-generated UUIDs (`TEXT` in SQLite, `uuid` in Postgres). Offline-first clients must mint ids without the server.
- **`user_id` on every synced table**, denormalized. PowerSync data queries cannot join, so the per-user stream filter needs the column on each table directly.
- `created_at` / `updated_at` timestamps on every table.
- **Postgres is the source of truth**; the client SQLite schema mirrors it 1:1 via PowerSync. Writes go through the TS API (server-authoritative, ADR 0003); PowerSync syncs results back down.
- **Text format**: notebook texts (journal, block notes, goal lines, whiteboard) are plain text with light markdown conventions. Inline entity references embed as `[[type:uuid]]` tokens rendered as chips; a dangling token renders as plain text. No rich-text documents.
- **Deletes are hard** (FK cascades), with one exception: Subjects archive (`archived_at`) instead of deleting, because Progress history, takes, and links hang off them. Archiving hides a Subject from menus and pickers; history stays browsable. Deleting a take or material also queues deletion of its MinIO object via the API.

## Tables

### Menu & structure

| Table | Columns (beyond id/user_id/timestamps) | Notes |
| --- | --- | --- |
| `instruments` | `name`, `transposition_semitones`, `sort` | Tuner transposition follows the active instrument. |
| `areas` | `name`, `sort` | One per-user list, shared across instruments. |
| `subjects` | `area_id` FK, `instrument_id` FK **nullable**, `name`, `archived_at` nullable, `sort` | Null instrument = instrument-agnostic ("per-instrument by default"). |
| `routines` | — | One active routine per user; edited in place, no versioning (Sessions record what actually happened). |
| `routine_sections` | `routine_id` FK, `instrument_id` FK nullable, `sort` | The instrument grouping. |
| `routine_items` | `section_id` FK, `area_id` FK **nullable**, `minutes`, `sort` | Null area = open time. Concrete minutes, not percentages; "derived from hours/day" happens at edit time. |

### Week & day

| Table | Columns | Notes |
| --- | --- | --- |
| `focuses` | `starts_on` date | Open-ended; closed by the next Focus starting. Timebase is the musician's. |
| `focus_subjects` | `focus_id` FK, `area_id` FK, `subject_id` FK, `sort` | "What's on the stand this week" — drives the week page directly. |
| `focus_goals` | `focus_id` FK, `text`, `sort` | One row per goal line; line identity is what chips attach to. |
| `sessions` | `date`, `journal_text` | Unique `(user_id, date)` — one day-page. General journal is one flowing text column. |
| `blocks` | `session_id` FK, `subject_id` FK nullable, `focus_goal_id` FK nullable, `goal` text, `planned_minutes`, `started_at`, `duration_seconds`, `note`, `sort` | Null subject = free block. `focus_goal_id` gives chip inheritance when created from a Focus line. Aggregate time only: pause/resume/end-early are runtime behaviors that accumulate `duration_seconds` — no segment log (that's trivia-stats territory). |
| `whiteboard_notes` | `text`, `area_id` FK nullable, `subject_id` FK nullable, `sort` | Hard delete — erased means gone. |

### Audio & tools

| Table | Columns | Notes |
| --- | --- | --- |
| `recording_takes` | `session_id` FK, `block_id` FK nullable, `subject_id` FK nullable, `duration_ms`, `codec`, `checksum`, `object_key`, `pinned`, `starred`, `note`, `bpm` nullable, `trim_start_ms` nullable, `trim_end_ms` nullable | ADR 0002 metadata plus #6 additions. `pinned` is **global** (synced): pin = keep offline everywhere; revisit if iOS storage pressure appears. `bpm` stamped from a running metronome. Trim is non-destructive bounds. Auto-tagged to the active block's Subject, one-tap override. |
| `tool_settings` | `subject_id` FK **nullable**, `tool` (`'metronome'`, `'tuner'`, …), `settings` JSON text | Unique `(user_id, subject_id, tool)`. Null subject = the standalone slot — no pseudo-Subject rows polluting the menu. JSON because metronome state is deep and evolves with the tool. |

### Library & player

| Table | Columns | Notes |
| --- | --- | --- |
| `folders` | `parent_id` FK nullable, `name`, `sort` | Self-referencing tree, nests freely. The flatness rule protects the notebook, not the cabinet. First run seeds ordinary editable folders (Backing Tracks, Transcription Sources, Sheet Music & Books) — no separate "sections" concept, no settings surface. |
| `materials` | `folder_id` FK nullable, `kind` (`audio`/`pdf`/`other`), `title`, `source` (`local`/`purchased`/`youtube`), `object_key`, `checksum`, `duration_ms` nullable, `page_count` nullable, `scan_status` (`none`/`pending`/`done`/`failed`) | Bytes in MinIO via the attachment pattern, same as takes. |
| `subject_materials` | `subject_id` FK, `material_id` FK | Attachments are references (#5). |
| `loops` | `material_id` FK, `label`, `a_ms`, `b_ms`, `speed_percent`, `pitch_semitones`, `pitch_cents`, `sort` | Saved A–B loops with notes and per-loop key/tempo stepping. |
| `playlists` / `playlist_items` | `name`, `sort` / `playlist_id` FK, `material_id` FK, `sort` | v1 playlists. |
| `patterns` | `name`, `material_id` FK nullable, `clip_a_ms` nullable, `clip_b_ms` nullable, `wendel_checks` | Fed by looper-region clipping; name is the librarian's matching handle. `wendel_checks` is a 6-bit bitmask for the optional, unenforced Wendel cross-off boxes. |

### Librarian (#14)

| Table | Columns | Notes |
| --- | --- | --- |
| `catalog_entries` | `material_id` FK, `name`, `page_start` nullable, `page_end` nullable, `origin` (`scan`/`user`), `sort` | The card catalog: per-material contents index. Import-time AI scan writes `origin='scan'`; the Contents tab is the repair surface (`origin='user'`). |
| `aliases` | `alias_text`, target FKs: `subject_id` / `material_id` / `catalog_entry_id` / `pattern_id` (all nullable, CHECK exactly one) | Per-user learned aliases from corrections; local-first, synced. |
| `entity_links` | source FKs: `focus_goal_id` / `block_id` (nullable, CHECK exactly one); target FKs: `subject_id` / `material_id` / `catalog_entry_id` / `pattern_id` (nullable, CHECK exactly one); `origin` (`auto`/`manual`), `matched_text` | The chips. Real FKs so chips cascade away with their line or target; `matched_text` kept for the repair surface. Chip ≠ text mutation — the link is metadata beside the line. |

### Local-only (client, outside sync)

- PowerSync attachment-queue state (SDK-managed).
- In-flight timer state for the running block.

## Sync Streams

**One stream per user**: every synced table filtered by `user_id = token.user_id`, full history included. Metadata rows are text and numbers; years of practice is megabytes. Every surface (Progress history, Library, catalog matching) is always fully local — no partial-data edge cases. The spike (#19) verified this topology healthy on the NAS.

Audio bytes never enter sync: takes and materials use the attachment pattern (ADR 0002) — metadata rows sync, bytes live in MinIO, fetched on demand and cached/pinned via the SDK attachment queue.

**MinIO key convention**: `user/{user_id}/takes/{take_id}.{ext}` and `user/{user_id}/materials/{material_id}.{ext}`.

## Import-scan pipeline (#14)

Server-side, in the TS API: material upload → `scan_status='pending'` → one LLM call per import → insert `catalog_entries` with `origin='scan'` → `done`. On `failed`, the material gets book-level entries only (title-level match still works). Named Pattern Book patterns are auto-enrolled as matching handles directly (patterns are a link target themselves — no catalog duplication).

## Consequences

- Every table carries `user_id`, even join-shaped ones — the price of join-free PowerSync stream filters.
- Client-minted UUIDs mean the API validates ids on write rather than issuing them.
- Archiving is the only soft state; nothing else needs `deleted_at` filtering, and Whiteboard's "erased means gone" holds.
- The `entity_links` / `aliases` CHECK-constrained FK fan means adding a new link-target type is a migration — accepted for referential integrity.
- Glossary additions (Library, Material, Take, Loop, Pattern Book, Chip/Token) recorded in CONTEXT.md alongside this ADR.
