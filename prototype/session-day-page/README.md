# Session day-page prototype (wayfinder ticket #8)

**Throwaway prototype — not production code.** Answers: does the Session model feel
like a notebook on screen — flat and ambient, never a dashboard or file tree?

## Run it

Open `prototype/session-day-page/index.html` in any browser (double-click, or):

```
start prototype/session-day-page/index.html
```

Flip variants with the floating bar or the ← → keys, or `?variant=a|b|c`:

| Key | Variant | World |
|-----|---------|-------|
| `a` | Album Side | Blue Note back sleeve — the day as a record side: blocks are the track list, journal is the liner notes, whiteboard is peel-off stickers |
| `b` | Day Page | Teacher's spiral assignment notebook — ruled paper, ballpoint ink, blocks as margin time-stamps inside the day's writing, taped Focus + whiteboard cards |
| `c` | Take Sheet | Studio session tracking sheet — typed take rows, grease-pencil whiteboard, live block as a rolling REC row with tape counter |

Everything is one self-contained file (fonts embedded); no build, no server, no network.
All musical content is synthetic demo state. The running block ticks live; buttons are
stubs (toast: nothing is saved); Variant B's "write here…" line is editable in memory.

Direction contracts for all three variants are in the opening comment of `index.html`
(impeccable seed key `5f5e5b1a`, mode operate).
