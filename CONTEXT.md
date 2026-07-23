# Practice App

A private practice notebook for 2–3 musicians (sax/jazz focus, instrument-agnostic core). The spine is the practice Session, kept flat and ambient like a paper notebook — never a nested file tree.

## Language

**Practice Surface**:
The app's top level — the room you practice in. The notebook is one thing on it; tuner, metronome, whiteboard, and music player sit beside it within reach, as peers, never nested inside the notebook. "Practice room" is acceptable too.
_Avoid_: dashboard, home screen, workspace

**Session**:
The single day-page holding everything practiced that day. Not a sit-down: one per day, blocks accumulate into it. Capture is ambient — running the timer is the only logging; there is no "I did this" entry ritual.
_Avoid_: practice log, workout, entry

**Block**:
A timed chunk of practice (pomodoro-style, e.g. 25+5 min) within a Session. Usually tied to a practice-menu subject with a goal; may also be free-flowing (untagged). Repeating a block on the same subject is a new block, one tap away.
_Avoid_: task, exercise slot, chunk

**Area**:
A stable top-level practice category (tone, technique, transcription, repertoire…). Small user-editable set; the menu never nests deeper than Area → Subject.
_Avoid_: category, folder

**Subject**:
A specific ongoing thing being practiced under an Area — an etude, a solo transcription, an articulation exercise. Per-instrument by default. The durable identity that attachments (recordings, PDFs) and progress history hang off.
_Avoid_: exercise, item, project

**Practice Routine**:
The daily template: a fixed structure of Areas with time proportions, followed each day. Derived from hours/day available; stable across weeks, changing only on structural shifts (e.g. summer break). May include open time. Grouped by instrument — an instrument section with its blocks under it, not an instrument tag on every block. Optional — a musician can practice without one.
_Avoid_: schedule, plan, rotation

**Focus**:
The week-ish period naming what's being worked on: the current Subjects under each Routine area, plus goals for the period ("what to focus on this week", as after a lesson). Timebase is the musician's — usually a week, never locked to one. Daily goals feed Focus goals. The Focus is the page kept *up* as the guide and through-line of the week; flipping it moves week to week — distinct from the day-by-day Journal, though the two must feel seamless.
_Avoid_: sprint, week, rotation

**Journal**:
The dated record kept on each Session's day page: general thoughts plus per-block notes, written like a notebook entry — something to track today and go on tomorrow. Accumulates forever; block notes tagged to a Subject also appear in that Subject's Progress. "Log" is acceptable too.
_Avoid_: diary

**Whiteboard**:
Undated, present-tense reminders visible on every day page — the wall whiteboard ("SLOW practice", "keep throat open"). General by default, optionally attached to an Area or Subject to surface during matching blocks. Erased when no longer needed; erased means gone, no archive.
_Avoid_: pinned notes, sticky notes

**Progress**:
A Subject's browsable history — dated block notes and attached recordings over time, read like a teacher reviewing an exercise. Not computed metrics; goals (e.g. a BPM target) stay plain text. No trivia stats, no gamification.
_Avoid_: stats, analytics, streaks
