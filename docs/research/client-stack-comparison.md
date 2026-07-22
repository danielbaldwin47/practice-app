# Client stack comparison for practice-app

**Date:** 2026-07-22
**Ticket:** GitHub issue #3
**Status:** Research complete — feeds the v1 spec decision

## Research question

> Which client stacks (native Swift/SwiftUI + portable core, Flutter, Tauri, Electron, Kotlin Multiplatform, React Native) best satisfy: Mac desktop v1, iOS soon after, Android/Windows eventually, Claude-driven maintainability, and pro-audio needs — sample-accurate metronome, real-time tuner DSP, time-stretch/pitch-shift looper, low-latency recording?

All claims below are traced to primary sources (official docs, specs, first-party repos). Citations are inline links; a consolidated source list is at the end. Assessments of LLM-driven maintainability are explicitly marked as analysis, since no primary source quantifies model training data per language.

---

## The one fact that shapes everything

**None of the six stacks lets you write the audio render path in the UI language's managed runtime.** Dart, JavaScript (V8/Hermes), Kotlin (JVM and Kotlin/Native) are all garbage-collected; a GC pause or JIT deopt inside an audio callback is an audible glitch. Even Swift, which uses ARC rather than tracing GC, gets a dedicated "realtime-safe" render-block API from Apple precisely because ordinary Swift code (locks, allocation, ObjC messaging) is not safe on the audio thread ([AVAudioSourceNode exposes `realtimeSafeRenderBlock` initializers](https://developer.apple.com/documentation/avfaudio/avaudiosourcenode)).

Concretely, per platform vendor:

- Android's AAudio docs: *"If your app reads or writes audio data from an ordinary thread, it may be preempted or experience timing jitter. This can cause audio glitches… AAudio executes the callback in a higher-priority thread that has better performance."* ([AAudio guide](https://developer.android.com/ndk/guides/audio/aaudio/aaudio)) — and AAudio/[Oboe](https://github.com/google/oboe) are C/C++ APIs only.
- Apple's audio-workgroup docs: real-time rendering threads must be registered with the OS scheduler — *"Optimize the performance of real-time audio threads that run in sync with the I/O thread by adding them to the audio device workgroup."* ([Workgroup Management](https://developer.apple.com/documentation/audiotoolbox/workgroup-management)) — a C API.
- cpal (Rust): the data callback *"is called by a dedicated, high-priority thread responsible for delivering audio data to the system's audio device in a timely manner."* ([cpal docs](https://docs.rs/cpal/latest/cpal/))

So the real decision is: **every stack ends up with a native audio core in C/C++/Rust (or realtime-disciplined Swift on Apple platforms).** The stacks differ in (a) how good the bridge to that core is, (b) how many platforms the UI layer covers and how well, and (c) how much of the codebase an LLM can work on in one coherent language.

### Where audio cannot run, and the escape hatch, per stack

| Stack | Audio CANNOT run in… | Why | Escape hatch |
|---|---|---|---|
| Swift/SwiftUI | Ordinary Swift on the render thread (locks/allocation/ObjC) | ARC + runtime not RT-safe by default | AVAudioEngine render blocks (incl. `realtimeSafeRenderBlock`), C/C++ core via [Swift C++ interop (Swift 5.9+)](https://www.swift.org/documentation/cxx-interop/) [^apple-rt] |
| Flutter | Dart isolates | Dart GC; FFI callbacks into Dart are thread-restricted (see Flutter section) | Native lib via [`dart:ffi`](https://dart.dev/interop/c-interop); callback stays entirely in C/C++/Rust |
| Tauri | The webview JS frontend | JS engine GC/JIT; webview process boundary | The app **core is already Rust** — run [cpal](https://docs.rs/cpal/latest/cpal/) streams in-process |
| Electron | Main/renderer JS | V8 GC | [AudioWorklet](https://webaudio.github.io/web-audio-api/) (rendering thread, still JS) or a C/C++ [Node-API addon](https://nodejs.org/api/n-api.html) owning the device |
| KMP | Kotlin/JVM (desktop) and Kotlin/Native (iOS) | JVM GC; Kotlin/Native is a concurrent-mark-sweep GC that *"forces a stop-the-world phase"* under allocation spikes ([memory manager docs](https://kotlinlang.org/docs/native-memory-manager.html)) | C/C++ core via JNI (Android/desktop JVM) + [cinterop](https://kotlinlang.org/docs/native-c-interop.html) (iOS — note: *"C libraries import is in Beta"*) |
| React Native | JS (Hermes), even with JSI | JS GC; JSI makes calls cheap, not the callee RT-safe | C++/Swift/Kotlin native module ([TurboModules/JSI](https://reactnative.dev/architecture/landing-page), [Nitro](https://nitro.margelo.com/)) owning the audio thread |

[^apple-rt]: Apple ships explicit APIs for this discipline: `AVAudioSourceNode` provides render blocks as *"a convenient method for delivering audio data instead of setting the input callback on an audio unit"*, including realtime-safe variants ([AVAudioSourceNode](https://developer.apple.com/documentation/avfaudio/avaudiosourcenode)), and audio workgroups register your RT threads with the scheduler ([Workgroup Management](https://developer.apple.com/documentation/audiotoolbox/workgroup-management)).

---

## Summary comparison table

| | Mac desktop v1 | iOS soon after | Android / Windows later | Metronome (sample-accurate) | Tuner DSP (RT input) | Time-stretch looper | Low-latency recording | Portable-core FFI | LLM maintainability (analysis) |
|---|---|---|---|---|---|---|---|---|---|
| **Swift/SwiftUI + portable core** | Excellent — native, first-class ([SwiftUI: macOS 10.15+](https://developer.apple.com/documentation/swiftui)) | Excellent — same frameworks ([AVAudioEngine iOS 8+](https://developer.apple.com/documentation/avfaudio/avaudioengine)) | UI rewrite per platform; core carries over | Excellent — `AVAudioTime` sample time + render-block frame counting | Excellent — input node taps / sink, 256-frame buffers on iOS | Excellent — link C++ libs directly | Excellent — `setPreferredIOBufferDuration` down to ~5 ms/256 frames | Best-in-class: C trivial, C++ official since Swift 5.9 | High: one dominant language, huge corpus; Xcode-only |
| **Flutter** | Good — desktop is stable/first-class ([docs](https://docs.flutter.dev/platform-integration/desktop)) | Good | Best breadth — same codebase | Native core only (via FFI) | Native core only | Native core only | Native core only | Good: `dart:ffi`, no serialization; callbacks can't re-enter Dart on RT thread | Medium-high: Dart + C/C++/Rust two-language split |
| **Tauri** | Good — small native binary, system webview ([Tauri](https://v2.tauri.app/start/)) | Supported in v2 ([prereqs list iOS/Android](https://tauri.app/start/prerequisites/)), younger than desktop | Yes — same Rust core + webview | Excellent in Rust core (cpal callback frame counting) | Excellent — cpal input streams, no GC in core | Good — Rust wrapper for signalsmith-stretch; C++ via FFI | Good — cpal `BufferSize` control; iOS session tuning needs native glue | The core **is** Rust — zero bridge for audio | Medium-high: TS UI (huge corpus) + Rust core (good corpus) |
| **Electron** | Good desktop app platform, heavy runtime ([Chromium+Node bundled](https://www.electronjs.org/docs/latest/)) | **None — Electron is desktop-only** (Windows/macOS/Linux) | Windows yes; Android no | Web Audio is sample-accurate by spec; serious work → N-API addon | AudioWorklet (JS on render thread, GC-risky) or N-API addon | signalsmith-stretch ships an official Web Audio/NPM build | Weakest control of the six; addon required for pro I/O | Node-API: ABI-stable C, threadsafe fns for cross-thread calls | High for JS/TS, but dead-ends the mobile requirement |
| **Kotlin Multiplatform** | OK — Compose Desktop is a JVM app ([stable](https://kotlinlang.org/docs/multiplatform/supported-platforms.html)) | Compose iOS stable since 1.8.0 (May 2025, [JetBrains](https://blog.jetbrains.com/kotlin/2025/05/compose-multiplatform-1-8-0-released-compose-multiplatform-for-ios-is-stable-and-production-ready/)) | Android is home turf; Windows = JVM desktop | Native core only; **two** FFI regimes (JNI + cinterop, cinterop Beta) | Native core only | Native core only | Native core only | Weakest seam story: JNI on JVM targets, Beta cinterop on iOS | Medium: Kotlin corpus good, Compose-MP + KMP build config less represented |
| **React Native** | Riskiest v1: macOS is a [Microsoft fork](https://github.com/microsoft/react-native-macos) tracking upstream (currently v0.81.x) | Excellent — first-party target | Android first-party; Windows = another MS fork | Native module only | Native module only | Native module only | Native module only | Good and improving: JSI direct C++ refs, [Nitro](https://nitro.margelo.com/) codegen for C++/Swift/Kotlin | High corpus (TS/React), but 4 platform forks + native modules = high tooling friction |

---

## 1. Native Swift/SwiftUI + portable core

### Desktop v1 / iOS

SwiftUI is Apple's first-party UI framework for *"every platform"* — macOS 10.15+, iOS 13+ ([SwiftUI](https://developer.apple.com/documentation/swiftui)). The entire audio stack is shared verbatim between macOS and iOS: AVAudioEngine is available on macOS 10.10+ and iOS 8+ ([AVAudioEngine](https://developer.apple.com/documentation/avfaudio/avaudioengine)). A Mac v1 followed by iOS is the path of least resistance: same language, same audio framework, same project. UI code shares heavily but not totally (navigation/window idioms differ between macOS and iOS SwiftUI).

### Pro audio — this is the reference stack the others are measured against

- **Sample-accurate metronome.** `AVAudioTime` represents time *"as audio samples at a particular sample rate"* as well as host time ([AVAudioTime](https://developer.apple.com/documentation/avfaudio/avaudiotime)). Two timer-free designs: (a) schedule click buffers on an `AVAudioPlayerNode` at explicit sample times; (b) synthesize clicks in an `AVAudioSourceNode` render block by counting frames — the source node exists exactly to supply audio *"instead of setting the input callback on an audio unit with `kAudioUnitProperty_SetRenderCallback`"* ([AVAudioSourceNode](https://developer.apple.com/documentation/avfaudio/avaudiosourcenode)).
- **Tuner DSP.** Real-time mic input via the engine's input node; on iOS, `AVAudioSession.setPreferredIOBufferDuration` documents *"The minimum I/O buffer duration is at least 0.005 seconds (256 frames) but might be lower depending on the hardware"* ([setPreferredIOBufferDuration](https://developer.apple.com/documentation/avfaudio/avaudiosession/setpreferrediobufferduration(_:))). 256 frames @ 48 kHz ≈ 5.3 ms per block — ample for a responsive tuner. If the pitch tracker runs on its own thread, register it with the device's audio workgroup so *"the system can schedule them appropriately"* ([Workgroup Management](https://developer.apple.com/documentation/audiotoolbox/workgroup-management)).
- **Time-stretch looper.** All three candidate libraries are C/C++ and link directly: [Rubber Band](https://breakfastquay.com/rubberband/) (C++, *"high quality software library for audio time-stretching and pitch-shifting"*, GPL **or** paid commercial license, explicit real-time mode via `OptionProcessRealTime` ([integration docs](https://breakfastquay.com/rubberband/integration.html))); [signalsmith-stretch](https://github.com/Signalsmith-Audio/signalsmith-stretch) (C++11, MIT, *"Just include `signalsmith-stretch.h`"*, pitch shifts of multiple octaves, stretch sweet spot 0.75x–1.5x); [SoundTouch](https://www.surina.net/soundtouch/) (C++, LGPL 2.1, real-time capable with *"input/output stream latency max. ~100 ms"*). Swift calls C++ directly since Swift 5.9: *"A great variety of C++ APIs can be called directly from Swift"* ([Swift C++ interop](https://www.swift.org/documentation/cxx-interop/)) — no wrapper layer needed for a C++ engine, though interop covers *"a subset of language features."*
- **Low-latency recording.** Input taps or manual rendering on the engine; buffer duration control as above; `AVAudioTime` host/sample timestamps allow compensating round-trip latency when aligning overdubs.
- **Tuner algorithms.** [Q](https://github.com/cycfi/q) (C++, Boost license, lists *"pitch detection"* as a core feature and is *"efficient enough to run on small microcontrollers"*) or [aubio](https://github.com/aubio/aubio) (C, GPL-3.0, *"different pitch detection methods"*) — both link into this stack (mind aubio's GPL).

### Portable core / later platforms

Nothing about this stack prevents putting the engine in C++ (or Rust with a C ABI) from day one; Swift's C interop is trivial and C++ interop official. That core then reuses on Android via [Oboe](https://github.com/google/oboe) (*"a C++ library which makes it easy to build high-performance audio apps on Android"*, choosing AAudio on API 27+) and on Windows via WASAPI or cpal. The **UI** does not carry over — Android/Windows each mean a new UI project. That is real cost, but it is deferred cost, paid only if/when those platforms happen.

### LLM maintainability (analysis)

Swift and SwiftUI are extremely well represented in training corpora; AVFoundation/AVFAudio patterns are idiomatic and heavily documented by Apple. The codebase is one language (plus optionally C++ in the core). Build tooling is Xcode-only — less scriptable than the others but the least configuration surface of any option here. Biggest LLM risk: SwiftUI API churn across OS versions.

---

## 2. Flutter

### Platform coverage

Desktop is stable and first-class: Flutter supports *"compiling a native Windows, macOS, or Linux desktop app"*, with full plugin support on desktop ([Flutter desktop docs](https://docs.flutter.dev/platform-integration/desktop)). One Dart codebase covers Mac v1 → iOS → Android → Windows with the least incremental effort of any stack in this list.

### Pro audio

Dart cannot host the render path. Flutter's own architecture docs lean on Dart's GC (*"fast object instantiation and deletion"… "Dart is particularly well suited for this task"* — [architectural overview](https://docs.flutter.dev/resources/architectural-overview)), which is exactly the property you cannot have on an audio thread. Platform channels serialize every message; the docs recommend FFI instead: *"The foreign function interface (FFI) model can be considerably faster than platform channels, because no serialization is required"* (same page).

The critical constraint is callback direction. `dart:ffi`'s [`NativeCallable`](https://api.dart.dev/stable/dart-ffi/NativeCallable-class.html) has two flavors: `isolateLocal` *"must be invoked from the same thread that created it"* — i.e., never from an OS audio callback — and `listener` *"can be invoked from any thread"* but delivers asynchronously with no return-value mechanism. **Therefore the entire real-time graph — metronome scheduling, tuner analysis, stretch processing, recording — must live in the native library, with Dart only sending control messages and receiving async results.** That is precisely the portable-core pattern: a C/C++/Rust engine (CoreAudio/AVAudioEngine on Apple, [Oboe/AAudio](https://developer.android.com/ndk/guides/audio/aaudio/aaudio) on Android, WASAPI on Windows — or cpal for all of them), bound with `dart:ffi` + ffigen. All four audio requirements are then met by the core exactly as in the Swift stack; Flutter contributes zero audio capability itself but doesn't obstruct it either. One platform-specific note from the Dart docs: *"On macOS, executables… can load only signed libraries"* ([C interop](https://dart.dev/interop/c-interop)).

### LLM maintainability (analysis)

Dart/Flutter is well represented, though less than Swift or TypeScript. The codebase is permanently two-language (Dart UI + C/C++/Rust core) with an FFI boundary an LLM must keep in sync (ffigen helps — headers are the source of truth). Tooling is genuinely good (one `flutter` CLI for five platforms). Widget-heavy Flutter code is verbose but highly idiomatic — LLM-friendly.

---

## 3. Tauri

### Platform coverage

Tauri is *"a framework for building tiny, fast binaries for all major desktop and mobile platforms"* — the app core is Rust, and the UI is any HTML/JS frontend rendered in *"the web view already available on every user's system"* ([Tauri v2](https://v2.tauri.app/start/)). Prerequisites cover macOS 10.15+, Windows 7+, Linux, and — new in v2 — Android and iOS ([prerequisites](https://tauri.app/start/prerequisites/)). Mobile support is real but much younger than desktop; the webview-UI approach on phones is less battle-tested than Flutter/RN.

### Pro audio

This is the only stack whose **default application language is already a no-GC systems language**. The audio engine lives in the Tauri Rust process, no bridge at all:

- [cpal](https://docs.rs/cpal/latest/cpal/) is the cross-platform audio I/O layer: CoreAudio (macOS/iOS), WASAPI + ASIO (Windows), ALSA/JACK et al. (Linux), AAudio (Android), with the data callback on *"a dedicated, high-priority thread."* Buffer size is controllable via the `BufferSize` API. One crate spans every OS this project will ever target.
- **Metronome:** count frames in the cpal output callback; sample-accurate by construction, no timers.
- **Tuner:** cpal input stream feeding a Rust pitch tracker (Rust ports of YIN/MPM exist; or bind C++ [Q](https://github.com/cycfi/q) via FFI). No GC anywhere in the signal path.
- **Looper:** [signalsmith-stretch has an official Rust wrapper](https://github.com/Signalsmith-Audio/signalsmith-stretch) (*"There's a Rust wrapper by Colin Marc"* — linked from the upstream README); Rubber Band and SoundTouch are usable via their C APIs.
- **Recording:** cpal input streams with buffer-size control; on iOS you will still need a little native glue for `AVAudioSession` category/buffer-duration configuration (the session API is iOS-only Objective-C — [setPreferredIOBufferDuration](https://developer.apple.com/documentation/avfaudio/avaudiosession/setpreferrediobufferduration(_:))), reachable from Rust via objc bindings.

Caveats: UI audio (if any preview/playback were done in the webview) varies by system webview — so keep *all* audio in Rust; and cpal is a community project (RustAudio), not vendor-backed, though it wraps the vendor APIs above.

### LLM maintainability (analysis)

Two languages: TypeScript/HTML UI (the single largest LLM corpus) + Rust core (strong corpus, and the compiler catches most LLM mistakes — a real asset for agent-driven maintenance). Tauri-specific glue (commands/events, capability permissions) is a smaller corpus. Webview CSS differences across five platforms are a recurring papercut an LLM handles adequately.

---

## 4. Electron

### Platform coverage — the disqualifier

*"Electron is a framework for building desktop applications"* that embeds *"Chromium and Node.js"* and targets *"Windows, macOS, and Linux"* ([Electron docs](https://www.electronjs.org/docs/latest/)). There is **no iOS or Android story at all**. "iOS soon after" would mean starting a second, unrelated codebase — Electron fails the ticket's platform sequence on its face, regardless of audio merits.

### Pro audio (for completeness)

Chromium's Web Audio implementation follows the [W3C spec](https://webaudio.github.io/web-audio-api/), which explicitly targets *"sample-accurate scheduled sound playback with low latency for musical applications requiring a very high degree of rhythmic precision"* — `start(when)` against `AudioContext.currentTime` is a legitimately sample-accurate, timer-free metronome. AudioWorklet runs processor code on the rendering thread, and mic input arrives via `getUserMedia()` → `MediaStreamAudioSourceNode`. Latency is only *hintable* (`latencyHint`, observable via `baseLatency`/`outputLatency`) — you do not get deterministic buffer-size control from JS. AudioWorklet code is still JavaScript with allocation/GC hazards on the render thread. The pro-grade escape hatch is a [Node-API](https://nodejs.org/api/n-api.html) C/C++ addon (*"ABI stable across versions of Node.js"*, with `napi_threadsafe_function` for calling JS *"asynchronously from multiple threads"*) that owns CoreAudio/WASAPI directly — at which point you've built the portable core anyway, inside the heaviest runtime of the six. Notably, [signalsmith-stretch ships an official Web Audio/NPM release](https://github.com/Signalsmith-Audio/signalsmith-stretch), so a looper prototype is easy here.

### LLM maintainability (analysis)

Best-in-class corpus (TS/Node/Chromium APIs). Irrelevant given the mobile dead end.

---

## 5. Kotlin Multiplatform (+ Compose Multiplatform)

### Platform coverage

Core KMP is stable for Android, iOS, desktop (JVM), and server; Compose Multiplatform (the shared-UI layer) is stable on Android, iOS, and desktop ([supported platforms](https://kotlinlang.org/docs/multiplatform/supported-platforms.html)). KMP itself went stable in Nov 2023 ([JetBrains](https://blog.jetbrains.com/kotlin/2023/11/kotlin-multiplatform-stable/)); Compose for iOS went stable with 1.8.0 in May 2025 ([JetBrains](https://blog.jetbrains.com/kotlin/2025/05/compose-multiplatform-1-8-0-released-compose-multiplatform-for-ios-is-stable-and-production-ready/)). Note the shape of "desktop": Compose Desktop is a **JVM** application — your Mac v1 ships a JVM. Windows later is the same JVM app, which is a genuine plus.

### Pro audio

Kotlin is GC'd on every target: JVM GC on desktop/Android, and on iOS Kotlin/Native's *"concurrent mark and sweep (CMS) collector"* which under allocation spikes *"forces a stop-the-world phase"* ([Kotlin/Native memory manager](https://kotlinlang.org/docs/native-memory-manager.html)). No audio thread in Kotlin, anywhere. The escape hatches are split by target, which is this stack's structural weakness:

- **Android:** JNI to a C++ core using [Oboe](https://github.com/google/oboe)/[AAudio](https://developer.android.com/ndk/guides/audio/aaudio/aaudio) — first-class, this is Kotlin's home platform.
- **Desktop (JVM):** JNI again, to the same C++ core driving CoreAudio (macOS) / WASAPI (Windows).
- **iOS:** Kotlin/Native [cinterop](https://kotlinlang.org/docs/native-c-interop.html) — but *"The C libraries import is in Beta. All Kotlin declarations generated by the cinterop tool from C libraries should have the `@ExperimentalForeignApi` annotation."* Passing Kotlin references to C requires `StableRef`; pointer work is explicitly unsafe.

So the portable C++ core is mandatory *and* bridged through two different FFI regimes (JNI + Beta cinterop), each with its own memory-ownership rules. All four audio requirements are achievable — via the core, same as Flutter — but the seam is the most complex of the six stacks. Also note the ordering mismatch: KMP's stable, mature leg is Android, which is this project's *last* platform; the Mac-v1 leg (Compose Desktop on JVM) delivers a non-native-feeling app with JVM startup/footprint.

### LLM maintainability (analysis)

Kotlin has a strong corpus (Android), but Compose *Multiplatform* specifics, KMP Gradle configuration (a chronic friction point), expect/actual wiring, and cinterop `.def` files are thinner territory. Codebase is Kotlin + C++ + Gradle/Xcode glue — three FFI/build seams for an LLM to keep coherent. Weakest maintainability-per-requirement fit here.

---

## 6. React Native

### Platform coverage

iOS and Android are first-party and excellent. **macOS is not**: it lives in [microsoft/react-native-macos](https://github.com/microsoft/react-native-macos), *"a working fork of facebook/react-native"* maintained by Microsoft, currently tracking React Native at v0.81.x — the desktop v1 would stand on a fork that trails upstream and depends on Microsoft's continued investment. Windows-later is another Microsoft fork (react-native-windows). For a *Mac-desktop-first* product, that inverts RN's strengths: the platform you ship first is the platform RN supports worst.

### Pro audio

The [New Architecture](https://reactnative.dev/architecture/landing-page) (default since RN 0.76) *"removes the asynchronous bridge… and replaces it with JavaScript Interface (JSI). JSI is an interface that allows JavaScript to hold a reference to a C++ object and vice-versa… you can directly invoke methods without serialization costs."* That makes the **control plane** fast and synchronous — but JS on Hermes is still GC'd, so the render path lives in a native module: a C++ (or Swift/Kotlin) audio engine exposed via TurboModules or [Nitro](https://nitro.margelo.com/) (*"statically compiled JSI bindings"*, with codegen producing *"type-safe C++/Swift/Kotlin types from your TypeScript interfaces"*). The engine itself is the same portable core as everywhere else: AVAudioEngine/CoreAudio on Apple targets, Oboe on Android. All four audio requirements are met by the core; RN adds one more moving part per platform (the module registration/codegen layer) times four platforms, two of which are forks.

### LLM maintainability (analysis)

TypeScript/React is the largest UI corpus there is, and Nitro's TS-interface-driven codegen is a good fit for LLM workflows. But the total system — JS + C++ core + Swift/Kotlin adapters + two Microsoft forks + Metro/Gradle/CocoaPods — has the highest tooling-friction surface of the six. RN upgrades across forks are a known recurring cost.

---

## Recommendation

### 1. Native Swift/SwiftUI with a C/C++ portable audio core — recommended

Traced to the requirements:

- **Mac v1 + iOS soon after** are the two platforms Apple's stack serves natively with one codebase and *zero* framework risk — SwiftUI and AVFAudio are first-party on both ([SwiftUI](https://developer.apple.com/documentation/swiftui), [AVAudioEngine](https://developer.apple.com/documentation/avfaudio/avaudioengine)). Every other stack adds a layer between you and the only two platforms that matter for the next year.
- **All four audio requirements have direct, documented first-party APIs**: sample-time scheduling ([AVAudioTime](https://developer.apple.com/documentation/avfaudio/avaudiotime)), realtime render blocks ([AVAudioSourceNode](https://developer.apple.com/documentation/avfaudio/avaudiosourcenode)), 256-frame I/O buffers ([AVAudioSession](https://developer.apple.com/documentation/avfaudio/avaudiosession/setpreferrediobufferduration(_:))), RT-thread scheduling ([workgroups](https://developer.apple.com/documentation/audiotoolbox/workgroup-management)). The stretch libraries are C++ and link directly via [Swift 5.9 C++ interop](https://www.swift.org/documentation/cxx-interop/).
- **Discipline for later platforms:** put metronome scheduling, pitch tracking, looper, and recording buffers in a C++ core (wrapping AVAudioEngine/CoreAudio behind a thin platform layer) from the start. Android later = Oboe backend + new UI; Windows later = WASAPI backend + new UI. The expensive, correctness-critical code moves; only UI is rewritten.
- **Maintainability:** single-language app + one C++ module; the most idiomatic, best-documented territory of the six for LLM-driven work.

The honest cost: Android/Windows each require a new UI later. Given "eventually" in the ticket, deferring that cost is rational.

### 2. Flutter + Rust/C++ core over `dart:ffi` — recommended if Android/Windows are nearer than "eventually"

- Stable, first-class desktop today ([docs](https://docs.flutter.dev/platform-integration/desktop)) and one UI codebase for all four platforms — unbeatable breadth-per-effort.
- The audio story is *identical work* to option 1's portable core (Dart callbacks can never sit on the audio thread — [NativeCallable](https://api.dart.dev/stable/dart-ffi/NativeCallable-class.html)), plus an FFI binding layer, minus per-platform UI rewrites.
- Choose this over option 1 if the Android/Windows timeline compresses; the Mac v1 will be slightly less "Mac-native" and the codebase permanently two-language.

### 3. Tauri v2 + Rust core — credible dark horse, watch mobile maturity

- The only stack where the app's core language is already RT-audio-appropriate (no GC), and [cpal](https://docs.rs/cpal/latest/cpal/) covers every target OS with one API including buffer-size control. The signalsmith-stretch Rust wrapper covers the looper with an MIT license.
- Held back from a top slot by the youth of Tauri mobile (v2-era) and webview-based UI on phones for a gesture-heavy music tool; iOS audio-session tuning still needs native glue.

**Not recommended:** Electron (desktop-only — fails "iOS soon after" outright, [docs](https://www.electronjs.org/docs/latest/)); KMP (its mature leg is the last platform on the roadmap, JVM-desktop Mac v1, and the most complex FFI story — Beta [cinterop](https://kotlinlang.org/docs/native-c-interop.html) + JNI); React Native (Mac v1 on a [Microsoft fork](https://github.com/microsoft/react-native-macos) inverts RN's strengths for this platform ordering).

### Decision hinge for the v1 spec

Pick between #1 and #2 on one question: **how real is the Android/Windows timeline?** "Eventually / maybe" → Swift + C++ core. "Committed within ~18 months" → Flutter + Rust/C++ core. In both cases, the v1 spec should mandate the portable core boundary now: **no metronome scheduling, DSP, or recording logic in the UI language.**

---

## Sources

**Apple (first-party)**
- AVAudioEngine — https://developer.apple.com/documentation/avfaudio/avaudioengine
- AVAudioSourceNode — https://developer.apple.com/documentation/avfaudio/avaudiosourcenode
- AVAudioTime — https://developer.apple.com/documentation/avfaudio/avaudiotime
- AVAudioSession.setPreferredIOBufferDuration — https://developer.apple.com/documentation/avfaudio/avaudiosession/setpreferrediobufferduration(_:)
- Workgroup Management (audio workgroups) — https://developer.apple.com/documentation/audiotoolbox/workgroup-management
- SwiftUI — https://developer.apple.com/documentation/swiftui
- Swift C++ interoperability — https://www.swift.org/documentation/cxx-interop/

**Flutter / Dart (first-party)**
- Desktop support — https://docs.flutter.dev/platform-integration/desktop
- Architectural overview (platform channels, FFI, Dart GC) — https://docs.flutter.dev/resources/architectural-overview
- C interop with dart:ffi — https://dart.dev/interop/c-interop
- NativeCallable API — https://api.dart.dev/stable/dart-ffi/NativeCallable-class.html

**Tauri / Rust**
- Tauri v2 overview — https://v2.tauri.app/start/
- Tauri prerequisites (desktop + iOS/Android targets) — https://tauri.app/start/prerequisites/
- cpal (RustAudio) — https://docs.rs/cpal/latest/cpal/

**Electron / Node / Web**
- Electron docs (scope: Windows/macOS/Linux) — https://www.electronjs.org/docs/latest/
- Node-API — https://nodejs.org/api/n-api.html
- Web Audio API spec (W3C editor's draft) — https://webaudio.github.io/web-audio-api/

**Kotlin (first-party)**
- KMP supported platforms & stability — https://kotlinlang.org/docs/multiplatform/supported-platforms.html
- Kotlin/Native C interop — https://kotlinlang.org/docs/native-c-interop.html
- Kotlin/Native memory manager (GC) — https://kotlinlang.org/docs/native-memory-manager.html
- KMP stable announcement (Nov 2023) — https://blog.jetbrains.com/kotlin/2023/11/kotlin-multiplatform-stable/
- Compose Multiplatform 1.8.0, iOS stable (May 2025) — https://blog.jetbrains.com/kotlin/2025/05/compose-multiplatform-1-8-0-released-compose-multiplatform-for-ios-is-stable-and-production-ready/

**React Native**
- New Architecture (JSI, TurboModules) — https://reactnative.dev/architecture/landing-page
- react-native-macos (Microsoft fork) — https://github.com/microsoft/react-native-macos
- Nitro Modules — https://nitro.margelo.com/

**Android audio (first-party)**
- AAudio NDK guide — https://developer.android.com/ndk/guides/audio/aaudio/aaudio
- Oboe (Google) — https://github.com/google/oboe

**DSP libraries (official project pages/repos)**
- Rubber Band Library — https://breakfastquay.com/rubberband/ ; integration/real-time modes — https://breakfastquay.com/rubberband/integration.html
- signalsmith-stretch — https://github.com/Signalsmith-Audio/signalsmith-stretch
- SoundTouch — https://www.surina.net/soundtouch/
- Q DSP library (Cycfi) — https://github.com/cycfi/q
- aubio — https://github.com/aubio/aubio
