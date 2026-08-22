# Issues 435, 436, 437, 438

All from `AUDIT_PATTERNS_2026-08-21.md`, domain: patterns.

---

## #435 — PAT-2026-08-21-1: `--no-patterns` stub counts `dpcm_sample_map` as events

**Severity:** MEDIUM

**Location:** `main.py:1084` (`detect_patterns_or_direct_export`, direct-export stub)

`direct_size = sum(len(ch) for ch in frames.values())` includes the
`dpcm_sample_map` side table (added by `NESEmulatorCore.process_all_tracks`,
`nes/emulator_core.py:241-247`) in event counts, inflating
`original_size`/`compressed_size`/`total_events` on drum songs in
`--no-patterns` mode. The shared `frames_to_events` extractor
(`nes/emulator_core.py:253-267`) already skips this via `DPCM_SAMPLE_MAP_KEY`
(fixed for #200/#261) but this stub does its own sweep and lacks the guard.

**Suggested fix:** `direct_size = sum(len(ch) for name, ch in frames.items() if name != DPCM_SAMPLE_MAP_KEY)`,
or reuse `len(frames_to_events(frames))`.

---

## #436 — PAT-2026-08-21-2: sampled-space pattern positions fed to loop detection over full event list

**Severity:** MEDIUM

**Location:** `tracker/parser_fast.py:213-239`; interacts with
`tracker/pattern_detector.py:219-222` (internal sampling) and
`tracker/loop_manager.py:138-139` (per-event tempo read)

`parse_midi_to_frames_with_analysis` runs pattern detection (which internally
samples when `len(note_on_events) > max_events=DETECTOR_MAX_EVENTS`) and then
calls `loop_manager.detect_loops(note_on_events, ...)` with the **full**
event list, so persisted `positions` (sampled-space indices) get
mis-dereferenced against the full list in `loop_manager.py:138-139`.

**Impact:** latent — `_with_analysis` variant isn't in the default pipeline.

**Suggested fix:** construct the detector with `max_events=len(note_on_events)`
(no sampling — this is explicitly the "expensive analysis" variant), or check
`was_sampled` and skip/flag loop detection accordingly.

---

## #437 — PAT-2026-08-21-3: `_analyze_pattern_tempo` passes event indices to `get_tempo_at_tick` as ticks

**Severity:** LOW

**Location:** `tracker/pattern_detector.py:479-507` (`_analyze_pattern_tempo`),
`:509-528` (`_analyze_variation_tempos`)

Both call `self.tempo_map.get_tempo_at_tick(tick) for tick in range(pos, pos + length)`
where `pos` is a pattern/event index, not a MIDI tick — the same unit-mismatch
class already fixed in `loop_manager.py:127-139` for #345/TEMPO-16 (which
reads `events[i]['tempo']` directly instead).

Only path where this bites: `parse_midi_to_frames_with_analysis`
(`analyze_tempo=True` + real multi-tempo map). All other call sites pass
`analyze_tempo=False` or a constant map.

**Suggested fix:** mirror the #345 fix — read `events[i]['tempo']` (fallback
to `get_tempo_at_tick` only if key absent).

---

## #438 — PAT-2026-08-21-4: `_WORKER_EVENTS` shipped to every worker process but never read

**Severity:** LOW

**Location:** `tracker/pattern_detector_parallel.py:198-202` (`initargs`),
`:359-368` (`_WORKER_EVENTS` global + `_init_pattern_worker`), `:463-472`
(worker reads only `_WORKER_SEQUENCE`)

Since the #332/PERF-12 rewrite, `_detect_window_groups_worker` only reads
`_WORKER_SEQUENCE`; candidate selection (which needs `events`) now runs in
the parent process. `_WORKER_EVENTS` is assigned but never read anywhere —
dead weight pickled to every spawned worker (up to `MAX_PATTERN_EVENTS` =
15,000 event dicts).

**Suggested fix:** drop `valid_events` from `initargs`, `_init_pattern_worker`'s
signature, and the `_WORKER_EVENTS` global; update the `:356-358` comment.
