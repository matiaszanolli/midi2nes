# Arranger Audit — 2026-08-21

Audit of the `--arranger` front-end (`arranger/`): role analysis, GM mapping, priority-based
voice allocation, and arpeggiation. Entry path traced end-to-end:
`main.py` `run_full_pipeline` → `arrange_for_nes(events, arp_speed=3, verbose=args.verbose)`
→ `analyze_midi_events` → `allocate_with_arpeggiation` → `VoiceAllocator` /
`FrameByFrameAllocator` → the five-channel `output` dict → Step-4 pattern detection
(`frames_to_events`) → `CA65Exporter.export_tables_with_patterns` (both the macro-bytecode
and `--no-patterns` direct paths) → `pack_dpcm_into_asm`. The `song build --arranger` route
(`main.py:midi_to_frames_for_song`) reuses the same `arrange_for_nes` call.

Since the prior arranger audit (`docs/audits/AUDIT_ARRANGER_2026-08-07.md`), one commit
touched `arranger/` (`ffccf51`, 2026-08-07): the `role_scores` `defaultdict` fix for
#ARR-2026-08-07-1's KeyError. The crash is gone, but this pass **disproves the fix
rationale's stated invariant** (see ARR-2026-08-21-3). This pass also found two HIGH
defects the prior passes' contract-parity verdicts missed, both reproduced with runnable
Python against this tree (evidence inline).

Dedup performed per `_audit-common.md`: `gh issue list` (all 304 issues incl. closed,
saved to /tmp/audit scratch) + full scan of `docs/audits/`. All previously-tracked
arranger issues — #84–#92 (incl. #88 and #91, which the skill doc still listed as open),
#205–#207, #230–#232, #251–#253, #268, #296, #308, #329–#331, #340, #359, #360, #391,
#392, #408–#410 — are CLOSED on GitHub and their fixes re-verified in the current tree
(see Verify-the-Fix section).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 2 |
| MEDIUM   | 2 |
| LOW      | 1 |
| **Total (new)** | **5** |

### Contract-parity verdict: **PASS on key shape / FAIL on DPCM id semantics**

- **Key shape: PASS.** `arrange_for_nes`'s five-channel dict
  (`arranger/pipeline_integration.py:295-348`) re-diffed key-by-key against
  `NESEmulatorCore.process_all_tracks` and against every exporter read
  (`exporter/exporter_ca65.py` direct-frame path :243-336, bytecode path :1168-1289,
  `main.py` Step-4 `frames_to_events`, `--no-patterns` stub stats): `note`/`pitch`/
  `volume`/`control` on pulse+triangle, `note`(period, floored ≥1)/`control`(mode bit 6)/
  `volume`(floored ≥1) on noise, `note`(sample+1)/`volume`(15) on DPCM. Noise `mode` now
  flows end-to-end (#392 fix holding). No key drift.
- **DPCM id semantics: FAIL.** The DPCM `note` byte's *meaning* differs between the two
  front-ends: legacy emits dense ids backed by a `dpcm_sample_map` side table; the
  arranger emits abstract kit slots (0=kick, 1=snare, 2=other) and **no**
  `dpcm_sample_map`, so the pack stage's fallback resolves them as raw catalog ids —
  wrong samples on every `--arranger` ROM with drums. See **ARR-2026-08-21-1**.

### Highest-leverage fixes

1. **ARR-2026-08-21-2** — stop destroying overlapping same-pitch notes in
   `analyze_midi_events` (legato/repeated-note MIDI loses nearly all of the affected
   passage; reproduced: 2 frames survive out of ~200).
2. **ARR-2026-08-21-1** — translate `DPCM_SAMPLE_SLOTS` to real `dpcm_index.json`
   catalog ids (or emit `dpcm_sample_map`): today an arranger kick plays
   "(Konami, Contra Force) Hit 1.dmc" and a snare plays "...Kick.dmc".

### Cross-audit dedup

- The `--arranger` **sub-C1 triangle detune** (baked frame `pitch` from
  `NES_TRIANGLE_TABLE[note<24]` vs. the bytecode serializer's floor-24 base note →
  pitch-macro offset e.g. +323 at note 21, clamped to +127 by `_encode_macro_offset`)
  was **confirmed from the arranger side** and is deduped against the sibling
  nes-hardware audit's finding **NH-HW-2026-08-21** — not re-filed here. (Pulse is
  unaffected: `NES_NOTE_TABLE` saturates at 2047 for all notes ≤ 24, so the offset is 0.)

---

## Findings

### ARR-2026-08-21-1: Arranger DPCM slot ids are consumed as dpcm_index.json catalog ids — kick and snare play the wrong samples on every `--arranger` ROM
- **Severity**: HIGH
- **Dimension**: 6 (GM drum routing / DPCM seam), also 1 (contract parity)
- **Location**: `arranger/voice_allocator.py:317-321` (`DPCM_SAMPLE_SLOTS`),
  `arranger/pipeline_integration.py:339-346` (DPCM conversion — no `dpcm_sample_map`
  emitted), `dpcm_sampler/generate_dpcm_index.py:155-162`
  (`get_dpcm_sample_ids_from_frames` fallback), `main.py:126` (`pack_dpcm_into_asm`)
- **Status**: NEW
- **Description**: `_allocate_dpcm` emits abstract kit slots — 0 for kick, 1 for
  acoustic snare, 2 as fallback — and `arrange_for_nes` encodes them as
  `note = slot + 1`. The legacy front-end's DPCM `note` is a *dense id* backed by a
  `frames['dpcm_sample_map']` side table mapping dense ids to real `dpcm_index.json`
  catalog ids (#200/D-14); the arranger emits **no such table**. The shared pack stage
  (`pack_dpcm_into_asm` → `get_dpcm_sample_ids_from_frames`) therefore takes its
  documented fallback — "treat dense ids as catalog ids directly" — and loads catalog
  entries 0/1/2 from `dpcm_index.json`. In the shipped catalog those are:
  id 0 = "(Konami, Contra Force) Hit 1", id 1 = "...Kick", id 2 = "...Snare" (all three
  `.dmc` files present in `dmc/`). The arranger's slot semantics are shifted off by one
  relative to that coincidental ordering — and are not *connected* to it at all: nothing
  in the arranger ever consults `dpcm_index.json`.
- **Evidence**: Traced end-to-end and verified against the shipped index:
  - `DPCM_SAMPLE_SLOTS = {"Acoustic Bass Drum": 0, "Bass Drum 1": 0, "Acoustic Snare": 1}`,
    default 2 (`arranger/voice_allocator.py:317-321`).
  - `output['dpcm'][frame] = {'note': min(255, data['sample'] + 1), 'volume': 15}` and no
    `dpcm_sample_map` key anywhere in `arrange_for_nes`'s `output`
    (`arranger/pipeline_integration.py:295-346`).
  - `get_dpcm_sample_ids_from_frames`: `ids[dense_id] = int(sample_map.get(str(dense_id),
    dense_id))` with `sample_map = frames.get('dpcm_sample_map', {})` → `{0: 0, 1: 1}`.
  - `load_dpcm_index_into_packer` then loads catalog ids 0/1 keyed by pack ids 0/1; the
    engine plays pack id `note - 1`. Inspected `dpcm_index.json`: id 0 = "Hit 1",
    id 1 = "Kick", id 2 = "Snare"; files confirmed present under `dmc/`.
  - Net: **kick hits (GM 35/36) play "Hit 1"; snare hits (GM 38) play a kick sample.**
- **Impact**: Every `--arranger` build with a channel-9 drum track containing kick or
  snare (i.e. virtually any drum kit) ships a ROM whose sampled drums are the wrong
  samples — most audibly, every snare strike sounds as a kick. Affects both the
  patterned (bytecode) and `--no-patterns` (direct) export paths, since both call
  `pack_dpcm_into_asm` on the same frames. Silent: the pack stage reports
  "Packed 2 DPCM samples" successfully. The prior audits' contract-parity PASS verdicts
  checked key *shape* only, so this id-namespace corruption slipped through.
- **Related**: #200/D-14 (dense-remap contract this producer never adopted), #340/
  DP-DPCM-01 (sample coverage — different issue), #87/ARR-04 (slot table introduced),
  cross-ref `/audit-dpcm`.
- **Suggested Fix**: Have the arranger resolve its semantic slots against
  `dpcm_index.json` (pick real catalog ids for kick/snare by name, the way the legacy
  drum mapper does) and emit the same `dpcm_sample_map` side table the legacy front-end
  emits; alternatively make `get_dpcm_sample_ids_from_frames` refuse (warn) when frames
  carry DPCM notes but no `dpcm_sample_map` instead of silently guessing.

### ARR-2026-08-21-2: Overlapping same-pitch notes are destroyed by `active_notes` overwrite — legato/repeated-note passages lose almost all their sound
- **Severity**: HIGH
- **Dimension**: 2 (event → NoteInfo conversion; feeds every later stage), also 1
- **Location**: `arranger/pipeline_integration.py:200-216` (`analyze_midi_events`
  note-on/off pairing)
- **Status**: NEW
- **Description**: `analyze_midi_events` pairs note-ons and note-offs with a single-slot
  `active_notes[note] = (frame, vel, chan, program)` dict. A note-on for a pitch that is
  already active **overwrites** the first onset: the first note never becomes a
  `NoteInfo` at all, and the one note-off that follows closes the *second* onset at the
  first note's off-frame, truncating it to the overlap window; the second note-off finds
  nothing active and is discarded. Overlapping same-pitch notes are routine in real MIDI
  (DAW legato exports, piano pedal, doubled unison voices on one channel), and
  `tracker/parser_fast.py` faithfully delivers them in chronological order — so the
  arranger silently deletes both notes except for the few frames where they overlap.
- **Evidence**: Reproduced against this tree (`/tmp/audit/overlap_test.py`). Input:
  on(C4)@f0, on(C4)@f98, off@f100, off@f200 — two notes intended to cover frames 0–200.
  - Arranger: **one `NoteInfo(start=98, end=100)`** — 2 frames of sound out of 200.
  - Legacy `NESEmulatorCore.compile_channel_to_frames` on the same events: frames 0–99
    covered (both onsets kept; second truncated by its imperfect off-search, but no
    silent vanishing).
- **Impact**: Any `--arranger` build of MIDI with legato-overlapped repeated pitches
  loses those notes with **no warning** (the loss happens before role analysis, so it
  also skews density/polyphony statistics and thus role detection). A repeated-note
  melody line with characteristic 1–2-tick overlaps can lose every note but the last.
  This is silent data loss changing the song on realistic input — HIGH per
  `_audit-severity.md` ("wrong output under realistic input"; the legacy front-end does
  not share the defect, so the two modes diverge audibly on the same file).
- **Related**: #296/ARR-NEW-4 (a different note-merging loss in `_apply_sustain`, fixed;
  this one is upstream of sustain), #96 (legacy same-frame collapse warns — contrast:
  this path has no diagnostic).
- **Suggested Fix**: On a note-on for an already-active pitch, close the active note at
  the new onset frame (implicit note-off / re-trigger semantics) before re-arming the
  slot; optionally count and warn like the legacy `_collapse_same_frame_events` does.

### ARR-2026-08-21-3: Out-of-bucket GM roles (PERCUSSION/SFX) can win `_determine_role`'s max() on the 3.0 GM bonus alone — contradicting the #ARR-2026-08-07-1 fix's stated invariant
- **Severity**: MEDIUM
- **Dimension**: 2 (role detection), also 8 (the invariant the determinism argument
  leaned on)
- **Location**: `arranger/role_analyzer.py:215-268` (`_determine_role`)
- **Status**: NEW (behavioral gap left open by the closed #ARR-2026-08-07-1 fix,
  commit `ffccf51`)
- **Description**: The `defaultdict` fix stopped the KeyError, but its comment (and the
  prior audit's rationale) claims an out-of-bucket GM hint "contributes no bonus while
  the pitch/density/velocity signals below still pick one of the 4 real buckets" and
  that the appended key is "never enough to win against a real signal". Both claims are
  false: `role_scores[gm_mapping.role] += 3.0` gives the PERCUSSION/SFX key the full
  GM bonus, and for an unremarkable track (mid-range pitch, moderate density/velocity,
  monophonic) the four real buckets top out at 1.0–2.0 — so the out-of-bucket role wins
  `max()`. When it does, `best_role` is PERCUSSION or SFX: `channel_override` is False
  (roles "agree"), and **none of the four role-adjustment branches fire** — no priority
  floor, no `PlayStyle.ARPEGGIATE` for polyphonic harmony, and `analysis.role` carries a
  value `_assign_channels`' melodic chain has no branch for (a NOISE/DPCM-curated
  preferred channel falls through to the generic pulse fallback).
- **Evidence**: Reproduced (`/tmp/audit/arranger_role_test.py`): a monophonic mid-range
  track with program 47 (Timpani) → `role=PERCUSSION, confidence=0.60,
  preferred=TRIANGLE` (claims the triangle exclusively at priority 6); program 55
  (Orchestra Hit) → `role=SFX, preferred=DPCM` → falls through to pulse1; program 115
  (Woodblock) → `role=SFX/PERCUSSION, preferred=NOISE` → pulse1. 19/128 GM programs are
  curated with these roles (`arranger/gm_instruments.py`).
- **Impact**: Musically-questionable channel claims (a mid-range Timpani/Synth-Drum
  accompaniment can occupy the bass-reserved triangle at priority 5–6 whenever no
  priority-8 BASS track outranks it), skipped arpeggiation styling for these tracks, and
  a comment/audit-trail that documents behavior the code does not have. Determinism is
  unaffected (dict insertion order is stable; seeded buckets win ties). Contained by the
  priority sort in typical mixes, hence MEDIUM (suboptimal allocation, playable output).
- **Related**: #ARR-2026-08-07-1 (the KeyError fix this refines), #408/ARR-2026-08-06-1
  (`channel_override` semantics).
- **Suggested Fix**: Decide the intent and make code+comment agree: either credit an
  out-of-bucket GM role's bonus to its nearest real bucket (PERCUSSION→DECORATIVE or a
  drum path, SFX→DECORATIVE) so `max()` always lands in the 4 buckets as the comment
  claims, or explicitly support PERCUSSION/SFX as first-class roles in the
  role-adjustment branches and `_assign_channels`.

### ARR-2026-08-21-4: Dropped tracks are never surfaced to the user — the live verbose output omits `dropped_tracks`/`plan.notes`, and `print_analysis` is dead code
- **Severity**: MEDIUM
- **Dimension**: 3 (voice allocation & overflow)
- **Location**: `arranger/pipeline_integration.py:272-283` (`arrange_for_nes` verbose
  block), `arranger/role_analyzer.py:464-499` (`print_analysis`),
  `arranger/__init__.py:21` (docstring-only reference)
- **Status**: NEW
- **Description**: `_assign_channels` faithfully records overflow in
  `plan.dropped_tracks` and `plan.notes` (including since #205's bookkeeping fix), but
  nothing on the live path ever shows them: `arrange_for_nes`'s `verbose` block prints
  only per-track role/polyphony lines, and `print_analysis` — the one function that
  prints `DROPPED:` and the notes — has no caller anywhere in the codebase (its only
  mention is the `arranger/__init__.py` module docstring). `allocate_frame` then skips
  unassigned tracks with a bare `continue`. So with >4 pitched voices, entire musical
  parts vanish from the ROM with zero indication even under `--verbose`, while the
  legacy front-end warns unconditionally about its (far smaller) same-frame note drops.
- **Evidence**: `grep -rn print_analysis` → only the definition and the docstring.
  Simulated 4 melodic tracks: `dropped=[2, 3]`, `plan.notes` populated with
  "Dropped - no channels available" — and a full `arrange_for_nes(verbose=True)` run
  prints none of it.
- **Impact**: A musically-wrong voice drop (MEDIUM floor per `_audit-severity.md`) made
  worse by being undiscoverable: users comparing the ROM to the source MIDI have no clue
  which parts were cut or why. Blast radius: any `--arranger` run of a >4-voice MIDI
  (most piano/orchestral files).
- **Related**: #205/ARR-10 (made the bookkeeping correct; this is about surfacing it),
  #230/REG-12 (tests for the drop logic).
- **Suggested Fix**: Print `plan.notes` (or at minimum a one-line
  "N track(s) dropped: ..." summary) unconditionally from `arrange_for_nes` — mirroring
  the legacy path's warning style — and either call `print_analysis` under `verbose` or
  delete it.

### ARR-2026-08-21-5: Contract/allocator tests skip the documented floor/clamp and fallback edge cases
- **Severity**: LOW
- **Dimension**: 1 (contract parity) / 6 (drum routing)
- **Location**: `tests/test_arranger_frame_contract.py`, `tests/test_voice_allocator.py`
- **Status**: NEW
- **Description**: The suites added for #84/#87 cover the happy paths well (81/81 pass)
  but none of the edge cases the fixes exist for:
  - No test drives a **period-0** noise hit through `arrange_for_nes`'s
    `max(1, period & 0x0F)` floor via the *contract* test (only the hi-hat rendering
    test touches it indirectly), and no test hits the noise **volume floor**
    (`max(1, min(15, v))`) with volume 0, nor DPCM `note` at the exporter-relevant 95
    boundary.
  - `DPCM_SAMPLE_SLOTS`' slot-2 fallback (`.get(mapping.name, 2)`) and
    `_allocate_noise`'s no-curated-period fallback (`noise_period = 5`) are untested —
    and that `5` is a **separate literal** from `get_drum_mapping`'s own "Unknown Drum"
    default `5` (`arranger/gm_instruments.py:1322`); nothing pins the two in sync, so a
    change to either silently diverges the fallback sound.
- **Evidence**: Test inventories read in full (`grep -n "def test"` both files; contract
  file read whole). `tests/test_arranger_frame_contract.py:31-86` asserts key sets and
  two value cases only.
- **Impact**: The floors/fallbacks guarding the rest-sentinel and unknown-drum contracts
  can regress without any test failing. Working code today — LOW (missing coverage on a
  working path).
- **Related**: #253 (period-0 sentinel decision), #268/NH-30 (volume floor), skill-doc
  verify items.
- **Suggested Fix**: Add parametrized edge-case tests (period 0, volume 0, slot-2 drum
  if `GM_DRUM_MAP` ever grows a third `use_sample` entry — assertable today by
  monkeypatching a mapping — and the literal-5 fallback), and have one of them assert
  `_allocate_noise`'s fallback equals `get_drum_mapping(<unmapped>).noise_period` so the
  two literals cannot drift apart.

---

## Verify-the-Fix (closed issues re-checked against the current tree)

- **#84/ARR-01** — holding. Noise frames: `note` = period floored ≥1, `control` = mode
  bit 6, `volume` floored ≥1; DPCM: `note` = id+1 (≤255, matching legacy's ceiling —
  the skill doc's "clamped ≤95" note is stale; the 95 limit is enforced with a loud
  `ValueError` at the bytecode serializer instead, #369), `volume` = 15. Step-4
  `frames_to_events` round-trips all five channels with non-zero values; the
  `--no-patterns` stub's `sum(len(ch) for ch in frames.values())` is well-formed (five
  dict channels, no `dpcm_sample_map` in arranger output). **But** see
  ARR-2026-08-21-1: shape parity ≠ id-semantics parity on DPCM.
- **#85/#86 (drum detection, GM program)** — holding. `parser_fast` stamps `channel` and
  the channel-scoped active `program` on every note event (`tracker/parser_fast.py:
  125-155`); mid-track program changes are handled (per-channel active program at note
  time), and `analyze_midi_events` takes the most-common program per channel (#308).
  Channel-9 detection is authoritative over misleading names (#206) with tests covering
  both override directions.
- **#87/ARR-04** — holding. `_allocate_dpcm`/`_allocate_noise` consult `get_drum_mapping`;
  electric snare (40) stays on noise; curated periods used; 0–15 clamp present. Slot-2
  remains unreachable (only notes 35/36/38 are `use_sample=True`).
- **#88/ARR-05** — **fixed by removal** (GitHub CLOSED, contrary to the skill doc's
  "still open"): `get_role_priority` no longer exists; only an explanatory NOTE comment
  remains at `arranger/gm_instruments.py:1326`; `grep` finds no caller or definition.
- **#89/#90 (pitch tables)** — holding. `midi_note_to_nes_pitch` clamps 0–127 and
  delegates to `NES_NOTE_TABLE`/`NES_TRIANGLE_TABLE`; both tables verified fully
  indexable 0–127, all values 8–2047 (11-bit, floor 8). No noise branch; the noise
  conversion never calls it.
- **#91/ARR-08** — **fixed** (GitHub CLOSED, contrary to the skill doc): `arp_speed` is
  now a property clamping `max(1, int(value))` (`arranger/voice_allocator.py:98-109`),
  covering `__init__` and `allocate_with_arpeggiation`'s direct reassignment; tests
  cover 0-speed clamp and no-crash arrangement.
- **#92/ARR-09** — holding. `_order_arp_notes` delegates to
  `tracker.track_mapper.apply_arpeggio_pattern`; `ArpStyle` values (`up`/`down`/
  `up_down`/`down_up`/`random`) all match `PATTERNS` keys exactly (no silent
  fall-through); `random` is note-seeded (`_deterministic_arp_order`, seed = polynomial
  of note values, local `random.Random`) — deterministic per chord, no wall-clock/global
  RNG. Live path only ever uses `UP` (`arrange_for_nes` doesn't expose `arp_style`).
- **#205, #251, #252, #253, #268, #330** — all holding (per-track drop bookkeeping with
  `assigned` flag; per-note `_route_note` dispatch keeping NOISE+DPCM+shared-PULSE2;
  per-chord arp phase starting on the root, integer-only, on-grid at 3 frames/step;
  period-0→1 floor documented; `max(1, vel // 8)` volume floors on both pulses and
  noise, ≤15 for vel ≤127; PULSE2-mapped drums reach PULSE2 via mapped-channel check
  before the NOISE catch-all, TRIANGLE-mapped percussion still lands on NOISE with
  curated periods).
- **#296, #329, #360** — holding (sustain requires real overlap before chording;
  per-channel track splitting with drum/program isolation and `chN` suffixes only on
  real splits; `analyze_midi_events` has no tempo/tick/fps parameters and no caller
  passes them).
- **#359/#391 (noise strike decay)** — holding. `_apply_noise_strike_decay` breaks a
  strike on gap, period change, **or raw-volume change**; only `volume` is rewritten
  (entry dict copied; period/mode untouched), only downward (`noise_strike_decay_volume`
  verified monotone 15→2 over 6 frames, floor 1, span-1 safe); called from
  `process_song`, which is the live entry (`allocate_with_arpeggiation`).
- **#392** — holding: hi-hats/cowbell get `periodic=True` → mode bit set, flows to
  `control` bit 6.
- **#408/#409/#410** — holding. Curated channel survives on role agreement; the
  non-BASS triangle last-resort is gone (simulated 4-track no-BASS mix: drops in strict
  priority order, triangle stays empty, diagnostics recorded); the BASS recheck stays as
  documented defense for direct `_assign_channels` callers.
- **#ARR-2026-08-07-1** — the KeyError is fixed (no crash for the 19 PERCUSSION/SFX
  programs), but the fix's stated invariant does not hold — see ARR-2026-08-21-3.
- **GM map invariants** (Dimension 4): programmatically verified — all 128 programs
  present; no TRIANGLE/NOISE/DPCM mapping carries a `duty`; no mapping uses `DUTY_75`;
  every NOISE-routed drum has a curated `noise_period`; `GM_DRUM_MAP` spans 35–81
  (46 entries; 58/Vibraslap is absent and falls back gracefully to "Unknown Drum",
  NOISE period 5).

## Observations (below the reporting bar)

- **Exporter high-note clamp partially defeated by baked `pitch`** (cross-ref
  `/audit-exporters`, shared with the legacy front-end, not arranger-specific): for a
  tone note > 95 the serializer clamps the stream note byte to 95 but the pitch-macro
  offset is computed against the frame's baked `pitch` for the *original* note, so the
  played timer is the original note's (small negative offset, unclamped) — the #298
  "re-pitched" counter reports a clamp that mostly doesn't happen audibly. Benign-ish
  (output is *more* faithful than advertised) but inconsistent; the sub-C1 direction is
  the audible NH-HW-2026-08-21 detune.
- **Duplicate MIDI track names merge in the parser** (cross-ref `/audit-pipeline`):
  `tracker/parser_fast.py` keys `track_events` by track *name*; two tracks named
  identically (e.g. two "Piano" tracks) merge into one event list before the arranger
  sees them — same-channel merges can manufacture false polyphony that then gets
  arpeggiated. Parser-domain; not filed here.
- **First arp note holds `arp_speed`+1 frames** (4 at speed 3) vs 3 for subsequent
  notes — unchanged since the 2026-07-19 audit's note; cosmetic, on-grid, deterministic.
- **Determinism** (Dimension 8) — re-verified end-to-end: parser insertion order →
  enumerated `track_idx` → stable `sort(key=priority)` (equal priorities keep analysis
  order) → seeded-bucket-first tie-breaks in `role_scores` → integer-only frame math →
  no live-path RNG. Same MIDI ⇒ same frames.
- `arp_speed` remains hardcoded to 3 at both call sites (`main.py:898`, `:1337`); no CLI
  surface exposes it, so #91's clamp is currently defense-in-depth only.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-08-21.md
```
