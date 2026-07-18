# Arranger Audit — 2026-07-18

Scope: the `--arranger` front-end (`arranger/` — `pipeline_integration.py`,
`voice_allocator.py`, `role_analyzer.py`, `gm_instruments.py`) plus its seams with
`tracker/parser_fast.py`, `tracker/track_mapper.py`, `nes/pitch_table.py`, and
`exporter/exporter_ca65.py`. All 8 dimensions covered.

## Summary

**Severity counts:** CRITICAL 0 · HIGH 0 · MEDIUM 1 · LOW 2 (3 findings total).

**Contract-parity verdict: PASS.** `arrange_for_nes` emits, for every channel, exactly
the keys the CA65 exporter reads: pulse/triangle carry `note`/`pitch`/`volume`/`control`
(exporter reads all four — `exporter/exporter_ca65.py:334-349`, and the bytecode path at
`:1138-1158` honors a pre-baked `pitch`); noise carries `note` (period low-nibble, floored
to 1), `control` (mode bit 6), `volume` (floored to 1) — matching `:402-407`; DPCM carries
`note = sample_id+1` and `volume=15` — matching `:417-424`. `frames_to_events`
(`nes/emulator_core.py:238-260`) reads only `note`/`volume`, which every channel provides
with real non-zero values. The five-channel dict makes `sum(len(ch) …)` (the `--no-patterns`
stub at `main.py:918`) meaningful. No key drift found.

**Verify-the-fix results (all HOLD):**
- **#84/ARR-01** (frame keys) — noise/DPCM emit canonical `note`/`control`/`volume`, no
  stray `period`/`sample`. Confirmed against exporter reads. HOLD.
- **#85/#86** (channel-9 drum detection, GM program hint) — `parser_fast.py:129-151`
  attaches `channel` and channel-scoped `program` to every note event; `analyze_midi_events`
  consumes them. HOLD, with a NEW multi-channel caveat (ARR-NEW-5 below).
- **#87/ARR-04** (drum routing via `GM_DRUM_MAP`) — `_allocate_noise`/`_allocate_dpcm`
  consult `get_drum_mapping`; noise fallback `5` matches `get_drum_mapping`'s default. HOLD.
- **#88/ARR-05** (`get_role_priority` dead) — **now CLOSED and fixed**: the function is
  removed (only an explanatory NOTE remains at `gm_instruments.py:1303-1307`); no callers,
  not re-exported. The skill text listing it "STILL OPEN" is stale. HOLD.
- **#89/#90/ARR-06/07** (pitch tables) — `midi_note_to_nes_pitch` clamps 0–127 and indexes
  `NES_TRIANGLE_TABLE`/`NES_NOTE_TABLE` (both dicts with keys 0–127, floor-8 at idx 127,
  2047 at idx 0). Noise never routes through it. HOLD.
- **#91/ARR-08** (`arp_speed=0` ZeroDivisionError) — **now CLOSED and fixed**: an `arp_speed`
  property setter (`voice_allocator.py:97-108`) clamps `max(1, int(value))`, covering both
  `VoiceAllocator.__init__` and `allocate_with_arpeggiation`'s direct reassignment. Confirmed
  no crash. The skill text listing it "STILL OPEN" is stale. HOLD.
- **#92/ARR-09** (arp patterns) — `_order_arp_notes` delegates to
  `track_mapper.apply_arpeggio_pattern`; `ArpStyle.value` strings (`up`/`down`/`up_down`/
  `down_up`/`random`) all match its `PATTERNS` keys; `RANDOM` is note-seeded/deterministic.
  Live path only ever uses `UP`. HOLD.
- **#268/NH-30** (soft-note floor) and **#319/TD-23** (linear `vel // 8` curve + noise floor)
  — verified: pulse and noise both use `max(1, vel // 8)`, triangle `15 if vel>0 else 0`,
  with the deliberate-divergence comment at `voice_allocator.py:421-427`. HOLD.

Test state: `tests/test_arranger*.py` + `tests/test_voice_allocator.py` — 50 passed.

**Highest-leverage fix:** ARR-NEW-5 — the arranger has no per-channel handling for a single
MIDI track that carries multiple channels (every Type-0 file, plus multi-channel Type-1
tracks). Drums merged into a pitched track are silently misrouted to pulse/triangle and the
GM program hint is corrupted.

---

## Findings

### ARR-NEW-5: Multi-channel / Type-0 MIDI tracks are mis-arranged — drums misrouted, GM hint corrupted
- **Severity**: MEDIUM
- **Dimension**: 2 (Role Detection) / 3 (Voice Allocation)
- **Location**: `arranger/pipeline_integration.py:120-139`; root cause `tracker/parser_fast.py:109-153`
- **Status**: NEW
- **Description**: `parser_fast` groups events by MIDI *track* only (`track_events[track_name]`),
  never by channel. A Type-0 MIDI (one track carrying all 16 channels, including channel-9
  drums) — and any multi-channel Type-1 track — therefore reaches the arranger as a single
  merged voice. `analyze_midi_events` then (a) samples the drum flag from only the *first*
  event that has a channel: `track_channel = next((e['channel'] for e in events if …), None)`,
  so unless that first event happens to be channel 9 the whole track is `is_drum_track=False`;
  and (b) derives one GM program via `Counter(programs).most_common(1)` across *all* mixed
  channels. Result: channel-9 percussion is analyzed as pitched notes and routed to
  pulse/triangle — it never reaches NOISE/DPCM — while the melodic program hint is skewed by
  the drum channel's program 0.
- **Evidence**: Empirically reproduced. A single track `{'track_0': [...]}` with melody on
  channel 0 (program 80) and kick/hat on channel 9 yields
  `role=MELODY, is_drum=False, program=0, noise_tracks=[], dpcm_tracks=[]` — all percussion
  routed to pulse1 as pitched notes.
- **Impact**: Whole-song musical corruption for a very common export class (Type-0 MIDI):
  drums lost from the percussion channels, melody timbre mis-hinted. Playable (no crash), so
  not CRITICAL, but musically wrong across the entire song — the `--arranger` path silently
  degrades. The legacy path shares the same track granularity, but the arranger's drum
  detection specifically only inspects the first channel, giving a false impression of
  channel-9 support.
- **Related**: #85/#86 (added the per-event channel/program the fix should split on); the
  name-heuristic drum fallback (`:126-127`) is also effectively unreachable via `parser_fast`
  since every real event carries a channel, so it cannot rescue this case.
- **Suggested Fix**: Split events by `(track, channel)` before role analysis (either in
  `parser_fast` or at the top of `analyze_midi_events`), so channel-9 events become their own
  drum track and each pitched channel gets its own GM program and role.

### ARR-NEW-6: Drum-track toms/agogos/cuicas ignore their GM_DRUM_MAP channel and always render as noise
- **Severity**: LOW
- **Dimension**: 3 (Voice Allocation) / 6 (GM Drum Routing)
- **Location**: `arranger/voice_allocator.py:204-218` (`_route_note`)
- **Status**: NEW
- **Description**: A drum track claims only NOISE + DPCM (`role_analyzer.py:313-321`).
  `_route_note` returns `NESChannel.NOISE` for *any* non-sample drum note as soon as NOISE is
  in the track's channels (`:212`), which fires *before* the "honor the mapped channel" branch
  at `:216`. So `GM_DRUM_MAP` notes whose curated channel is TRIANGLE (toms 41/43/45/47/48/50)
  or PULSE2 (agogos 67/68, cuicas 78/79, mute/open triangle 80/81) are funneled to noise
  instead — and since those mappings carry no `noise_period`, they fall back to the generic
  period `5`. Pitched toms lose their pitch and sound like a generic noise hit.
- **Evidence**: `_route_note`: `if NESChannel.NOISE in channels: return NESChannel.NOISE`
  precedes `if mapping.channel in channels: return mapping.channel`. Toms have
  `noise_period=None` → `_allocate_noise` fallback `5` (`:337-338`).
- **Impact**: Musical-quality degradation on drum tracks that use melodic toms or the
  agogo/cuica/triangle percussion; the intended pitched-percussion timbre is lost. No crash,
  workaround is to author those on a separate pitched track. Structurally constrained
  (triangle is reserved for bass), but the current routing ignores the mapping table it
  otherwise consults.
- **Related**: #87/ARR-04 (routing driven by `GM_DRUM_MAP`).
- **Suggested Fix**: Before defaulting to NOISE, honor `mapping.channel` when that channel is
  in the track's assignment; only fall through to NOISE when the mapped channel isn't owned.

### ARR-NEW-7: `enhanced_track_mapper` is an unused, re-exported public helper
- **Severity**: LOW
- **Dimension**: 4 (dead/misleading API surface)
- **Location**: `arranger/pipeline_integration.py:332-357`; re-exported in `arranger/__init__.py`
- **Status**: NEW
- **Description**: `enhanced_track_mapper` (converts arranger frames back to an event-list
  format) has no call site anywhere in the repo — the live pipeline uses `arrange_for_nes`
  directly (`main.py:820`). It is nonetheless in `__all__`, so a maintainer may assume it is a
  supported/used entry point.
- **Evidence**: `grep -rn enhanced_track_mapper --include=*.py` returns only the definition
  and the `__init__` re-export; no callers.
- **Impact**: Maintenance noise / misleading API. No runtime effect.
- **Related**: mirrors the #88/ARR-05 dead-code cleanup pattern.
- **Suggested Fix**: Remove it (and its `__all__`/import entries), or add a test/caller if it
  is intended as public API.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-07-18.md
```
