# Arranger Audit — 2026-06-29

**Scope:** The `--arranger` front-end (`arranger/` subsystem): role detection
(`role_analyzer.py`), GM-instrument mapping (`gm_instruments.py`), priority-based voice
allocation + arpeggiation (`voice_allocator.py`), and the `arrange_for_nes` integration
(`pipeline_integration.py`). All 8 dimensions of `audit-arranger/SKILL.md`.

**Entry path traced:** `main.py:425-435` (`use_arranger = args.arranger`) →
`arrange_for_nes(midi_data["events"], arp_speed=3, verbose=...)` →
`analyze_midi_events` → `allocate_with_arpeggiation` → `FrameByFrameAllocator.process_song`
→ `VoiceAllocator.allocate_frame`. Downstream: `frames` → Step-4 pattern detection loop
(`main.py:455-495`) → `CA65Exporter.export_tables_with_patterns` (`exporter/exporter_ca65.py`).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 3 |
| LOW | 4 |
| **Total** | **9** |

**Contract-parity verdict: FAIL.** `arrange_for_nes` does **not** emit the same per-frame
key schema the exporter consumes for two of five channels. The legacy/canonical contract
(`NESEmulatorCore.process_all_tracks`, hardened under #9) emits noise frames as
`{"note": period, "control": mode<<6, "volume": vol}` and DPCM frames as
`{"note": sample_id+1, "volume": 15}`. The arranger instead emits noise as
`{"period", "volume", "control"}` (no `note`) and DPCM as `{"sample"}` (no `note`, no
`volume`). The CA65 exporter reads `note` for the noise period and gates DPCM on
`volume` — so on the arranger path **all noise loses its period (reads 0) and all DPCM is
silenced**. Pulse/triangle frames *do* match. (ARR-01.)

**Highest-leverage fixes:**
1. **ARR-01 (HIGH)** — make `arrange_for_nes` emit noise/DPCM with the same `note`/`volume`
   keys the exporter and macro serializer read (the #9 contract), or the arranger can never
   produce drums even when a drum track is detected.
2. **ARR-02 (HIGH)** — drum tracks are essentially never detected, because detection keys on
   the *track name* containing `'drum'`/`'9'` but `parser_fast` names tracks `track_{i}` and
   discards MIDI channel 10. Combined with ARR-01, the noise+DPCM channels are dead on the
   live arranger path for ordinary GM MIDI.
3. **ARR-03 (MEDIUM)** — every non-drum track is analyzed with a hardcoded `program=0`
   (Acoustic Grand Piano); program-change events are never parsed or wired, so 127/128 of the
   GM table and all GM-driven role/channel/duty selection are dead. Only pitch/density/
   velocity heuristics survive.

The remaining findings are quality/dead-code/doc-rot (ARR-04…ARR-09).

## Verified non-findings (attempted and disproved)

- **GM table coverage** — `GM_INSTRUMENT_MAP` covers programs 0–127 with no gaps (verified
  programmatically). No silent fallthrough to the HARMONY/PULSE2 fallback.
- **Duty on non-pulse channels** — no `InstrumentMapping` whose channel is TRIANGLE/NOISE/DPCM
  carries a `duty` (all `duty=None`). Triangle `control = 0x81` in `arrange_for_nes` has no
  duty/volume bits; downstream triangle handling derives control from `volume` only
  (`exporter_ca65.py:160-168`). No triangle volume/duty contract violation. (PASS — cross-ref
  `docs/APU_TRIANGLE_REFERENCE.md`.)
- **Determinism** — `midi_events.items()` is parser insertion-order (stable), `track_idx` by
  enumeration, role ties resolved by `max()` over a fixed dict literal, `_assign_channels`
  sorts by `priority` with Python's stable sort, and a fresh `VoiceAllocator` is built per
  `arrange_for_nes` call (so `frame_count` does not bleed across songs). No RNG on the live
  path. (PASS — Dimension 8.)
- **Pulse `control` byte range** — `(duty<<6)|0x30|volume` with duty 0–3, volume 0–15 stays in
  0–255 and lands duty in bits 6–7 per `docs/APU_PULSE_REFERENCE.md`. (PASS — Dimension 7.)
- **Pulse/triangle pitch clamp** — `midi_note_to_nes_pitch` clamps to `0..2047` (11-bit) for
  pulse/triangle. (PASS for range; divergence-from-canonical-table risk recorded as ARR-06.)

## Findings

### ARR-01: Arranger noise/DPCM frames use keys (`period`/`sample`) the exporter never reads — silent drum loss
- **Severity**: HIGH
- **Dimension**: 1 (Downstream Contract Parity)
- **Location**: `arranger/pipeline_integration.py:241-253` (producer); `exporter/exporter_ca65.py:214-249` (direct path) and `:914-950` (macro path) (consumer); contrast `nes/emulator_core.py:88-130` (canonical contract)
- **Status**: NEW
- **Description**: The non-arranger path (`process_all_tracks`, the canonical `frames`
  contract hardened by #9) emits noise as `{"note": period, "control": mode<<6, "volume": vol}`
  and DPCM as `{"note": sample_id+1, "volume": 15}` — the period and sample id live in `note`,
  and DPCM carries a `volume`. The arranger instead emits noise as `{"period", "volume",
  "control"}` (period under `period`, **no `note`**) and DPCM as `{"sample"}` (**no `note`,
  no `volume`**). The CA65 exporter reads the noise period as `fd.get('note', 0) & 0x0F`
  (always 0 for arranger frames) and gates DPCM emission on `fd.get('volume', 0) == 0`
  (always true → every DPCM frame skipped). The macro path (`:914-950`) likewise reads
  `note`/`volume`, so arranger noise becomes all rest-sentinel (note 0) and DPCM all rests.
- **Evidence**: Arranger producer:
  ```python
  # pipeline_integration.py:242-253
  output['noise'][frame] = {'period': data['period'], 'volume': data['volume'], 'control': ...}
  output['dpcm'][frame]  = {'sample': data['sample']}
  ```
  Exporter consumer (direct path):
  ```python
  # exporter_ca65.py:220-223
  if not fd or fd.get('volume', 0) == 0: ... continue
  period = fd.get('note', 0) & 0x0F          # arranger has no 'note' → 0
  # :243  DPCM
  if not fd or fd.get('volume', 0) == 0: ... continue   # arranger has no 'volume' → skipped
  ```
  Canonical contract (`emulator_core.py:106-110, 123-126`): noise `{"note": period, ...}`,
  DPCM `{"note": sample_id+1, "volume": 15}`.
- **Impact**: On any `--arranger` run where a drum track *is* detected, every noise hit plays
  with period 0 (wrong pitch / lowest-period white noise) and every DPCM sample is silently
  dropped. Inter-stage key drift that yields wrong/empty output for valid input — HIGH per
  `_audit-severity.md` ("Inter-stage JSON key mismatch that … silently yields empty output").
  Currently masked by ARR-02 (drums rarely detected) but is a latent contract break on both
  export paths.
- **Related**: ARR-02 (drum detection), #9 (the contract this diverges from), pipeline audit
  F-series (contract analysis did not cover the arranger noise/DPCM schema).
- **Suggested Fix**: In `arrange_for_nes`, emit noise as `{"note": period, "control": mode<<6,
  "volume": volume}` and DPCM as `{"note": sample_id+1, "volume": 15}` to match
  `process_all_tracks`. Add a contract test asserting arranger and legacy frames share the
  same per-channel key set (ties into REG-04/#44).

### ARR-02: Drum tracks are never detected on the live path — noise/DPCM channels stay empty for ordinary GM MIDI
- **Severity**: HIGH
- **Dimension**: 2 (Role Detection) / 6 (GM Drum Routing)
- **Location**: `arranger/pipeline_integration.py:107-108`; `tracker/parser_fast.py:51-76`
- **Status**: NEW
- **Description**: `analyze_midi_events` flags a drum track only when the track *name*
  contains `'drum'` or equals `'9'`/`9`. But `parser_fast.parse_midi_to_frames` names tracks
  `track_{i}` (or the literal `track_name` meta) and **discards the MIDI channel** (`msg.channel`
  is never read). GM percussion lives on MIDI channel 10 (index 9), which the arranger's drum
  test was clearly meant to catch (`track_name == '9'`), but no track is ever keyed by channel
  number. So unless a MIDI happens to name a track with the substring "drum", drums are scored
  as ordinary pitched voices and routed to pulse/triangle; `plan.noise_tracks` /
  `plan.dpcm_tracks` stay empty.
- **Evidence**:
  ```python
  # pipeline_integration.py:108
  if 'drum' in str(track_name).lower() or track_name == '9' or track_name == 9:
      analyzer.mark_drum_track(track_idx)
  # parser_fast.py:53  track_name = f"track_{i}"   (msg.channel never inspected)
  ```
- **Impact**: For typical GM MIDI, percussion is mis-routed onto tone channels (stealing a
  pulse/triangle from real melodic/bass content) and the noise+DPCM channels produce nothing.
  Musically wrong arrangement on every drummed song; combined with ARR-01 the drum path is
  dead end-to-end. MEDIUM as "musically wrong voice dropped/mis-routed" but elevated to HIGH
  because it produces wrong output on common input (drummed GM MIDI is the norm).
- **Related**: ARR-01 (the noise/DPCM contract that would matter once detection works), #44
  (no test exercises this), `/audit-dpcm` (drum routing).
- **Suggested Fix**: Pass MIDI channel through `parser_fast` (retain `msg.channel`) and flag
  channel-9 tracks as drums in `analyze_midi_events`; keep the name heuristic as a fallback.

### ARR-03: `program` is hardcoded to 0 — the entire GM instrument table and GM-driven role/channel/duty selection are dead
- **Severity**: MEDIUM
- **Dimension**: 2 (Role Detection) / 4 (GM Mapping Coverage)
- **Location**: `arranger/pipeline_integration.py:114`, `:133`, `:146`; consumed at `arranger/role_analyzer.py:218-224`
- **Status**: NEW
- **Description**: In `analyze_midi_events`, every `NoteInfo` is built with a local
  `program = 0` that is never updated from MIDI program-change events (`parser_fast` does not
  parse them, and `VoiceRoleAnalyzer.set_track_program` is never called on the live path —
  only the unused `arranger/__init__.py` docstring shows it). `_determine_role` therefore
  always calls `get_instrument_mapping(0)` = Acoustic Grand Piano (MELODY / PULSE1 / DUTY_50 /
  priority 8) as the GM hint for every non-drum track. The `+3.0` GM-role score and the GM
  duty/channel base are identical for all tracks, so the 127 other GM entries
  (`gm_instruments.py:85-1181`) never influence a live arrangement. Effective role selection
  reduces to the pitch/density/velocity heuristics only.
- **Evidence**:
  ```python
  # pipeline_integration.py:114
  program = 0          # never reassigned anywhere in the function
  # role_analyzer.py:218
  gm_mapping = get_instrument_mapping(analysis.program)   # analysis.program is always 0
  ```
  `grep set_track_program` → only `arranger/__init__.py` docstring + definition; no live call.
- **Impact**: GM-specific timbre/role intent (e.g. bass programs 32–39 → TRIANGLE,
  pads → PULSE2, leads → DUTY) is silently ignored; arrangements are blander and
  occasionally mis-roled versus the documented design. Workaround exists (pitch heuristics
  still drive BASS→TRIANGLE etc.), so MEDIUM. All Dimension-4 GM-table findings are gated by
  this: the table is correct but unreachable.
- **Related**: ARR-02 (drum detection shares the missing-channel/program plumbing), #44.
- **Suggested Fix**: Parse `program_change` in `parser_fast` (carry per-track program) and
  call `analyzer.set_track_program(track_idx, program)` in `analyze_midi_events`.

### ARR-04: Arranger DPCM/noise routing is hardcoded and diverges from `GM_DRUM_MAP` and `dpcm_index.json`
- **Severity**: MEDIUM
- **Dimension**: 6 (GM Drum Routing)
- **Location**: `arranger/voice_allocator.py:256-280`; contrast `arranger/gm_instruments.py:1202-1268`; data `dpcm_index.json`
- **Status**: NEW
- **Description**: `VoiceAllocator._allocate_dpcm` and `_allocate_noise` re-derive drum routing
  with hardcoded note lists and magic sample indices instead of consulting `get_drum_mapping`/
  `GM_DRUM_MAP` (which are imported into `role_analyzer.py`/`pipeline_integration.py` but never
  used at allocation time). Two divergences: (a) note 40 is "Electric Snare → NOISE
  (noise_period=4)" in `GM_DRUM_MAP` but is treated as a DPCM snare in `_allocate_dpcm`
  (`note.pitch in [38, 40] → return 1`); (b) the DPCM sample indices `0` (kick), `1` (snare),
  `2` (generic) do not match `dpcm_index.json`, where `id 0 = "Hit 1"`, `id 1 = "Kick"`,
  `id 2 = "Snare"` — so the arranger's "kick" would trigger "Hit 1", its "snare" would trigger
  "Kick", and generic would trigger "Snare". `_allocate_noise` also discards the curated
  `GM_DRUM_MAP.noise_period` values, recomputing `(pitch-36)//6` clamped 0–15.
- **Evidence**:
  ```python
  # voice_allocator.py:273-280
  if note.pitch in [35, 36]: return 0   # "kick" → dpcm_index id 0 == "Hit 1"
  elif note.pitch in [38, 40]: return 1 # "snare" → id 1 == "Kick"
  return 2                              # generic → id 2 == "Snare"
  # :258  noise_period = max(0, min(15, (note.pitch - 36) // 6))  (ignores GM_DRUM_MAP)
  ```
- **Impact**: Wrong DPCM samples fire and noise periods are uncurated whenever drums reach the
  allocator — but this is currently unreachable due to ARR-01 (DPCM silenced) and ARR-02
  (drums undetected), so it is latent. MEDIUM (duplicate/divergent routing that would mis-play
  once the upstream bugs are fixed). Cross-ref `/audit-dpcm`.
- **Related**: ARR-01, ARR-02, `/audit-dpcm`.
- **Suggested Fix**: Drive `_allocate_dpcm`/`_allocate_noise` from `get_drum_mapping(pitch)`
  (use its `noise_period`, and resolve sample ids via `dpcm_index.json` by name, not literals).

### ARR-05: `get_role_priority()` is dead and inconsistent with the live drop order
- **Severity**: LOW
- **Dimension**: 4 (GM Mapping) / 3 (Allocation Priority)
- **Location**: `arranger/gm_instruments.py:1300-1309`; live order at `arranger/role_analyzer.py:299` + `:306-391`
- **Status**: NEW
- **Description**: `get_role_priority()` defines a role ordering (BASS=1 best … SFX=6) but is
  only re-exported in `arranger/__init__.py` and never called. The actual channel-drop order in
  `_assign_channels` sorts `plan.tracks` by the integer `TrackAnalysis.priority` (set in
  `_determine_role`), which is a *different* scale (higher = keep). The two are inconsistent and
  the named-role table is dead.
- **Evidence**: `grep get_role_priority` → definition + `__init__.py` export only; no allocation
  call. `role_analyzer.py:299` sorts by `t.priority` (reverse), not by role.
- **Impact**: Maintenance/readability only — a reader may assume role priority governs drops.
  No runtime effect. LOW (dead code / inconsistent helper).
- **Related**: ARR-03.
- **Suggested Fix**: Either remove `get_role_priority()` or make `_assign_channels` use it as a
  tie-break; document that `TrackAnalysis.priority` is the live drop key.

### ARR-06: Hand-rolled `midi_note_to_nes_pitch` diverges from the canonical `nes/pitch_table.py` used elsewhere
- **Severity**: LOW
- **Dimension**: 7 (Hardware-Limit Compliance)
- **Location**: `arranger/pipeline_integration.py:258-290`; canonical `nes/pitch_table.py` / `exporter` `midi_note_to_timer_value` (`exporter_ca65.py:990, 1005`)
- **Status**: NEW
- **Description**: `arrange_for_nes` pre-bakes a `pitch` per pulse/triangle frame using a
  float formula (`int(CPU_CLOCK/(16*f)-1)` for pulse, `/32` for triangle, clamped 0–2047). The
  macro export path recomputes its own `base_timer = midi_note_to_timer_value(note, channel)`
  and stores only `pitch_offset = clamp(pitch - base_timer, -128, 127)`. If the two formulas
  disagree by more than ±127 the offset saturates; for in-range notes they agree closely, so
  the pre-baked `pitch` is largely redundant on the macro path. Two pitch sources for the same
  value is a divergence risk and the clamp is correct vs `docs/APU_PITCH_TABLE_REFERENCE.md`
  (11-bit), so this is hardening, not a live wrong-pitch bug.
- **Evidence**: `pipeline_integration.py:281` `period = int(CPU_CLOCK / (16 * frequency) - 1)`
  vs `exporter_ca65.py:990` `base_timer = self.midi_note_to_timer_value(note, channel)`.
- **Impact**: Potential small pitch drift / dead pre-bake; no observed out-of-range emission.
  LOW. Cross-ref `/audit-nes-hardware`.
- **Related**: ARR-07.
- **Suggested Fix**: Have the arranger reuse `nes/pitch_table.py` (or `midi_note_to_timer_value`)
  so there is a single authoritative pitch source.

### ARR-07: Dead noise branch in `midi_note_to_nes_pitch` returns an unclamped MIDI note
- **Severity**: LOW
- **Dimension**: 7 / 5
- **Location**: `arranger/pipeline_integration.py:285-287`
- **Status**: NEW
- **Description**: The `else` branch of `midi_note_to_nes_pitch` returns `midi_note` directly
  (no clamp) for `channel='noise'`. `arrange_for_nes` never calls it with `'noise'` (noise
  period comes from `_allocate_noise`'s 0–15 clamp), so the branch is unreachable on the live
  path, but it is a latent unclamped value (0–127) if ever wired to the 4-bit noise period.
- **Evidence**: `pipeline_integration.py:285-287`; noise frames built from `data['period']`
  at `:243-246`, not this function.
- **Impact**: None today (dead). LOW — magic/dead code that contradicts the 4-bit noise range.
- **Related**: ARR-06.
- **Suggested Fix**: Remove the noise branch or clamp to 0–15; the noise period is the
  allocator's responsibility.

### ARR-08: `arp_speed` is not validated — `arp_speed=0` raises ZeroDivisionError in the allocator
- **Severity**: LOW
- **Dimension**: 5 (Arpeggiation) / 8
- **Location**: `arranger/voice_allocator.py:201`; call site `main.py:431-435` (hardcoded 3)
- **Status**: NEW
- **Description**: `_allocate_pulse` advances the arp index via `self.frame_count %
  self.arp_speed`. `arp_speed` is passed through `arrange_for_nes`/`allocate_with_arpeggiation`
  with no guard; a value of 0 raises `ZeroDivisionError` mid-arrangement. The live CLI hardcodes
  `arp_speed=3` (`main.py:433`), so this is unreachable from the CLI but exposed to any
  programmatic caller of the public `arrange_for_nes`.
- **Evidence**: `voice_allocator.py:201` `if self.frame_count % self.arp_speed == 0:` with no
  `arp_speed >= 1` validation in `__init__`, `allocate_with_arpeggiation`, or `arrange_for_nes`.
- **Impact**: Crash on a degenerate parameter from an API caller; not reachable via the CLI.
  LOW (missing input validation on a recoverable path).
- **Related**: SKILL Dimension 5 note on ZeroDivision.
- **Suggested Fix**: Clamp/validate `arp_speed = max(1, arp_speed)` at the `VoiceAllocator`
  boundary.

### ARR-09: `docs/arpeggio.md` documents `down_up` and `random` patterns that the code does not implement
- **Severity**: LOW
- **Dimension**: 5 (Arpeggiation) — doc-vs-code drift
- **Location**: `docs/arpeggio.md` (`down_up`, `random` sections); `arranger/voice_allocator.py:43-48` (`ArpStyle`) and `:213-225` (`_order_arp_notes`)
- **Status**: NEW
- **Description**: `docs/arpeggio.md` describes five patterns: `up`, `down`, `up_down`,
  `down_up`, `random`. The `ArpStyle` enum has only `UP`/`DOWN`/`UP_DOWN`/`RANDOM`, and
  `_order_arp_notes` implements only UP/DOWN/UP_DOWN — `RANDOM` has no branch (falls through the
  `else` to plain sorted order) and `down_up` has no enum member at all. Additionally,
  `arrange_for_nes` never exposes `arp_style` (default `ArpStyle.UP`), so on the live path only
  the UP pattern is reachable regardless of the doc.
- **Evidence**: `voice_allocator.py:215-225` (`else: return pitches` covers RANDOM);
  `docs/arpeggio.md` "#### \"down_up\" Pattern" / "#### \"random\" Pattern".
- **Impact**: Doc-rot; a reader expecting `random`/`down_up` gets plain UP order. No runtime
  break. LOW (`docs/*.md` contradicts code).
- **Related**: ARR-06.
- **Suggested Fix**: Either implement `down_up`/`random` (a `random` branch would need a seeded
  RNG to preserve determinism — see Dimension 8) or trim `docs/arpeggio.md` to the three
  implemented patterns and note that the live path only uses UP.

---

*Generated by `/audit-arranger`. Deduplicated against `/tmp/audit/issues.json` (22 open) and
`docs/audits/`. The only pre-existing arranger issue is REG-04 (#44, test-coverage gap) — all
findings above are NEW behavioral/contract findings not covered by it.*

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-06-29.md
```
