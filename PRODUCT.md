# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

_(Inferred mapping: the real client is Flutter desktop (Mac first, iOS next) with fully custom-drawn UI — no native design language to inherit. HTML prototypes stand in for Flutter surfaces during the spec phase.)_

## Users

2–3 fully private users (the developer and family). Primary user: a jazz saxophonist practicing daily at home, notebook on the music stand, tools (metronome, tuner, recorder) within reach. Multi-instrument per user is in scope. No sharing, teacher, or collaboration features — ever.

## Product Purpose

A private practice notebook. The spine is the practice **Session** — one day-page per day, holding timed Blocks, journal notes, and ambient state. Success: capture happens as a side effect of practicing (running the timer is the only logging), and the accumulated record reads like a musician's paper notebook a teacher could browse.

## Positioning

Against practice-tracker apps: no gamification, no streaks, no computed stats, no nested file trees. The app is a **Practice Surface** — the room you practice in — where the notebook is one object among peers (tuner, metronome, whiteboard, player), never a dashboard.

## Operating Context

Daily home practice, structured as timed Blocks (pomodoro-style, e.g. 25+5) drawn from a practice menu (Area → Subject, never deeper). A weekly-ish **Focus** page names current Subjects and goals; the **Whiteboard** holds undated present-tense reminders visible on every day page. Journal entries accumulate forever; block notes tagged to a Subject also appear in that Subject's Progress history.

## Capabilities and Constraints

- Domain vocabulary is binding — see `CONTEXT.md` (Practice Surface, Session, Block, Area, Subject, Routine, Focus, Journal, Whiteboard, Progress) including its _Avoid_ lists.
- Sessions are unique per (user, date); Blocks aggregate time only; capture is ambient — no "I did this" entry ritual.
- v1 feature cut: session core (journal, timer, weekly notebook, whiteboard) + sound tools (metronome, tuner, recorder) + transcription suite (looper, pattern book, backing tracks).
- Stack: Flutter UI + Rust audio core; PowerSync/SQLite offline-first sync (ADRs 0001–0006).
- Undecided (this prototype's question): what the Session day-page looks like — whether the model *feels* like a notebook on screen.

## Brand Commitments

Flat and ambient, like a paper notebook — never a nested file tree, never a dashboard. No trivia stats, no gamification, no streaks. Progress is browsable history read like a teacher reviewing an exercise.

## Product Principles

1. Capture is ambient — the timer is the logger; writing is optional and welcome.
2. Flat like paper — a day is one page; depth never exceeds Area → Subject.
3. Tools are peers in the room, not features nested in a hierarchy.
4. The record is prose and takes, not metrics — plain-text goals, no charts of practice time.
5. Private by construction — 2–3 known users, no audience-facing surface anywhere.
