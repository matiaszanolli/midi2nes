# Exporters Audit — 2026-07-18

Scope: `exporter/` output generators — the CA65 macro-bytecode path
(`export_tables_with_patterns`, the default `python main.py input.mid out.nes`
run), the direct-frame path (`export_direct_frames`, `--no-patterns`), NSF
(`exporter_nsf.py`), and FamiStudio (`exporter_famistudio.py`) — per
`.claude/commands/audit-exporters/SKILL.md`. Cross-checked against
`docs/AUDIO_BYTECODE_SPEC.md`, `docs/MACRO_USAGE_GUIDE.md`, the shipped engine
(`nes/audio_engine.asm`), the frame producers (`nes/emulator_core.py`), and the
consumer `nes/project_builder.py`. Severity floors from
`.claude/commands/_audit-severity.md`.

Dedup sources: `gh issue list --repo matiaszanolli/midi2nes --limit 200
--json number,title,state,labels` (saved to `/tmp/audit/issues.json`, 27 open
issues) and every prior report in `docs/audits/`, in particular
`docs/audits/AUDIT_EXPORTERS_2026-07-06.md` (the most recent exporters audit,
12 days prior). Per the SKILL's framing, this is a delta/re-verify pass, not a
from-scratch audit.

**Baseline re-verification.** One exporter-relevant commit landed since
2026-07-06, re-read at HEAD rather than trusting the commit message:

- `c1b52d9` (2026-07-16) "fix: report tone-channel notes clamped to NES range
  instead of silently re-pitching (#298)" — this is exactly the fix the
  2026-07-06 report's **EXP-10** finding (open, MEDIUM) asked for.
  `export_tables_with_patterns` now tracks `notes_clamped_high`/`_low`
  (`exporter_ca65.py:1048-1049`), counts each distinct clamped source note once
  (`:1094-1105`), exposes `self.notes_clamped` for callers/tests
  (`:1308`), and prints a one-line `⚠ N note(s) clamped...` summary when
  `total_clamped > 0` (`:1310-1315`). Traced the counting logic by hand against
  several clamp/no-clamp sequences (sustained runs, adjacent distinct
  out-of-range notes, dpcm exclusion) — it fires exactly once per re-pitched
  note run and never counts dpcm (whose "note" is a sample id, not a pitch).
  **EXP-10 is fixed; closed below**, matching the SKILL's Dimension 4
  pre-verification note.

Every other fix re-verified by the 2026-07-06 report still holds at HEAD:
EXP-01 (#77, `_encode_macro_offset` `:71-86`), EXP-02 (#78, `channel` passed to
`midi_note_to_timer_value` on both note-start `:1135` and continuation
`:1154`), EXP-03/D8 (#79, `main.py:1176` `choices=['ca65']`; `run_export:544`
branches only on `"ca65"`), EXP-04 (#80, `_register_instrument` `:906-924`),
EXP-05 (#81, `NSFExporter.export()`/`export_nsf()` `exporter_nsf.py:73-80`
raise `NotImplementedError`, no live caller), EXP-06 (#82, FamiStudio octave
clamp `exporter_famistudio.py:168`, dpcm sample_id fallback `:108-110`), EXP-07
(#83, spec §3 `$FE CMD_BANK_JUMP` row distinct from the in-macro loop byte),
NH-16 (#158, `midi_note_to_timer_value` clamps `[24,119]`), D-09 (#72, no
`$87`/`CMD_DMC_LEVEL` emitter), NH-21 (#163, `_compress_macro` emits only
`$FF`, no loop compression).

Two new findings surfaced this cycle by exercising code paths the prior
reports' re-verification checklist didn't cover: a **live crash in the
FamiStudio exporter** on realistic frames data (found by constructing a
`frames` dict with a populated `dpcm_sample_map` side table — the exact shape
`nes/emulator_core.py` produces for any DPCM-using song — and calling
`generate_famistudio_txt` on it directly), and **dead engine code shipped by
`nes/project_builder.py`** into every bytecode-mode `music.asm` (found while
checking Dimension 1's "confirm `audio_init`/`audio_update` exist in the
engine the builder ships" against the full appended runtime text, not just the
two imported symbols).

## Summary

### Counts by severity
- CRITICAL: 0
- HIGH: 1 (EXP-11 — NEW)
- MEDIUM: 0 (EXP-10 fixed this cycle by #298 / `c1b52d9`)
- LOW: 2 (EXP-12 — NEW; EXP-09 — re-confirmed open, unchanged)
- **Genuinely new this cycle: 2**
- Resolved since last cycle: EXP-10 (#298, `c1b52d9`)

### Counts by dimension
- D1 (CA65 well-formedness / builder compat): 1 new (EXP-12 — dead builder-side
  macro engine)
- D2 (APU register serialization): 0 new (re-verified clean)
- D3 (pattern-vs-empty paths): 0 new (`references`-unused docstring still
  accurate)
- D4 (byte-range safety): 0 new (EXP-04/#80 guard holds; all macro bytes ≤255)
- D5 (bytecode-spec conformance): 0 new (spec §3 in sync with the exporter and
  the engine)
- D6 (macro emission): 0 new (null macros seeded, Vol/Arp/Pitch/Duty order
  intact, EXP-10 clamp-reporting fix independently re-verified)
- D7 (cross-exporter consistency): 1 new (EXP-11 — FamiStudio crash),
  1 re-confirmed (EXP-09 dead code)
- D8 (format-string / CLI mismatch): 0 new (re-verified clean)

### Three highest-impact findings
1. **EXP-11 (HIGH, NEW)** — `exporter/exporter_famistudio.py`'s
   `generate_famistudio_txt` iterates every top-level key of the `frames` dict,
   including the `dpcm_sample_map` side table that `nes/emulator_core.py`
   attaches for any DPCM-using song. For a realistic song (more frames than
   distinct DPCM samples), this produces a malformed pattern key that crashes
   the write-patterns loop with `ValueError: too many values to unpack`. The
   FamiStudio exporter is completely non-functional for any DPCM-bearing song
   through its only public entry points.
2. **EXP-12 (LOW, NEW)** — `nes/project_builder.py` appends a second, entirely
   dead macro-instrument/DPCM-trigger implementation (`seq_cmd_instrument`,
   `seq_cmd_dpcm_play`, and ~85 bytes of supporting `ch_*` BSS state) into
   every bytecode-mode `music.asm`. Neither symbol is ever called by
   `nes/audio_engine.asm` or anywhere else — the shipped engine implements
   both operations inline. Wastes PRG-ROM/RAM on every MMC3 macro-bytecode
   build; no playback effect.
3. **EXP-10 (RESOLVED)** — the silent tone-channel note-clamp diagnostic gap
   flagged open in the 2026-07-03/05/06 reports is fixed by #298 (`c1b52d9`,
   2026-07-16): clamped notes are now counted and reported.

---

## Findings

### EXP-11: FamiStudio exporter crashes on any `frames` dict carrying the `dpcm_sample_map` side table
- **Severity**: HIGH
- **Dimension**: 7 (Cross-Exporter Consistency)
- **Spec ref**: consumer contract — `nes/emulator_core.py:206-242` documents
  `dpcm_sample_map` as a `dense_id -> catalog_id` side table attached to the
  `frames` dict for any song with DPCM samples (`DPCM_SAMPLE_MAP_KEY =
  'dpcm_sample_map'`), explicitly **not** a per-frame channel. Every other
  consumer of `frames` skips it: `exporter/exporter_ca65.py:104` (`if name !=
  'dpcm_sample_map' and data`) and `:252-253`
  (`if channel_name == 'dpcm_sample_map': continue`),
  `dpcm_sampler/generate_dpcm_index.py:135-146`
  (`sample_map = frames.get('dpcm_sample_map', {})`, read explicitly rather
  than iterated as a channel), and `benchmarks/performance_suite.py:220`.
- **Location**: `exporter/exporter_famistudio.py:84-123` (`generate_famistudio_txt`'s
  pattern-generation loop; root cause at `:90` — `for channel, events in
  frames_data.items():` with no skip for `dpcm_sample_map`); crash surfaces at
  `:128` (`channel, index = pattern_key.split('_')`).
- **Status**: NEW (not in `/tmp/audit/issues.json`; not raised by any prior
  `docs/audits/AUDIT_EXPORTERS_*.md` — the 2026-07-06 report's Dimension 7
  channel-set check only verified the *separate*, hardcoded five-channel
  `SEQUENCE` list at `exporter_famistudio.py:150`, which is unaffected; it did
  not exercise the raw `frames_data.items()` pattern-generation loop with a
  `dpcm_sample_map` key present).
- **Description**: Unlike the CA65 exporter (both paths) and the DPCM index
  generator, `generate_famistudio_txt` treats every top-level key of the
  `frames` dict as a playable channel, including the `dpcm_sample_map`
  bookkeeping table `nes/emulator_core.py` attaches whenever DPCM samples are
  used. For each song frame, the code checks `if str(frame) in events:` —
  `events` here is the sparse `{dense_id: catalog_id}` map, so frames that
  happen to coincide with a low dense id are silently swallowed (none of the
  `if/elif` channel-name branches match `'dpcm_sample_map'`, so nothing is
  appended), and all other frames fall through to the `else` branch and append
  the `"... .."` placeholder — exactly like a real channel would. Once
  `current_pattern` for this pseudo-channel is non-empty, it gets written into
  `patterns` under the key `f"dpcm_sample_map_{n}"`. The later write-out loop
  splits every pattern key on `'_'` expecting exactly two parts
  (`channel, index = pattern_key.split('_')`); `"dpcm_sample_map_0"` splits
  into four parts (`['dpcm', 'sample', 'map', '0']`), raising
  `ValueError: too many values to unpack (expected 2)`.
- **Evidence**:
  ```
  $ python3 -c "
  from exporter.exporter_famistudio import generate_famistudio_txt
  frames = {
      'pulse1': {'0': {'note': 60, 'volume': 15}, '200': {'note': 62, 'volume': 10}},
      'dpcm': {'0': {'note': 5, 'volume': 15}},
      'dpcm_sample_map': {'0': 1318, '1': 1620},
  }
  generate_famistudio_txt(frames)
  "
  Traceback (most recent call last):
    ...
    channel, index = pattern_key.split('_')
    ^^^^^^^^^^^^^^
  ValueError: too many values to unpack (expected 2)
  ```
  This `frames` shape (a tone channel spanning many frames, a `dpcm` channel,
  and a sparse `dpcm_sample_map`) is exactly what `nes/emulator_core.py`
  produces for any real song using DPCM drums with more than a handful of
  frames — i.e. essentially any playable song, not an edge case. A shorter
  song where `dpcm_sample_map` happens to cover every frame index densely
  (tested separately) does *not* crash, which is why this slipped past manual
  smoke-testing with tiny fixtures — but no realistic song has that shape.
  `tests/test_famistudio_export.py`'s fixtures never include
  `dpcm_sample_map`, so the existing test suite (`22 passed` for
  `test_famistudio_export.py` + `test_exporter_integration.py`) does not
  exercise this path.
- **Impact**: `FamiStudioExporter.export()` / `export_famistudio()` /
  `generate_famistudio_txt()` — the only public entry points for FamiStudio
  text export — are completely non-functional for any song that uses DPCM
  samples, which is the common case for drum-bearing NES music. `main.py`'s
  CLI does not currently expose a FamiStudio export subcommand (confirmed:
  `grep -n famistudio main.py` is empty), so no default-pipeline user hits
  this today, but the module is a documented, tested, directly-importable
  exporter (`exporter/exporter_famistudio.py` is listed in
  `.claude/commands/_audit-common.md`'s project layout as a live output
  format) and any library caller or a future CLI wiring hits this
  immediately and unconditionally.
- **Related**: distinct from EXP-06 (#82, the octave-clamp/`sample_id`-KeyError
  fix already in this same function) — that fix handles the real `dpcm`
  channel correctly; this bug is about the *other* top-level key,
  `dpcm_sample_map`, which isn't a channel at all. Same root-cause class as
  #200/D-14 (the `dpcm_sample_map` skip that `exporter_ca65.py` already
  implements at `:104`/`:252-253`) — this exporter never got the equivalent
  fix.
- **Suggested Fix**: Skip `dpcm_sample_map` at the top of the `for channel,
  events in frames_data.items():` loop (`:90`), mirroring
  `exporter_ca65.py:252-253`'s `if channel_name == 'dpcm_sample_map': continue`.
  Add a regression test with a populated `dpcm_sample_map` alongside a
  multi-hundred-frame tone channel (reproducing the shape above) to
  `tests/test_famistudio_export.py`.

### EXP-12: `nes/project_builder.py` ships a second, fully dead macro-instrument/DPCM-trigger implementation into every bytecode-mode `music.asm`
- **Severity**: LOW
- **Dimension**: 1 (CA65 Well-Formedness & Builder Compatibility) — builder-side
  dead code adjacent to the exporter's bytecode-mode contract.
- **Spec ref**: consumer — `nes/audio_engine.asm` (the shipped engine
  `exporter_ca65.py`'s non-standalone bytecode output is built to run
  against).
- **Location**: `nes/project_builder.py:136-168` (`seq_cmd_dpcm_play`,
  `.global`'d, appended whenever `is_bytecode`) and `:171-288` (BSS block
  `ch_sequence_bank`/`ch_macro_{vol,duty,arp,pitch}_{lo,hi,idx}`/
  `ch_{vol,duty}_current`/`ch_{arp,pitch}_offset`/`ch_base_note`/
  `apu_shadow_*` at `:173-202`, plus `seq_cmd_instrument` at `:244-286`).
  `fetch_sequence_byte` in the same appended block (`:209-238`) is **not**
  dead — it is `.import`ed and called by `nes/audio_engine.asm:11,198,227` and
  is the one piece of this appended text that's actually live.
- **Status**: NEW (no GitHub issue or prior audit report tracks this
  specific dead block under its own finding. A closely related but distinct
  observation exists in `docs/audits/AUDIT_NES_HARDWARE_2026-07-01.md`'s NH-21
  finding, which mentioned in passing that "the `$FE`-capable macro runtime
  exists only in the *unused* `process_channel_macros` copy
  (`nes/project_builder.py:274-330`, `.global` with zero callers)" — that was
  evidence for a since-fixed `$FE`-encoding bug (#163, closed), not a
  standalone dead-code finding, and the function has since been restructured
  (renamed/simplified to `seq_cmd_instrument`, no longer `$FE`-capable) without
  ever being removed. No subsequent report re-verified or tracked the
  dead-code fact itself.).
- **Description**: `NESProjectBuilder.prepare_project` appends a complete,
  independent macro-instrument-pointer loader (`seq_cmd_instrument`, reading
  `instrument_table` into `ch_macro_{vol,arp,pitch,duty}_{lo,hi}` and resetting
  `ch_macro_*_idx`) and DPCM sample trigger (`seq_cmd_dpcm_play`, swapping the
  MMC3 DPCM bank via `switch_dpcm_bank` and writing `$4010`-`$4013`/`$4015`)
  into every bytecode-mode `music.asm`, plus ~85 bytes of `ch_*`/`apu_shadow_*`
  BSS state to back them. Neither routine is ever invoked: `grep -rn
  "seq_cmd_instrument\|seq_cmd_dpcm_play\|ch_macro_vol_lo\|ch_sequence_bank"`
  across every `.py` and `.asm` file in the repo turns up only their own
  definitions in `project_builder.py` — no `jsr seq_cmd_instrument`, no `jsr
  seq_cmd_dpcm_play`, no reference to any `ch_*` variable, anywhere else,
  including inside the appended block itself (the only `jsr` in that whole
  text is the legitimately-used `jsr switch_dpcm_bank` inside the dead
  `seq_cmd_dpcm_play`). `nes/audio_engine.asm` implements both operations
  itself, inline, with different variable names and a different calling
  convention: `CMD_INSTRUMENT` is handled directly in `@is_command`
  (`audio_engine.asm:226-229`, `sta current_inst, x` — no call to
  `seq_cmd_instrument`), instrument-pointer lookup happens inline via the
  `EVAL_MACRO` macro at `@process_macros` (`:337-346`), and DPCM triggering
  for the bytecode path happens via `@write_dpcm` (`:513-541`, reached from
  `@process_macros` for channel index 4, not via any `$85` command byte) since
  the exporter never emits `CMD_DPCM_PLAY` ($85) — confirmed separately per
  Dimension 5/SKILL note. `switch_dpcm_bank` itself (defined by
  `mappers/mmc3.py`, exported from `main.asm`) has no other caller either, so
  it is transitively dead along with `seq_cmd_dpcm_play`.
- **Evidence**:
  ```
  $ grep -rn "seq_cmd_instrument\|seq_cmd_dpcm_play\|ch_macro_vol_lo\|ch_sequence_bank" \
      --include='*.py' --include='*.asm' .
  nes/project_builder.py:141:; seq_cmd_dpcm_play ($85)
  nes/project_builder.py:144:.global seq_cmd_dpcm_play
  nes/project_builder.py:145:seq_cmd_dpcm_play:
  nes/project_builder.py:175:ch_sequence_bank:   .res 5
  nes/project_builder.py:178:ch_macro_vol_lo:    .res 4
  nes/project_builder.py:241:; seq_cmd_instrument ($80)
  nes/project_builder.py:244:.global seq_cmd_instrument
  nes/project_builder.py:245:seq_cmd_instrument:
  nes/project_builder.py:258:    sta ch_macro_vol_lo, x
  ```
  Only definitions — zero call sites, zero references outside their own
  definitions.
- **Impact**: No functional/playback effect — `nes/audio_engine.asm` never
  calls into this code, so it cannot desync or corrupt anything at runtime.
  Purely a PRG-ROM/RAM budget cost paid on every bytecode-mode (default
  pipeline) build: roughly 90-100 bytes of `CODE` for the two dead routines
  plus 85 bytes of reserved `BSS` RAM for their supporting state, on a
  platform where both budgets are scarce. Also a maintenance hazard — a
  contributor modifying the macro/instrument or DPCM-trigger behavior could
  edit this copy (it reads as "the" instrument/DPCM logic, complete with its
  own doc comments) and observe zero effect on actual playback.
- **Related**: NH-28 (#203, OPEN, `nes/mmc3_init.asm` fully dead) is the same
  class of issue (a superseded engine-adjacent file/block never wired in)
  found by a different audit; NH-21 (#163, closed) is where this block was
  first incidentally noted, under a different (now-fixed) defect.
- **Suggested Fix**: Delete `seq_cmd_dpcm_play` (`nes/project_builder.py:136-168`)
  and `seq_cmd_instrument` plus its dedicated `ch_*` BSS block
  (`:171-202`, `:240-288`), keeping only the live `fetch_sequence_byte`
  definition and the `.import switch_dpcm_bank` line if nothing else needs it
  (or drop that too, since its sole caller is being removed). Re-run the
  `prepare`/`compile` step-by-step pipeline on a sample MIDI to confirm
  `audio_engine.asm` still assembles and links without these symbols (it
  should, since it never references them).

---

## Existing findings re-confirmed, already tracked (not re-counted as new)

- **EXP-09 (#302, OPEN)** — `exporter/compression.py`'s `CompressionEngine`
  and `BaseExporter.compress_channel_data`/`decompress_channel_data`
  (`base_exporter.py:12-46`) remain dead code: `grep -rn
  'compress_channel_data\|decompress_channel_data\|CompressionEngine'
  --include='*.py' . | grep -v test` still returns only the definitions and
  the `BaseExporter` wrappers — no exporter or `main.py` call site. Unchanged
  since 2026-07-03.
- **NH-25 (#167, OPEN)** — direct-path pulse control bytes omit the
  length-counter halt flag NH-25 tracks; the `ora #$08` before
  `$4003`/`$4007`/`$400B` (`exporter_ca65.py:625`/`:679`/`:731`) is a
  length-counter *reload* bit, a separate concern. Unchanged.
- **NH-14 (#107, OPEN)** — direct-export tone-channel `@silence` `beq`
  branches are unreachable dead code (engine-side/direct-path tech debt).
  Unchanged.
- **TD-08 (#137, OPEN)** — stale DPCM `.incbin` TODO comment at
  `exporter_ca65.py:988`; the DPCM packer does the real work elsewhere.
  Unchanged.
- **TD-11 (#136, OPEN)** — `export_direct_frames` (now ~717 lines) remains a
  monolith; tracked as tech debt, not re-counted here.

## Resolved this cycle

- **EXP-10 (was MEDIUM, open since 2026-07-03) — NOW FIXED** by `c1b52d9`
  (#298, 2026-07-16). See baseline re-verification above for the detailed
  trace of the new counting/reporting logic (`exporter_ca65.py:1048-1049`,
  `:1094-1105`, `:1306-1315`).

## Methodology notes (disproved candidates)

- **Noise-channel high clamp mislabeling (D4/D6)**: `export_tables_with_patterns`'s
  `elif note > 95: note = 95` (`:1082-1083`) applies to the `noise` channel too
  (only the *low* clamp is `channel != 'noise'`-guarded), and the adjacent
  clamp-counting logic (`:1099-1105`) would mislabel a clamped noise "note" as
  a tone-range re-pitch in the `⚠ N note(s) clamped to the NES tone range
  (24-95)` message. Traced the only producer of noise-channel `note`
  (`nes/emulator_core.py:165`, `period = max(1, self.midi_to_nes_pitch(e['note'],
  'noise'))`) through `nes/pitch_table.py:get_noise_period`, which always
  returns a 4-bit index in `0-15` — `note > 95` is unreachable for noise given
  every current producer. Not filed; would only become live if a future
  change widened the noise period encoding without updating this guard.
- **DPCM channel instrument-macro byte waste (D4/D6)**: the macro-bytecode
  path builds a full vol/arp/pitch/duty instrument tuple for DPCM events too
  and emits `CMD_INSTRUMENT` ($80) bytes for it, even though
  `nes/audio_engine.asm:332-335` (`cpx #4 / bne :+ / jmp @write_dpcm`) skips
  all macro evaluation for the DPCM channel (x=4) — so the `current_inst`
  value set by that command is read but never used. Harmless (2 wasted bytes
  per instrument change on the DPCM stream, no playback effect). Already
  identified and explicitly *not filed* by `docs/audits/AUDIT_EXPORTERS_2026-07-03.md`
  as below the LOW bar for a new finding; re-confirmed unchanged at HEAD, still
  not filed.
- **DPCM `note` byte (0-255) colliding with macro-path command-byte ranges
  (D4/D5)**: the DPCM channel's `note = sample_id + 1` byte can land anywhere
  in `$00-$FF`, but it is always emitted as the second byte of a Length
  command pair (`${length:02X}, ${note:02X}`), never as a dispatched command
  byte on its own — the engine's `@is_length`/`@read_next` loop only inspects
  the *first* byte of each pair for range dispatch. Traced several DPCM
  sample-id values (0, 94, 200, 254) through the emission and confirmed each
  is always consumed as length-command data, never misread as `$FE`/`$FF`/`$80`
  control. Disproved as a new bug (matches the 2026-07-06 report's identical
  conclusion; re-verified independently, not re-counted).

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-07-18.md
```
