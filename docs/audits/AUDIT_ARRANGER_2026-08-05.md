# Arranger Audit — 2026-08-05

Audit of the `--arranger` front-end (`arranger/`): role analysis, GM mapping, priority-based
voice allocation, and arpeggiation. Entry path traced: `main.py` `run_full_pipeline` →
`arrange_for_nes(events, arp_speed=3, verbose=args.verbose)` →
`analyze_midi_events` → `allocate_with_arpeggiation` → `VoiceAllocator` /
`FrameByFrameAllocator`.

This is a re-verification pass on top of `docs/audits/AUDIT_ARRANGER_2026-07-19.md`. Only one
commit has touched `arranger/` since that report: `bc5467a` ("fix: give arranger percussion a
strike decay; drop dead analyze_midi_events params (#359, #360)"), applied the same day as that
audit. Every other file in `arranger/` (`role_analyzer.py`, `gm_instruments.py`) is byte-for-byte
unchanged, so this pass re-verifies those findings against current line numbers and focuses new
scrutiny on the `bc5467a` diff itself — which turned up one new HIGH finding.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total (new)** | **1** |

- **NEW**: 1 (HIGH)
- **EXISTING** (still-open issues re-confirmed, not re-filed): 4 (#329, #330, #331, #340)
- **Re-verified fixed** (skill's prior-findings note was stale on two of these — see below):
  #84, #85/#86, #87, #88, #89/#90, #91, #92, #205–#207, #230–#232, #251–#253, #268, #359, #360.

### Contract-parity verdict: **PASS**

`arrange_for_nes`'s five-channel `output` dict (`arranger/pipeline_integration.py:246-301`) was
re-diffed key-by-key against what `exporter/exporter_ca65.py` actually reads and against the
legacy `NESEmulatorCore.process_all_tracks` contract. No drift since the 2026-07-19 verification:
`note`/`pitch`/`volume`/`control` on pulse/triangle, `note`(period)/`control`(mode bit)/`volume`
on noise, `note`(sample+1, ≤255)/`volume`(15) on DPCM. The `bc5467a` commit only changed *how*
noise-channel `volume` values are computed pre-export (the new strike-decay pass) — it did not
touch the key shape, so the contract itself still holds.

### Highest-leverage finding

**ARR-2026-08-05-1** (new, HIGH): the `#359` noise strike-decay fix — while a correct and
necessary improvement over the flat-volume behavior it replaced — reshapes noise frames by
scanning for contiguous-frame-and-same-period runs *after* per-frame allocation has already
flattened discrete note events together. Because `_apply_sustain` (default on, 200ms gap) and
plain back-to-back drum hits routinely produce zero-gap, same-period frame runs, two or more
*separate* physical strikes of the same drum (e.g. a 16th-note hi-hat pattern) collapse into a
single decaying strike: the second/third hit's real (often louder) volume is discarded in favor
of continuing the first hit's decay curve, and any hit beyond `NOISE_DECAY_FRAMES` (6 frames)
into the run is dropped outright with no re-attack. This is a regression relative to the legacy
`NESEmulatorCore` noise path, which this fix was explicitly modeled on and which does not have
this bug (it re-triggers per discrete MIDI note event, not per contiguous frame run).

### Verify-the-fix results

- **#84 (ARR-01)** frames contract — noise/DPCM emit canonical `note` keys
  (`pipeline_integration.py:282-299`). **Holds.**
- **#85/#86 (ARR-02/03)** channel-9 drum detection + GM `program` hint via
  `Counter.most_common` (`pipeline_integration.py:120-139`). **Holds.**
- **#87 (ARR-04)** drum routing via `GM_DRUM_MAP` in `_allocate_noise`/`_allocate_dpcm`
  (`voice_allocator.py:314-370`). **Holds.**
- **#88 (ARR-05)** `get_role_priority` — confirmed **removed**; `gm_instruments.py:1303` is now
  only a tombstone comment explaining the removal, no callers remain. The audit-arranger skill's
  "STILL OPEN" note for #88 is stale (already flagged stale in the 2026-07-19 report too — it has
  not been updated since). **Fixed, and re-confirmed fixed.**
- **#89/#90 (ARR-06/07)** pitch via `nes/pitch_table.py`; noise never calls
  `midi_note_to_nes_pitch` (`pipeline_integration.py:304-317`). **Holds.**
- **#91 (ARR-08)** `arp_speed=0` — confirmed **guarded**: `VoiceAllocator.arp_speed` is now a
  property whose setter clamps `max(1, int(value))` (`voice_allocator.py:102-109`), covering both
  `__init__` and the `allocate_with_arpeggiation` reassignment (`:533`). The skill's "STILL OPEN"
  note for #91 is also stale. **Fixed, and re-confirmed fixed.**
- **#92 (ARR-09)** `_order_arp_notes` delegates to `tracker.track_mapper.apply_arpeggio_pattern`
  (`voice_allocator.py:276-286`); `ArpStyle.value`s match the accepted pattern keys; live path
  only ever uses `UP` (`arrange_for_nes` never sets `arp_style`). **Holds.**
- **#205 (ARR-10)** second drum track no longer vanishes silently — `_assign_channels`
  (`role_analyzer.py:296-387`) only skips the drop bookkeeping when at least one of noise/DPCM
  was actually claimed. **Holds.**
- **#251/#252/#253/#268** (per-note routing, per-chord arp phase, hi-hat `noise_period=0`
  sentinel, soft-note `max(1,...)` volume floor) — all present and unchanged
  (`voice_allocator.py:254-343`, `pipeline_integration.py:275-290`). **Hold.**
- **#359/ARR-2026-07-19-1** (noise strike decay) — implemented as described
  (`voice_allocator.py:468-511`, `nes/envelope_processor.py` `NOISE_DECAY_FRAMES` +
  `noise_strike_decay_volume` shared with `nes/emulator_core.py`). **The core fix holds** — flat
  15-frame hiss bursts are gone — **but see ARR-2026-08-05-1 for an edge case the fix
  introduces.**
- **#360/ARR-2026-07-19-2** (dead `ticks_per_beat`/`tempo`/`fps` params) — confirmed removed;
  `analyze_midi_events` signature is now `(midi_events, sustain=True, sustain_gap=12)`
  (`pipeline_integration.py:84-87`), verified via `tests/test_arranger_audit_fixes.py`. **Holds.**
- GM coverage: `GM_INSTRUMENT_MAP` covers all 128 programs 0–127 (verified via direct Python
  check, no fallback gap). No TRIANGLE/NOISE/DPCM instrument mapping carries a `duty`.
  **Clean.**
- Noise-period fallback consistency (#87 follow-up): `_allocate_noise`'s fallback literal `5`
  (`voice_allocator.py:338-339`) still matches `get_drum_mapping`'s own "Unknown Drum" default.
  **Holds.**

---

## Findings

### ARR-2026-08-05-1: Noise strike-decay post-processing merges back-to-back same-pitch drum hits into one strike, dropping re-attacks and hits beyond 6 frames
- **Severity**: HIGH
- **Dimension**: 7 (NES Hardware-Limit Compliance) / 3 (Voice Allocation & Overflow)
- **Location**: `arranger/voice_allocator.py:476-511` (`FrameByFrameAllocator._apply_noise_strike_decay`), interacting with `arranger/pipeline_integration.py:16-81` (`_apply_sustain`, default `sustain=True`, `sustain_gap=12`)
- **Status**: NEW (introduced by the `#359` fix in commit `bc5467a`, dated 2026-07-19; not present in the flat-volume code that fix replaced)
- **Description**: `_apply_noise_strike_decay` groups `frames["noise"]` into "strikes" purely by
  scanning for **contiguous frame numbers with an identical `period`** (`voice_allocator.py:498-502`):
  ```python
  while (j + 1 < n and ordered[j + 1] == ordered[j] + 1
         and noise_frames[ordered[j + 1]].get("period") == period):
      j += 1
  ```
  It has no concept of a discrete note-on event, so it cannot distinguish "one long hit" from
  "two back-to-back re-triggers of the same drum with zero gap between them." The peak volume for
  the whole merged run is taken only from the **first** frame (`peak = noise_frames[start].get("volume", 1)`,
  `:497`), and the run is truncated to `NOISE_DECAY_FRAMES` (6) frames — so a second (or third)
  hit's real, independently-computed volume is silently discarded, and any hit whose frames fall
  past the 6-frame truncation point disappears from the output entirely with no re-attack.
  Zero-gap adjacency between separate drum hits is a common outcome, not a corner case: `_apply_sustain`
  (on by default, `sustain_gap=12` = 200ms) bridges the end of one note-group to the start of the
  next whenever they are ≤12 frames apart (`pipeline_integration.py:62-68`), and 16th notes at
  120 BPM are 7.5 frames apart — well inside that window. This is the difference in architecture
  from the legacy `NESEmulatorCore` noise path this fix explicitly modeled itself on
  (`nes/emulator_core.py:156-183`): the legacy path iterates **discrete MIDI note events**
  (`sorted_events`) and explicitly cuts a strike short at the *next event's* start frame
  (`next_frame = sorted_events[i + 1]['frame']`, `emulator_core.py:171-174`), so a re-trigger always
  gets a fresh peak. The arranger's post-hoc, frame-flattened approach lost that per-event
  granularity.
- **Evidence**: Reproduced directly against the shipped code:
  ```python
  from arranger.voice_allocator import FrameByFrameAllocator
  noise_frames = {}
  for f in range(0, 3): noise_frames[f] = {'period': 5, 'volume': 8}   # hit 1
  for f in range(3, 6): noise_frames[f] = {'period': 5, 'volume': 12}  # hit 2 (louder re-trigger)
  for f in range(6, 9): noise_frames[f] = {'period': 5, 'volume': 8}   # hit 3
  out = FrameByFrameAllocator._apply_noise_strike_decay(noise_frames)
  # -> {0:8, 1:7, 2:5, 3:4, 4:3, 5:1}  (frames 6,7,8 dropped entirely)
  ```
  Hit 2's volume 12 peak and all of hit 3 vanish; the output is a single monotonic decay from 8
  down to 1 that stops at frame 5, even though three real strikes were present in the input.
- **Impact**: Any `--arranger` build of a song with a fast, repeated same-pitch percussion part
  (16th-note hi-hats, snare/tom rolls, rapid claps) will hear those hits collapse into one
  decaying strike instead of a repeated pattern — audibly wrong and a regression versus both the
  legacy front-end and the pre-`bc5467a` flat-volume arranger behavior (which at least sustained
  audible volume for every active frame, even if it didn't decay). Blast radius: noise channel on
  any `--arranger` build with rhythmically active percussion, which is most usable input for this
  feature. `tests/test_arranger_audit_fixes.py::test_separate_hits_each_decay` only covers the
  *non-adjacent* (gapped) case and does not exercise this zero-gap/different-volume scenario, so
  the existing test suite does not catch it.
- **Related**: Regression introduced alongside the fix for #359/ARR-2026-07-19-1; same file/function.
- **Suggested Fix**: Detect a new strike on a **volume increase** (a re-attack rising back toward
  a local peak) in addition to a period/gap change, or — better — move the decay application
  earlier, before per-frame flattening, so it operates on the original per-note event list (mirroring
  the legacy path's `sorted_events` approach) rather than re-deriving event boundaries from an
  already-flattened frame dict.

---

## Existing Findings Re-Confirmed (not re-filed)

### #329: Multi-channel / Type-0 MIDI mis-arranged (channel-9 drums misrouted, GM hint mixed)
- **Severity**: MEDIUM
- **Dimension**: 2 (role detection) / 6 (drum routing)
- **Location**: `arranger/pipeline_integration.py:120-139`
- **Status**: Existing: #329 (OPEN)
- **Description**: Drum detection uses the **first** event carrying channel info
  (`next((e['channel'] ...), None)`), and `track_program` now uses `Counter.most_common` across
  the whole track — both still operate at track granularity, so a Type-0 track that interleaves
  channel-9 drums with pitched channels is still classified/mixed as one unit. Confirmed still
  present at current line numbers; not re-filed.
- **Impact**: Type-0 / multi-channel MIDI arranges incorrectly on `--arranger`.
- **Related**: #85/#86.
- **Suggested Fix**: Split events by MIDI channel before role/program analysis (tracked in #329).

### #330: Drum-track toms/agogos/cuicas ignore their GM_DRUM_MAP channel and always render as noise
- **Severity**: LOW
- **Dimension**: 6 (drum routing)
- **Location**: `arranger/voice_allocator.py` `_route_note` (channel dispatch for drum-track notes)
- **Status**: Existing: #330 (OPEN)
- **Description**: A drum track only ever holds NOISE+DPCM channel assignments, so every non-DPCM
  hit on that track is sent to NOISE regardless of whether `GM_DRUM_MAP` says the note belongs on
  TRIANGLE (toms 41-50) or PULSE2 (agogos/cuicas/triangle-instrument 67-81). Confirmed still
  present; not re-filed.
- **Impact**: Pitched percussion loses its intended timbre on `--arranger`.
- **Related**: ARR-2026-08-05-1 (more instruments funnel into the noise decay path above).
- **Suggested Fix**: Let a drum track also claim TRIANGLE/PULSE for GM-mapped melodic percussion
  (tracked in #330).

### #331: `enhanced_track_mapper` is an unused, re-exported public helper (dead API surface)
- **Severity**: LOW
- **Dimension**: 4 (dead code)
- **Location**: `arranger/pipeline_integration.py` (`enhanced_track_mapper`), re-exported in `arranger/__init__.py`
- **Status**: Existing: #331 (OPEN)
- **Description**: `enhanced_track_mapper` wraps `arrange_for_nes` and reshapes it back to an
  event-list format but has no call site in the pipeline (`main.py` calls `arrange_for_nes`
  directly). Still exported. Confirmed still present; not re-filed.
- **Impact**: Maintenance/confusion only.
- **Suggested Fix**: Remove or mark clearly internal (tracked in #331).

### #340: DPCM slot cross-reference — several percussion roles fall back to noise (cross-ref /audit-dpcm)
- **Severity**: LOW
- **Dimension**: 6 (drum routing, DPCM seam)
- **Location**: `arranger/voice_allocator.py:308-313` (`DPCM_SAMPLE_SLOTS`), `dpcm_index.json`
- **Status**: Existing: #340 (OPEN, filed as DP-DPCM-01 under the DPCM domain)
- **Description**: `GM_DRUM_MAP` flags only notes 35/36/38 `use_sample=True`, so
  `DPCM_SAMPLE_SLOTS` only ever emits slots 0 (kick) and 1 (snare); slot 2 (`.get(mapping.name, 2)`
  fallback) is presently unreachable dead code, confirmed unchanged. Splash/vibraslap/triangle
  roles have no DPCM sample and fall to noise — tracked as a DPCM-domain issue, cross-referenced
  here not re-filed.
- **Impact**: Percussion coverage gaps on the sampled path.
- **Related**: ARR-2026-08-05-1.
- **Suggested Fix**: See #340 / `/audit-dpcm`.

---

## Notes (observations below the reporting bar)

- The audit-arranger skill's "prior findings" note still lists #88 and #91 as "STILL OPEN" — both
  were confirmed fixed in the 2026-07-19 audit and remain fixed here. This is stale skill prose,
  not a code issue; worth a `/audit-sync` pass on `audit-arranger`'s `SKILL.md` to retire it.
- Determinism (Dimension 8) re-checked: parser dict insertion order → `analyze_midi_events`
  enumeration → stable `sort(key=priority)` → `max(role_scores, key=...)` first-by-dict-order.
  `ArpStyle.RANDOM` is note-seeded and unreachable on the live path. No wall-clock/global RNG. No
  change since 2026-07-19.
- Noise mode is still always 0 in both front-ends (parity, not a regression) — see 2026-07-19
  report for detail; unchanged.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-08-05.md
```
