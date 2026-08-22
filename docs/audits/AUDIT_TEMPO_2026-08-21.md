# Tempo & Frame-Timing Audit — 2026-08-21

## 1. Summary

**Invariant verdict: PASS.** Frame timing stays on the 60Hz grid on the live MIDI→ROM
path. The keystone conversion
`get_frame_for_tick(tick) = round(calculate_time_ms(0, tick) / FRAME_MS)`
(`tracker/tempo_map.py:209-212`) measures time **absolutely from tick 0** on every call
via the bisect-based cumulative-ms index (`_build_tempo_index` / `_cumulative_ms`,
`tracker/tempo_map.py:140-177`), so rounding error is bounded at ±0.5 frame per note and
does not accumulate. This round the invariant was re-verified **empirically**, not just
by code reading (script at /tmp/audit/tempo_checks.py, run against the working tree):

- **Drift**: a 5-minute song at 120 BPM/480 PPQ lands its final tick on frame 18000
  exactly (expected `total_ms/FRAME_MS` = 18000.0, delta 0.0); the max
  `|time − frame·FRAME_MS|` over 2400 evenly-spaced notes is 8.333 ms = exactly the
  half-frame bound. No error growth with song length.
- **Multi-tempo exactness**: a 3-segment map (120→240→60 BPM) totals 17500.0 ms against
  a hand-computed 17500; the identity
  `calculate_time_ms(a,b) == cumulative(b) − cumulative(a)` held to <1e-9 ms over 200
  random spans; a tempo change is effective at its own tick
  (`get_tempo_at_tick(4800)==new`, `(4799)==old`) and contributes no time before it.
- **Duplicate same-tick changes**: last-inserted wins regardless of numeric tempo value
  (tick-only stable sort, `tracker/tempo_map.py:127-138` + `bisect_right`; #210 holds).
- **Cache/index invalidation**: `get_frame_for_tick` returns the updated frame after
  every mutation path exercised — base `add_tempo_change`, `EnhancedTempoMap`'s
  tick-0 in-place replacement (`tracker/tempo_map.py:296-301`), and a mid-song add.
  No stale `_time_cache`/`_tempo_index` value observed.
- **Rounding bias**: 1000 constructed exact half-frame ties split 491 down / 509 up —
  banker's rounding does not systematically bias one direction.
- **Guards**: `TempoMap(initial_tempo=0)` and `EnhancedTempoMap(initial_tempo=0)` both
  raise `TempoValidationError` (#383/#317); `ticks_per_beat` of 0 or negative raises
  `ValueError` (#93/#95). `calculate_time_ms` stays finite at 10^12 ticks at 1 BPM
  (float64 headroom, no overflow).
- **Frame edges**: tick 0 → frame 0 (short-circuit + `_cumulative_ms(0)==0.0`);
  `compile_channel_to_frames`'s `range(start_frame, end_frame)`
  (`nes/emulator_core.py:106`) emits the last sounding frame with `end_frame` derived
  from the real note-off where paired (#160).

**Code churn since the 2026-08-07 audit is nil in this subsystem.** `git log
--since=2026-08-07` over `tracker/tempo_map.py`, `tracker/parser_fast.py`,
`tracker/loop_manager.py`, `nes/emulator_core.py`, `constants.py`, `main.py`,
`tracker/parser.py` shows only c864426 (the song-bank feature, which the 08-07 audit
already reviewed and cleared: `midi_to_frames_for_song` calls the same
`parse_midi_to_frames`, no new tick→frame math). The three commits since (949f0c6,
ffccf51, 8ea7ac3) touch drum mapping, project-builder/song-bank plumbing, and audit
skill prose — none of the audited timing code. All prior TEMPO-xx issues (#93-#99,
#208-#211, #259/#260, #317, #344/#345, #382/#383, #396) remain CLOSED with their fixes
confirmed present in the current source; **no open issue exists in the repo at all**.

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 1 (1 NEW — audit-tooling doc-rot, not
a code defect).

**Highest-leverage fix:** run /audit-sync to retire the stale Dimension-4 prose in the
audit-tempo skill (finding TEMPO-2026-08-21-1) — the only inaccuracy left in the
subsystem is in its own audit instructions, which now describe a fixed bug as live and
will keep costing each future audit a re-derivation pass.

## 2. Findings

### TEMPO-2026-08-21-1: audit-tempo skill prose still describes the fixed `--with-analysis` silent tempo-drop as a live residual
- **Severity**: LOW
- **Dimension**: Dimension 4 (Extreme Tempo Bounds) — meta/doc-rot
- **Location**: `.claude/commands/audit-tempo/SKILL.md:95-99` (D4 bullet 2); stale line
  refs also at `:135` (D6 intro)
- **Status**: NEW (noted as stale prose in the 2026-08-07 audit's coverage notes but
  never filed; no matching issue in /tmp/audit/issues.json)
- **Description**: The skill's Dimension 4 instructs auditors that
  `parse_midi_to_frames_with_analysis` "rebuilds its own tempo map (lines ~166-177) and
  still has a bare `except TempoValidationError: continue` (lines ~186-189) with no
  counting/warning, unlike the fixed default-path parser." That code no longer exists:
  since the #335/PERF-15 refactor, both entry points share
  `_parse_frames_and_tempo_map` → `_build_tempo_map`
  (`tracker/parser_fast.py:24-67, 70-110, 192-201`), so the analysis path gets the same
  count-and-warn drop handling (#94) and the same real `ticks_per_beat` — exactly what
  #259/TEMPO-12 and #260/TEMPO-13 (both CLOSED) fixed. The skill also cites the
  `EnhancedLoopManager` instantiation at "line ~193"; it is at
  `tracker/parser_fast.py:209`. Two consecutive audits (2026-08-07 and this one) have
  now spent a verification pass re-disproving the same retired defect, and the
  2026-08-07 skill-refresh commit (949f0c6) updated 13 sibling SKILL.md files while
  leaving this one stale.
- **Evidence**: `.claude/commands/audit-tempo/SKILL.md:97` ("still has a bare `except
  TempoValidationError: continue` (lines ~186-189)") vs. `tracker/parser_fast.py`,
  where `grep -n 'except TempoValidationError'` matches only inside the shared
  `_build_tempo_map` (line 56), whose handler counts and warns (lines 56-65). Last
  audit-tempo skill sync: 85c50b3, which predates the shared-helper refactor's
  documentation state.
- **Impact**: No effect on any ROM or pipeline stage — audit-process cost only: wasted
  re-derivation each cycle and risk that a future auditor "re-confirms" and files the
  retired defect as a regression.
- **Related**: #335/PERF-15, #259/TEMPO-12, #260/TEMPO-13 (all CLOSED — the fixes the
  prose predates); 2026-08-07 tempo audit D3 coverage note (first flagged the
  staleness).
- **Suggested Fix**: Run /audit-sync on the audit-tempo skill to rewrite the D4 bullet
  as a verify-the-fix item (shared `_build_tempo_map`, #259/#260 closed) and refresh
  the D6 line references.

## 3. Cross-Audit Dedup

- **`_analyze_pattern_tempo` unit mismatch (sibling of #345/TEMPO-16)** — confirmed
  independently this round: `tracker/pattern_detector.py:479-507`
  (`_analyze_pattern_tempo`) and `:509-528` (`_analyze_variation_tempos`) still pass
  event-list indices to `get_tempo_at_tick` as if they were MIDI ticks, the exact
  defect class #345 fixed in `EnhancedLoopManager` by reading each event's stamped
  `tempo` field (`tracker/loop_manager.py:127-139`). Inert on the default pipeline
  (both `main.py` detector sites pass `analyze_tempo=False` or a flat single-entry
  map); wrong-but-unconsumed metadata on the opt-in `--with-analysis` path only.
  **Filed today as PAT-2026-08-21-3 (LOW) in `docs/audits/AUDIT_PATTERNS_2026-08-21.md`**
  — deduplicated there per protocol, not double-reported here.

## 4. Dimension Coverage Notes

- **D1 (tick→frame drift)**: Clean — empirically verified this round (Summary bullets
  1-4). `calculate_time_ms(0, tick)` is exact via
  `_cumulative_ms(end) − _cumulative_ms(start)` over one shared segmentation; per-segment
  math in `np.float64` with no int truncation (`tracker/tempo_map.py:140-159`); every
  mutation path clears both `_time_cache` and `_tempo_index` (`:127-138`, `:300-301`,
  `:376-377`, `:731-739`), with the `_get_tempo_index` length backstop (`:161-167`) as
  defense-in-depth.
- **D2 (multi-tempo)**: Clean. Per-track `current_tick` reset
  (`tracker/parser_fast.py:45, 118`) matches MIDI track-local delta-time semantics —
  each track's `set_tempo` lands at its correct absolute tick. Segment boundaries
  inclusive-at-change-tick, consistent between `_build_tempo_index` and
  `_cumulative_ms`/`get_tempo_at_tick` (`bisect_right − 1`), verified empirically.
  The FRAME_ALIGNED tick re-snap in `add_tempo_change`
  (`tracker/tempo_map.py:321-362`) remains unreachable: both live
  `add_tempo_change` call sites (`tracker/parser_fast.py:51`, `tracker/parser.py:47`)
  construct their maps with `optimization_strategy=None`.
- **D3 (defaults)**: The two `main.py` analysis-only maps (`main.py:749`, `:1115`)
  remain inert and now carry the #98/#376 documentation comments — per the skill, not
  re-filed. Missing `set_tempo` correctly falls back to `(0, 500000)` = 120 BPM.
  `initial_tempo<=0` raises `TempoValidationError` in both classes before any division
  (verified empirically, C6).
- **D4 (extreme bounds)**: Widened 1-2000 BPM / ratio-∞ config
  (`tracker/parser_fast.py:103-109`) intact; drops counted and warned to stdout
  (`:63-65`). Same-frame collapse (#96) with later-event tie-break (#344) confirmed at
  `nes/emulator_core.py:38-42`. No `_frame_times` or any other fixed frame-count cap
  (grep: none). No float64 overflow (C8). The skill's claim of a residual bare
  `except ... continue` in the analysis path is stale → finding TEMPO-2026-08-21-1.
- **D5 (PPQ)**: Both guards agree at `< 1` (`tracker/parser_fast.py:89-94`,
  `tracker/tempo_map.py:101-107`); no construction path bypasses `TempoMap.__init__`
  (only subclass is `EnhancedTempoMap`, which calls `super().__init__`; no direct
  `self.ticks_per_beat =` assignment outside it). `tracker/parser.py:30-35` passes the
  real `ticks_per_beat` (#396 fixed, re-read directly).
- **D6 (loops)**: `EnhancedLoopManager` reachable only from
  `parse_midi_to_frames_with_analysis` (`tracker/parser_fast.py:209`) and the test-only
  `tracker/parser.py:84`. Stamped-tempo reads (`tracker/loop_manager.py:138-139`, the
  #345 fix) intact; `end` handled as an exclusive index consistently
  (`events[end − 1]` for tempo, `positions[-1] + length ≤ len(events)` so no
  out-of-range read); jump-table key format matches between writer and reader
  (`loop_{end}_{start}`, `:141` / `:167`).
- **D7 (optimization fidelity)**: `optimize_tempo_changes` /
  `_smooth_tempo_transitions` / `_minimize_tempo_changes` / `_align_to_frames` still
  have zero callers outside `tracker/tempo_map.py` and tests (grep: none); #97 WARNING
  docstrings in place (`:622-637`, `:709-720`). Dead on the live path; not re-filed.
- **D8 (frame edges)**: Tick 0 → frame 0 (C7). Last frame emitted by
  `range(start_frame, end_frame)` with note-off-paired `end_frame`
  (`nes/emulator_core.py:79-97, 106`). All three alignment verdict predicates
  (`is_frame_aligned:274-279`, `_validate_frame_boundaries:488-502`,
  `_check_frame_alignment:881-898`) delegate to the same symmetric nearest-boundary
  test on true cumulative time (#382 fix intact — re-read all three). The
  `add_tempo_change` re-snap's separate 1.0/2.0 ms tolerances remain a documented,
  unreachable exception (see D2); the 0.001 ms short-circuit in
  `find_nearest_frame_aligned_tick`/`_align_to_frames` sits inside dead/inert code
  paths only.

---

Report ready. To publish the finding as a GitHub issue:

```
/audit-publish docs/audits/AUDIT_TEMPO_2026-08-21.md
```
