# Batch fix: #334, #335, #336, #337

Fetched via `gh issue view 334 335 336 337 --repo matiaszanolli/midi2nes --json title,body,labels,state`.
Immutable snapshot as filed — GitHub is authoritative for current state.

## #334 — PERF-14: LARGE_FILE_THRESHOLD is hardcoded, advisory-only, and not aligned with the two configurable sampling caps
Labels: bug, low, performance
Source: AUDIT_PERFORMANCE_2026-07-18.md

`MAX_PATTERN_EVENTS` (15000, parallel) and `DETECTOR_MAX_EVENTS` (1000, sequential) are
overridable via `processing.pattern_detection.max_events`/`max_pattern_events` (#219,
`get_pattern_detection_caps`). But `LARGE_FILE_THRESHOLD = 10000` is a bare inline literal
in `run_full_pipeline` (`main.py:861`), has no `default_config.yaml` key, and is purely
advisory (prints a hint, changes no behavior). Suggested fix: move it into
`default_config.yaml` alongside the other caps and align its default with the parallel cap,
or delete the advisory branch.

## #335 — PERF-15: Redundant EnhancedTempoMap construction + events->frames->events round-trip across pipeline sites
Labels: bug, low, performance
Source: AUDIT_PERFORMANCE_2026-07-18.md

`run_detect_patterns` and `run_full_pipeline` each construct a bare
`EnhancedTempoMap(initial_tempo=500000)`; `parse_midi_to_frames_with_analysis` re-opens the
MIDI file and rebuilds the map after already parsing once. No output impact — cheap
redundant allocation only. Suggested fix marked **optional**: cache the first-pass tempo map
in `parse_midi_to_frames_with_analysis`; otherwise leave as-is.

## #336 — PERF-16: MemoryMonitor reports peak_mb=0 for sub-interval work and silently swallows sampling errors
Labels: bug, low, performance
Source: AUDIT_PERFORMANCE_2026-07-18.md

`_monitor_loop` appends a sample then sleeps `interval_ms`; if `stop_monitoring` runs before
the daemon thread's first loop iteration, `_memory_samples` is empty and a misleading
`peak_mb=0` is returned. The loop wraps its body in `except Exception: break`, discarding
any sampling error. Suggested fix: seed `_memory_samples` with an immediate RSS read in
`start_monitoring`; log/count swallowed sampling exceptions instead of a bare `break`.

## #337 — REG-18: dpcm_sampler/dpcm_converter.py has 0% test coverage — WAV->DMC encoder emits NES sample bytes untested
Labels: bug, medium, regression
Source: AUDIT_REGRESSION_2026-07-18.md

`convert_wav_to_unsigned_pcm`, `delta_encode`, `dpcm_compress`, `convert_wav_to_dmc` have
zero test references and 0% coverage. Non-trivial DSP: `delta_encode` produces reconstructed
7-bit values clamped to `[0,127]` with ±1 steps; `dpcm_compress` re-derives 1-bit deltas and
truncates at `dmc_bytes[:4081]`. Standalone asset-prep CLI, not wired into the automated
pipeline (checked-in `.dmc` files are what ships), but it's the only producer of those bytes.
Suggested fix: add `tests/test_dpcm_converter.py` pinning PCM conversion, exact
`delta_encode`/`dpcm_compress` byte output, and the 4081-byte cap.
