# Issues 434, 439, 440, 441

## #434 — NH-HW-2026-08-21-8: Arranger's dead `control: 0x81` on triangle frames

**Severity:** LOW · **Domain:** nes-hardware

**Location:** `arranger/pipeline_integration.py:319` (`'control': 0x81,  # Triangle linear counter`)

Both export sinks ignore a triangle frame's `control` key: `export_direct_frames` derives
the `$4008` byte solely from `volume`; `_build_song_bytecode` only extracts duty bits from
it (discarded for channel 2 by the engine). So `0x81` is inert today — but it looks like a
meaningful linear-counter reload (control flag + reload 1, near-instant gate), same
latent-trap shape as the `volume * 7` reload retired under #364/NH-HW-04. The legacy
front-end emits no `control` key for triangle at all — the honest shape.

**Suggested fix:** drop the `control` key from arranger triangle frames (match
`process_all_tracks`' triangle contract), or set it to the engine's real on-value constant
with a comment that consumers must ignore it.

---

## #439 — EXP-2026-08-21-1: Bytecode path retriggers held notes at every 32-frame boundary

**Severity:** MEDIUM · **Domain:** exporters

**Location:** `exporter/exporter_ca65.py:1428-1434` (32-frame chunk split re-emits the same
note byte per chunk); `nes/audio_engine.asm:445-465` (`@is_note` unconditionally resets
`macro_steps_*` and forces `last_written_hi = $FF`)

An event with `dur > 32` can't be expressed as one note in the bytecode format, so the
exporter emits repeated `($6X, note)` pairs. The engine has no "same note continued"
concept: every note byte is a full onset — macro steps reset to 0, `last_written_hi` set to
`$FF` so `$4003`/`$4007` always rewrites next. Rewriting `$4003`/`$4007` restarts the pulse
duty-sequencer phase, so a held pulse note re-clicks every 32 frames (~533ms). Macro restart
also replays each macro's first entries (inaudible today only because every live producer
emits per-event-constant volume/pitch). Direct path (`--no-patterns`) sustains without any
rewrite — the two export paths audibly differ for the same frames input.

**Suggested fix:** add a tie/continue encoding (dedicated `CMD_TIE` or Length-only
continuation chunk); short of a format change, `@is_note` could skip macro-reset and the
`last_written_hi` sentinel when the incoming note equals `current_note, x` (same-note bytes
become idempotent — exactly what the exporter's split means).

---

## #440 — EXP-2026-08-21-2: FamiStudio pattern keys mix global/per-channel counters

**Severity:** MEDIUM · **Domain:** exporters

**Location:** `exporter/exporter_famistudio.py:129` (full patterns keyed by
`f"{channel}_{len(patterns)}"` — global count across ALL channels), `:135` (remainder
pattern keyed by per-channel count), `:167` (`SEQUENCE` emits per-channel 0-based names)

First channel works by coincidence (global == per-channel count). Every subsequent channel:
full patterns get globally-numbered names, remainder gets per-channel-numbered name, and
`SEQUENCE` always references per-channel 0-based names — so `SEQUENCE` for channel 2+
references undefined `PATTERN`s. Also: remainder pattern is always declared `LENGTH 64`
regardless of actual row count.

**Suggested fix:** key full patterns with the per-channel count (same expression the
remainder branch already uses); emit the remainder's real `LENGTH`. Strengthen
`tests/test_famistudio_export.py` to assert every `SEQUENCE` reference resolves to a
defined `PATTERN`.

---

## #441 — EXP-2026-08-21-3: FamiStudio export only recognizes string frame keys

**Severity:** LOW · **Domain:** exporters

**Location:** `exporter/exporter_famistudio.py:101` (`if str(frame) in events:` — no int-key
fallback)

Both CA65 emitters accept int OR str frame keys (in-memory frames carry int keys; JSON
round-trips produce str keys). FamiStudio checks only `str(frame)`, so an in-memory
int-keyed frames dict silently exports all-rest rows. Same divergence class #370 fixed for
`.get()` defaults, one level up (key lookup instead of field lookup).

**Suggested fix:** mirror the CA65 lookup: `event = events.get(str(frame), events.get(frame))`.
