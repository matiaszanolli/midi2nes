# Tempo & Frame-Timing Audit — 2026-07-17

## Summary

**Invariant verdict: frame timing stays on the 60Hz grid.** Re-verified empirically
against the current tree (HEAD `d5564b8`). A 5-minute, 120 BPM song
(`ticks_per_beat=480`, 288,000 ticks) lands the final frame at exactly frame **18000** —
**0 frames** of drift. The maximum absolute error `|get_frame_for_tick − exact|` sampled
over 2,000 consecutive beats is **3.6e-12** (float noise, sub-nanoframe). Boundary checks
pass: tick 0 → frame 0 (`calculate_time_ms(0,0)` short-circuits to `0.0`,
`tracker/tempo_map.py:185-186`), and a mid-song tempo change at tick 960 leaves that tick at
1000.0 ms → frame 60 (the change applies only to the *following* segment, not the boundary
tick itself). `calculate_time_ms(0, tick)` integrates from tick 0 on every call via the
bisect index `_cumulative_ms(end) − _cumulative_ms(start)` (`tracker/tempo_map.py:158-190`)
with no accumulating running counter.

**No findings this pass — 0 NEW, 0 open.** Since the 2026-07-06 audit the four residual LOW
items have all been resolved and their issues closed:

- **#97 / TEMPO-05** (dead `optimize_tempo_changes` / `_smooth_tempo_transitions` on the
  live path + µs/quarter interpolation timing hazard) — **CLOSED**. Verified: WARNING
  docstrings are now in code (`tracker/tempo_map.py:595-609` on `_smooth_tempo_transitions`,
  `:682-693` on `optimize_tempo_changes`) documenting that the routines are off the live
  MIDI→ROM path and that SMOOTH_TRANSITIONS/FRAME_ALIGNED are timing-lossy. Grep confirms no
  caller of `optimize_tempo_changes()` outside `tracker/tempo_map.py` and its tests; the fast
  front-end builds the map with `optimization_strategy=None` (`tracker/parser_fast.py:42`).
  Code is still inert/off-live-path — documentation matches.
- **#98 / TEMPO-06** (inert full-pipeline default-PPQ-480 tempo maps) — **CLOSED**. Verified:
  both construction sites carry the analysis-only comment — `main.py:641-646`
  (`run_detect_patterns`, also `analyze_tempo=False`) and `main.py:836-844` (`run_full_pipeline`,
  `use_patterns` branch). Both still construct `EnhancedTempoMap(initial_tempo=500000)` and
  never receive an `add_tempo_change`, so `get_tempo_at_tick` returns the constant 500000 and
  the default `ticks_per_beat` is never used for timing. Still inert — documentation matches.
- **#259 / TEMPO-12** and **#260 / TEMPO-13** (analysis parser's silent tempo-drop +
  missing `ticks_per_beat`) — **CLOSED (fixed)**. Both passes now build the tempo map through
  the shared `_build_tempo_map(mid, config)` helper (`tracker/parser_fast.py:26-69`), which
  passes the real `mid.ticks_per_beat` (`:40`) and counts + warns on dropped tempo changes
  (`:62-67`). `parse_midi_to_frames_with_analysis` calls it (`:204`), so the pre-#94 silent
  `except TempoValidationError: continue` is gone and the two passes can no longer diverge.

| Severity | Count | of which NEW |
|----------|-------|--------------|
| CRITICAL | 0     | 0 |
| HIGH     | 0     | 0 |
| MEDIUM   | 0     | 0 |
| LOW      | 0     | 0 |
| **Total**| **0** | **0** |

**Highest-leverage fix:** none. The live ROM timing path is clean and every previously-open
tempo item is now closed (documented or fixed).

---

## Findings

None.

---

## Confirmed-fixed / verified-in-place (re-verified, not re-reported)

- **#97** — WARNING docstrings present (`tracker/tempo_map.py:595-609`, `:682-693`);
  `optimize_tempo_changes` still has no live caller (grep-verified); front-end uses
  `optimization_strategy=None`. Inert, documented.
- **#98** — analysis-only comments present at `main.py:641-646` and `:836-844`; both maps never
  mutated, `ticks_per_beat` never used for timing. Inert, documented.
- **#259 / #260** — unified through `_build_tempo_map` (`tracker/parser_fast.py:26-69`); passes
  real `ticks_per_beat` and count-and-warn on drop; both parse passes share it.
- **#113** — O(log T) bisect index (`_build_tempo_index`/`_cumulative_ms`, `:129-166`);
  `calculate_time_ms(0, tick)` remains an exact from-zero computation. 0-frame drift re-verified
  (final frame 18000; max abs error 3.6e-12 over 2,000 beats).
- **#93 / #95** — SMPTE/zero/negative `ticks_per_beat`: `TempoMap.__init__` raises `ValueError`
  for `ticks_per_beat is None or < 1` (`:101-107`); `parse_midi_to_frames` rejects it earlier
  (`:86-91`). Both agree on the `< 1` boundary.
- **#94** — widened 1–2000 BPM band with `max_tempo_change_ratio=float('inf')` and
  count-and-warn (`parser_fast.py:100-107`, `_build_tempo_map:62-67`). In place.
- **#96** — same-frame note collapse in `nes/emulator_core.py:16-46` (louder wins, later wins on
  tie at `:39`, warns with count). In place.
- **#99** — single `FRAME_ALIGNMENT_TOLERANCE_MS = 0.5` (`:23`) referenced by `is_frame_aligned`
  (`:259`), `_validate_frame_boundaries` (`:472`), `_check_frame_alignment` (`:863`). In place.
- **#160** — note-off pairing: `compile_channel_to_frames` derives `end_frame` from the matching
  note-off in `all_events_sorted` (captured pre-collapse), falling back to `sustain_frames` only
  when unpaired (`nes/emulator_core.py:54-93`); `range(start_frame, end_frame)` emits up to but
  not including the note-off frame. In place.
- **#208 / #209 / #210 / #211** — tick-0 tempo validation, zero/negative tempo guard,
  duplicate-tick stable tie-break, `_frame_times`/`_frame_cache` removal — all re-verified in
  place (`tempo_map.py:266-282`, `:396-399`/`:426-429`, `:125`/`:679`; 0 grep matches for the
  dead arrays).

---

## Dedup notes

- Pre-fetched `/tmp/audit/issues.json` (27 open issues): **no** open tempo/frame/PPQ issue
  remains. #97, #98, #259, #260 — the four items carried by the 2026-07-06 audit — are all
  absent from the open list (closed since that pass; corroborated by commits `7fb526c` (#98),
  `bbe8a9b` (#97), `53a8d19` (#259/#260) in the tempo-file `git log`).
- `docs/audits/AUDIT_TEMPO_2026-07-06.md` is the prior pass; its four Existing/open LOW items
  are the ones now closed. Earlier passes (`AUDIT_TEMPO_2026-07-05.md`,
  `AUDIT_TEMPO_2026-07-03.md`, `AUDIT_TEMPO_2026-06-29.md`) cover TEMPO-01…TEMPO-13.
- No other domain audit report references live tempo/frame-timing defects.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_TEMPO_2026-07-17.md
```
