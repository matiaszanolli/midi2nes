# Arranger Audit — 2026-07-19

Audit of the `--arranger` front-end (`arranger/`): role analysis, GM mapping, priority-based
voice allocation, and arpeggiation. Entry path traced: `main.py:861` →
`arrange_for_nes(events, arp_speed=3)` → `analyze_midi_events` → `allocate_with_arpeggiation`
→ `VoiceAllocator`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 2 |
| LOW      | 4 |
| **Total**| **6** |

- **NEW**: 2 (1 MEDIUM, 1 LOW)
- **EXISTING** (open issues, deduped against `/tmp/audit/issues.json`): 4 (#329, #330, #331, #340)

### Contract-parity verdict: **PASS**

`arrange_for_nes` output was diffed key-by-key against `NESEmulatorCore.process_all_tracks`
(the legacy producer the exporter expects) for all five channels:

| Channel | Arranger keys | Legacy keys | Match |
|---------|---------------|-------------|-------|
| pulse1/pulse2 | `note, pitch, volume, control` | `pitch, control, note, volume` | ✓ |
| triangle | `note, pitch, volume, control(0x81)` | `pitch, volume, note` (no control) | ✓ (extra `control` is harmless — exporter reads `control` via `.get(..., 0x80)`) |
| noise | `note(period≥1), control(mode<<6), volume` | `note, control(mode<<6), volume` | ✓ |
| dpcm | `note(sample+1, ≤255), volume(15)` | `note(dense_id+1, ≤255), volume(15)` | ✓ |

The exporter (`exporter/exporter_ca65.py`) consumes `note`/`volume`/`control` on both the
direct-frames (`:334-349`) and macro-bytecode (`:1067-1159`) paths, and honors a pre-baked
`pitch` when present (`:1140`, `:1159`) — so the arranger's pre-baked `pitch`/`control`
(Dimension 7) are live, not dead. The Step-4 pattern loop reads `note`/`volume` from every
channel; noise and DPCM now round-trip with real non-zero values (#84 fix holds).

### Verify-the-fix results (all prior findings confirmed still fixed)

- **#84 (ARR-01)** frames contract — noise/DPCM emit canonical `note` keys. **Holds.**
- **#85/#86 (ARR-02/03)** channel-9 drum detection + GM `program` hint — `parser_fast.py:152-154`
  carries `channel`+`program` per event; `analyze_midi_events:120-139` consumes them (with the
  #308 `Counter.most_common` program pick). **Holds.**
- **#87 (ARR-04)** drum routing via `GM_DRUM_MAP` in `_allocate_noise`/`_allocate_dpcm`. **Holds.**
- **#88 (ARR-05)** `get_role_priority` — **removed** (`gm_instruments.py:1303-1307` is now only a
  tombstone comment); no callers, not in `__init__.__all__`. The skill's "STILL OPEN" note is
  stale. **Fixed.**
- **#89/#90 (ARR-06/07)** pitch via `nes/pitch_table.py`; noise never calls
  `midi_note_to_nes_pitch`. **Holds.**
- **#91 (ARR-08)** `arp_speed=0` ZeroDivisionError — **now guarded** by the `arp_speed` property
  setter (`voice_allocator.py:97-108`, `max(1, int(value))`), which covers `VoiceAllocator.__init__`
  and the `allocate_with_arpeggiation` reassignment. The skill's "STILL OPEN" note is stale.
  **Fixed.**
- **#92 (ARR-09)** `_order_arp_notes` delegates to `track_mapper.apply_arpeggio_pattern`; the five
  `ArpStyle.value`s match the pattern keys; `RANDOM` is seeded from note values
  (`_deterministic_arp_order`). Live path only ever uses `UP`. **Holds.**
- **#251/#252/#253/#268** (per-note routing, per-chord arp phase, hi-hat sentinel, soft-note
  floor) — all present in `voice_allocator.py`. **Hold.**
- GM coverage: `GM_INSTRUMENT_MAP` covers all programs 0–127 (no fallback gap). No TRIANGLE/
  NOISE/DPCM instrument mapping carries a `duty`; `DUTY_75` is unused. **Clean.**

### Highest-leverage fix

ARR-2026-07-19-1 (noise percussion has no strike-decay envelope) is the only finding with an
audible effect on a common `--arranger` build; everything else is dead code / doc hygiene or
already-tracked routing gaps.

---

## Findings

### ARR-2026-07-19-1: Arranger percussion emits flat-volume noise with no strike decay; note-off-less hits sustain 15 frames
- **Severity**: MEDIUM
- **Dimension**: 7 (Hardware-limit compliance) / 6 (drum routing)
- **Location**: `arranger/voice_allocator.py:455-460` (`process_song` noise emit),
  `arranger/pipeline_integration.py:172-183` (15-frame default duration)
- **Status**: NEW
- **Description**: The legacy front-end deliberately renders each noise/percussion hit as a
  short **decaying** strike — `NESEmulatorCore` writes a per-frame volume ramp over
  `NOISE_DECAY_FRAMES = 6` (~100 ms), cutting off on re-trigger (`nes/emulator_core.py:152,
  172-178`), precisely because the engine forces constant-volume+halt (`$30` on `$400C`) and
  there is no hardware envelope to lean on (#162/NH-19). The arranger's noise path does none of
  this: `process_song` writes a single flat `volume = max(1, vel // 8)` for **every** frame the
  note is active (`voice_allocator.py:455-460`), so a percussion hit plays at constant amplitude
  for its whole duration rather than as a "tsh"/"tk" strike. This is compounded by two arranger
  behaviors: (a) a drum note that never receives a note-off is given a fixed
  `end_frame = start_frame + 15` (`pipeline_integration.py:172-178`) = 250 ms of continuous
  noise; and (b) `_apply_sustain` (default `sustain=True`, `sustain_gap=12`) extends and bridges
  drum notes across gaps, lengthening the burst further.
- **Evidence**: Legacy `nes/emulator_core.py:172-178` builds `decayed_volume = max(1,
  round(peak_volume * (span - offset) / span))` per frame; arranger `voice_allocator.py:457-460`
  emits `{"period": period, "volume": max(1, vel // 8)}` with no offset/decay term.
- **Impact**: On the `--arranger` path, drum tracks (all noise-routed percussion: hi-hats,
  snares-not-sampled, cymbals, claps, toms-misrouted-to-noise) sound like sustained hiss bursts
  instead of crisp strikes. Playable, but audibly worse than legacy mode; workaround is to use
  the default (non-arranger) front-end. Blast radius: noise channel on every polyphonic
  `--arranger` build.
- **Related**: #330 (toms→noise makes more instruments hit this path); legacy decay is #162/NH-19.
- **Suggested Fix**: Apply the same short decay ramp used by `NESEmulatorCore` when materializing
  noise frames in `process_song` (or post-process the arranger's noise dict through the shared
  decay helper), and reconsider whether `_apply_sustain` should run on drum-detected tracks.

### ARR-2026-07-19-2: `analyze_midi_events` declares three unused parameters (`ticks_per_beat`, `tempo`, `fps`)
- **Severity**: LOW
- **Dimension**: 1 (contract) / 8 (determinism, docs)
- **Location**: `arranger/pipeline_integration.py:86-99`
- **Status**: NEW
- **Description**: `analyze_midi_events(midi_events, ticks_per_beat=480, tempo=500000, fps=60,
  sustain=True, sustain_gap=12)` never references `ticks_per_beat`, `tempo`, or `fps` in its
  body (verified via AST: each appears only in the signature and docstring). Frame numbers come
  pre-computed from `parser_fast` (`event.get('frame', 0)`), and note density uses
  `VoiceRoleAnalyzer.tempo_fps` (hardcoded 60.0), not this `fps`. The parameters imply the
  arranger does tempo/tick-aware frame math here — it does not — which is misleading to a
  maintainer and invites a caller to pass a real tempo expecting it to matter.
- **Evidence**: AST scan shows `ticks_per_beat`/`tempo`/`fps` occur only on signature/docstring
  lines; no read in the function body (lines 106-200).
- **Impact**: Documentation/maintainability only; no runtime effect (`arrange_for_nes` calls it
  with all defaults).
- **Related**: —
- **Suggested Fix**: Drop the three unused parameters (and their docstring lines), or wire `fps`
  through to `VoiceRoleAnalyzer.tempo_fps` if per-song FPS is intended.

### #329: Multi-channel / Type-0 MIDI mis-arranged (channel-9 drums misrouted, GM hint mixed)
- **Severity**: MEDIUM
- **Dimension**: 2 (role detection) / 6 (drum routing)
- **Location**: `arranger/pipeline_integration.py:120-138`
- **Status**: Existing: #329
- **Description**: Drum detection uses `track_channel = next((e['channel'] ... ), None)` — the
  **first** event's channel — so a Type-0 track that interleaves channel-9 drums with pitched
  channels is classified by whichever note comes first; and `track_program` counts programs
  across all channels in the track, mixing instruments. Confirmed still present. Deduped against
  open issue #329; not re-filed.
- **Impact**: Type-0 / multi-channel MIDI arranges incorrectly on `--arranger`.
- **Related**: #85/#86.
- **Suggested Fix**: Split events by MIDI channel before role/program analysis (tracked in #329).

### #330: Drum-track toms / agogos / cuicas ignore their `GM_DRUM_MAP` channel and render as noise
- **Severity**: LOW
- **Dimension**: 6 (drum routing)
- **Location**: `arranger/voice_allocator.py:207-218` (`_route_note`)
- **Status**: Existing: #330
- **Description**: A drum track only ever holds NOISE+DPCM channel assignments, so `_route_note`
  sends every non-DPCM hit to NOISE (`:212-213`). Notes whose `GM_DRUM_MAP` channel is TRIANGLE
  (toms 41-50, whistles) or PULSE2 (agogos 67/68, cuicas 78/79, mute/open triangle 80/81) are
  never routed there — they collapse onto noise. Confirmed still present. Deduped against #330.
- **Impact**: Pitched percussion loses its intended timbre on `--arranger`.
- **Related**: ARR-2026-07-19-1 (more instruments funnel into the decay-less noise path).
- **Suggested Fix**: Let a drum track also claim TRIANGLE/PULSE for GM-mapped melodic percussion
  (tracked in #330).

### #331: `enhanced_track_mapper` is an unused, re-exported public helper (dead API surface)
- **Severity**: LOW
- **Dimension**: 4 (dead code)
- **Location**: `arranger/pipeline_integration.py:332-357`, re-exported in `arranger/__init__.py:61,95`
- **Status**: Existing: #331
- **Description**: `enhanced_track_mapper` wraps `arrange_for_nes` and reshapes it back to an
  event-list format, but has no call site in the pipeline (`main.py` calls `arrange_for_nes`
  directly). It remains exported in `__all__`. Confirmed still present. Deduped against #331.
- **Impact**: Maintenance/confusion only.
- **Related**: —
- **Suggested Fix**: Remove or mark clearly internal (tracked in #331).

### #340: DPCM slot cross-reference — several percussion roles fall back to noise (cross-ref /audit-dpcm)
- **Severity**: LOW
- **Dimension**: 6 (drum routing, DPCM seam)
- **Location**: `arranger/voice_allocator.py:307-311` (`DPCM_SAMPLE_SLOTS`), `dpcm_index.json`
- **Status**: Existing: #340
- **Description**: `GM_DRUM_MAP` flags only notes 35/36/38 `use_sample=True`, so the arranger's
  `DPCM_SAMPLE_SLOTS` only ever emits slots 0 (kick) and 1 (snare); slot 2 is presently
  unreachable dead code. Whether slots 0/1 have backing samples in `dpcm_index.json` is a DPCM
  concern already tracked in #340 (splash/vibraslap/triangle roles have no sample and fall to
  noise). Deduped — cross-referenced to `/audit-dpcm`, not re-filed.
- **Impact**: Percussion coverage gaps on the sampled path.
- **Related**: #340, ARR-2026-07-19-1.
- **Suggested Fix**: See #340 / `/audit-dpcm`.

---

## Notes (observations below the reporting bar)

- **Noise mode always 0**: `arrange_for_nes:285` reads `data.get('mode', 0)`, but `process_song`
  never writes a `mode` key on noise frames, so the arranger can only ever emit normal (long-mode)
  noise. The legacy path is equally mode-0-by-default (`emulator_core.py:160` reads
  `noise_mode` which is rarely set), so this is parity, not a regression — noted for completeness.
- **First arp note holds 4 frames vs 3**: per-chord `arp_frame` starts at 0 and steps on
  `% arp_speed == 0`, so the root spans frames 0-3 (4 frames) and subsequent notes span 3 each.
  Cosmetic, on-grid, deterministic — not a finding (the #252 intent, root-plays-on-attack, holds).
- **Determinism**: verified end-to-end — parser dict insertion order → `analyze_midi_events`
  enumeration → stable `sort(key=priority)` → `max(role_scores, key=...)` first-by-dict-order.
  `ArpStyle.RANDOM` is note-seeded and unreachable on the live path. No wall-clock/global RNG.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-07-19.md
```
