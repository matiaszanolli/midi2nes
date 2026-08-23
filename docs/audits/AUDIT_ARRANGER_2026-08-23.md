# Arranger Audit — 2026-08-23

**Scope**: `--arranger` mode (`arranger/`), its contract with the legacy `frames` shape
(`nes/emulator_core.py`) and the exporter (`exporter/exporter_ca65.py`), and the GM/DPCM
seams shared with `/audit-dpcm` and `/audit-nes-hardware`. All 8 skill dimensions covered.

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 1 |

**Contract-parity verdict: PASS.** `arrange_for_nes`'s output is key-for-key identical to
`NESEmulatorCore.process_all_tracks`'s `frames` shape for all five channels (pulse1/pulse2/
triangle/noise/dpcm), including the `dpcm_sample_map` side table. The exporter genuinely
consumes the arranger's pre-baked `pitch`/`control` (not dead weight), and the previously
HIGH-severity DPCM id-semantics break (`ARR-2026-08-21-1`) is confirmed fixed and held under
direct testing against the real `dpcm_index.json`.

**Correction to this audit's own starting premise**: the skill's "only #88 and #91 remain
open" note is stale — `gh issue list` shows **all 31** arranger-labeled issues are now
CLOSED (#88/ARR-05 and #91/ARR-08 included). More importantly, the assumption that
`arranger/` "has had zero commits since the 2026-08-21 audit" was **wrong**: four commits
dated 2026-08-22 (`168d422`, `7839c4e`, `e6ab23e`, `70ae14f`) touched
`arranger/pipeline_integration.py` and `arranger/role_analyzer.py`, fixing every finding in
`AUDIT_ARRANGER_2026-08-21.md` (including its one HIGH). This audit verified against current
`HEAD` (post those commits) throughout, not the 08-21 baseline — see the doc-rot finding
below for where the skill file itself still needs updating to match.

**Highest-leverage item**: the one new finding (MEDIUM) — a GM instrument program set on one
MIDI track is invisible to a *different* track sharing the same channel, because
`tracker/parser_fast.py` scopes program tracking per-track rather than per-file. This is a
distinct root cause from the already-fixed #308 (which was about within-track event
ordering), reproduced end-to-end below.

**Verification highlights** (no finding — re-confirmed holding, not re-listed as findings
per the dedup protocol since none regressed):
- Dimension 1 (contract parity): PASS, all 5 channels, `--no-patterns` stub stats correct
  (uses `frames_to_events`, doesn't double-count `dpcm_sample_map`), `tests/test_arranger_frame_contract.py` covers the period-0/volume-0 floors.
- Dimension 3 (voice allocation/overflow): PASS — #409's BASS-only triangle fallback verified
  by direct `_assign_channels` invocation (5 non-BASS tracks, no BASS: triangle stays empty,
  drops in strict priority order); #330's PULSE2 drum-sharing and TRIANGLE-percussion exclusion
  hold; all per-frame tie-breaks traced to be set/dict-iteration-free.
- Dimension 4 (GM mapping): PASS — 128/128 programs covered, no TRIANGLE/NOISE/DPCM mapping
  carries `duty`, `get_role_priority()` (#88) isn't just uncalled, it's been **deleted
  entirely** (only a `# NOTE (#88/ARR-05)` comment remains).
- Dimension 5 (arpeggiation): PASS — `arp_speed`'s clamp (#91) is a property setter
  (`voice_allocator.py:104-115`, `max(1, int(value))`) covering every entry point including
  `allocate_with_arpeggiation`'s direct reassignment; `_order_arp_notes` delegates to
  `track_mapper.apply_arpeggio_pattern` with exact style-key parity (#92 holds).
- Dimension 6 (drum routing): PASS — real `dpcm_index.json` has `kick`/`snare`, noise-period
  fallback (`5`) is now pinned equal to `get_drum_mapping`'s own default by a dedicated test
  (closing the "two literals could drift" LOW from the prior audit).
- Dimension 7 (hardware limits): PASS — triangle emits only `note`/`pitch`/`volume` (the old
  dead `control: 0x81` key was removed by #434, one day after the 08-21 baseline — see doc-rot
  finding); pitch conversion delegates fully to `nes/pitch_table.py` with an added
  `CHANNEL_RANGES` clamp (#431); noise strike-decay's three break conditions (gap/period/
  volume-change, #391) all present; pulse control byte algebraically bounded to `[0x31, 0xFF]`.
- Dimension 8 (determinism): PASS — insertion order (parser → `track_idx` → `role_scores`
  4-key guard → stable sort → integer-only frame math) traced end-to-end with no `set`
  iteration anywhere in a tie-break path; `ArpStyle.RANDOM` unreachable from the live path and
  deterministically seeded if it were.

## Findings

### ARR-2026-08-23-1: Program change on one MIDI track is invisible to another track sharing its channel
- **Severity**: MEDIUM
- **Dimension**: 2
- **Location**: `tracker/parser_fast.py:117-125` (`channel_programs = {}` reset inside the per-track loop)
- **Status**: NEW
- **Description**: `channel_programs` (the dict tracking each MIDI channel's currently-active
  GM program, feeding the `program` key stamped onto every note event) is reset to `{}` at
  the top of `for i, track in enumerate(mid.tracks):` — i.e. it is scoped **per track**, not
  per file. A `program_change` message on one track only updates the program for note events
  in that *same* track. If a different track carries note events on the same MIDI channel
  with no local `program_change` of its own — a real GM/Type-1 convention where a dedicated
  "conductor" track issues program changes for channels whose notes live elsewhere — those
  notes silently read back `program=0` (Acoustic Grand Piano) via the `channel_programs.get(msg.channel, 0)`
  default at `:154`, instead of the real instrument set on that channel. This is a distinct
  root cause from the already-fixed #308/ARR-NEW-5, which was about *within-track* event
  ordering (first-event vs. most-common), not cross-track channel scope; `git log -p` on
  `channel_programs` shows only its original #86 introduction and no later commit addressing
  cross-track scope.
- **Evidence**: Constructed a 2-track MIDI (Track 0 "Conductor": `program_change(channel=5,
  program=40)` only, no notes; Track 1 "Violin": notes on channel 5, no local
  `program_change`) and ran it end-to-end:
  ```
  parse_midi_to_frames(...)['events']['Violin'][0]['program'] == 0   # should be 40
  analyze_midi_events(...) -> TrackAnalysis(program=0, duty=DUTY_50, style=SUSTAIN, priority=8)
  # correct GM program 40 (Violin) would give duty=DUTY_25, style=LEGATO, priority=7
  ```
  No test in `tests/test_parser_fast.py` or `tests/test_arranger*.py` builds a multi-track
  MIDI sharing a channel across tracks.
- **Impact**: Silent, no warning, no crash — playable but musically wrong. The affected
  track's GM-curated duty cycle, play style, and `_assign_channels` drop-priority (Dimension 3)
  are wrong, and `_determine_role`'s GM-hint bonus (+3.0) is credited to the wrong role bucket.
  Blast radius: MIDI files that centralize program changes on a setup/conductor track rather
  than repeating them on every track sharing a channel — a real but not universal authoring
  convention (more common in DAW/sequencer exports than hand-authored GM files).
- **Related**: Distinct from #308/ARR-NEW-5 (CLOSED — fixed the within-track first-vs-most-common
  selection; did not touch `channel_programs`'s scope).
- **Suggested Fix**: Build `channel_programs` once across the whole file, before the per-track
  note-emission pass — e.g. carry a single dict across the `for i, track in enumerate(mid.tracks)`
  loop instead of resetting it per track — so a program change on any track updates the active
  program for every subsequent note on that channel, regardless of which track issues the note.

### ARR-2026-08-23-2: audit-arranger/SKILL.md itself has drifted from the code it audits
- **Severity**: LOW
- **Dimension**: 7 (doc-rot; also touches Dimension 4/5 text)
- **Location**: `.claude/commands/audit-arranger/SKILL.md:200, 223, 298`
- **Status**: NEW
- **Description**: Three spots in the skill file this audit runs from are stale relative to
  fixes that landed on 2026-08-22 (one day before this audit, and after the 2026-08-21 audit
  this skill file's prose was last written against):
  - `:200` — `**STILL OPEN — #88 (ARR-05)**: get_role_priority() ... is re-exported via
    arranger/__init__.py but has no call site`. Current code: the function has been **deleted
    entirely** (only a `# NOTE (#88/ARR-05)` comment remains at `gm_instruments.py:1326`), and
    it is no longer re-exported (`arranger/__init__.py`'s `__all__` has no such entry). #88 is
    CLOSED on GitHub.
  - `:223` — `**STILL OPEN — #91 (ARR-08)**: arp_speed is never validated ... Nothing ...
    guards against 0`. Current code: `VoiceAllocator.arp_speed` is a property with a clamping
    setter (`voice_allocator.py:104-115`, `max(1, int(value))`) covering every entry point.
    `tests/test_voice_allocator.py::TestArpSpeedValidation` exercises `arp_speed=0`/`-5` at
    the constructor, direct reassignment, and a full `arrange_for_nes(events, arp_speed=0)`
    run with no crash. #91 is CLOSED on GitHub.
  - `:298` — `... arrange_for_nes writes triangle control = 0x81 with no duty bits`. Current
    code: commit `70ae14f` (#434, 2026-08-22) removed the triangle `control` key entirely —
    `pipeline_integration.py`'s triangle conversion now emits only `note`/`pitch`/`volume`,
    matching `nes/emulator_core.py`'s triangle contract (which never had a `control` key
    either). The `0x81` value described no longer exists anywhere in the live code.
- **Evidence**: `grep -n "STILL OPEN\|0x81" .claude/commands/audit-arranger/SKILL.md` →
  lines 200, 223, 298 above; `git show 70ae14f -- arranger/pipeline_integration.py` shows the
  `'control': 0x81,  # Triangle linear counter` line deleted.
- **Impact**: None on ROM correctness. Misleads a future auditor (human or agent) into
  re-investigating already-closed issues, or worse, "fixing" already-correct code, or
  reporting a real fix (#434's triangle-key removal) as a regression because the checklist
  still expects the old key.
- **Suggested Fix**: Run `/audit-sync --issues 88,91,434` (or hand-edit) to update Dimension
  4/5's `#88`/`#91` framing from "STILL OPEN" to fixed, and Dimension 7's triangle checklist
  item to say triangle frames carry no `control` key at all, citing #434.

---

Suggested next steps:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-08-23.md
/audit-sync --issues 88,91,434
```
