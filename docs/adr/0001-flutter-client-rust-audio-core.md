# ADR 0001: Flutter client with Rust audio core

## Status

Accepted (2026-07-23)

## Context

Clients are Mac desktop first, iOS next — and Windows and Android are definite future targets (Mac-first is circumstantial: the primary Windows machine currently lives where practicing isn't possible). [Client stack research](../research/client-stack-comparison.md) compared six stacks and found a cross-cutting constraint: no stack allows the real-time audio path in the UI language's managed runtime; every stack converges on a native C/C++/Rust audio core. The research recommended native Swift/SwiftUI when Android/Windows is "eventual", and Flutter + native core when it is committed.

## Decision

- **UI: Flutter**, one Dart codebase across macOS → iOS → Android → Windows.
- **Audio core: Rust**, bound via `flutter_rust_bridge` / `dart:ffi`. The entire real-time graph — metronome scheduling, tuner DSP, looper time-stretch, recording — lives in Rust. Dart sends control messages and receives async results only; no audio code in Dart.
- Device I/O through **cpal** (CoreAudio / WASAPI / AAudio from one API).
- C++ DSP libraries wrapped where needed; looper time-stretch uses **signalsmith-stretch** (MIT).

## Consequences

- Windows/Android become UI-config work, not rewrites.
- Mac v1 accepts weaker native desktop feel (menus, windowing) than SwiftUI would give.
- Permanent two-language codebase with an FFI boundary to keep in sync (ffigen/flutter_rust_bridge generate the glue; Rust headers are the source of truth).
- On macOS, Dart executables load only signed native libraries — build pipeline must sign the Rust core.
