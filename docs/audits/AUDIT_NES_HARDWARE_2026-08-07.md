# NES Hardware Correctness Audit — 2026-08-07

Scope: the boundary where Python/asm numbers become APU register writes —
`nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py`,
`nes/audio_engine.asm`, and `exporter/exporter_ca65.py` — all ten dimensions
from `.claude/commands/audit-nes-hardware/SKILL.md`, re-derived from the
current working tree (not copied from the prior report), with focused
attention on the newly-landed `song build` / multi-song "jukebox" feature
(#30/F-13, commit `c864426`) that added `.ifdef JUKEBOX_BUILD`-gated routines
(`load_song_streams_indexed`, `audio_init_song`, `audio_advance_song`, the
`EVAL_MACRO` indirect-instrument-table path, and an end-of-stream
auto-advance hook) to `nes/audio_engine.asm`.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 1 |
| LOW      | 1 |
| **Total**| **3** |

All 3 findings are **NEW**.

**Headline: the single-song, non-jukebox register-write path remains fully
clean.** Every dimension previously tracked as fixed (NH-01..NH-11,
NH-15..NH-25, NH-HW-04) was re-verified against the current source and still
holds: the length-counter halt bit (`0x30`) on pulse/noise control bytes, the
Triangle no-volume/no-duty invariant (both `emulator_core.py`'s `default_duty
=None` routing and the exporter's fixed `0xFF`/`0x00` control derivation), the
11-bit timer clamp floored at 8 on both the pulse (`/16`) and triangle (`/32`)
tables, the `$4017=$40`/`$4015=$0F`/sweep-off (`$08`→`$4001`/`$4005`) init
sequence at all live init sites (zero-`$4011`-before-enable order confirmed),
and the bytecode engine's `last_written_hi` phase-reset guard (now also
correctly reset by the new `audio_advance_song`). This holds precisely
*because* the jukebox additions are structurally inert for single-song
builds: `nes/project_builder.py` only emits `JUKEBOX_BUILD = 1` ahead of
`.include "audio_engine.asm"` when `song_count > 1`, and a byte-for-byte diff
of the `.ifdef`/`.else` split confirms the non-jukebox branch (`audio_init`'s
`.else`, `EVAL_MACRO`'s `.else`) is untouched instruction-for-instruction by
the feature commit.

**The jukebox feature itself, however, ships with two real bugs**, both
newly introduced by this commit and both reproduced directly against a live
CC65 toolchain in this pass (not just read-through):

1. **HIGH** — `song build` on a bank containing exactly one song **fails to
   compile at all** (`ld65: Error: 8 unresolved external(s)`), because
   `CA65Exporter.export_song_bank_bytecode` always emits the multi-song
   symbol format (`song0_pulse1_sequence`, …) regardless of song count, but
   `NESProjectBuilder`'s `jukebox_mode`/`JUKEBOX_BUILD` gate requires
   `song_count > 1`, so a 1-song build assembles `audio_engine.asm`'s
   non-jukebox `.else` branches against symbols the music.asm never defines.
2. **MEDIUM** — the new end-of-stream auto-advance path in
   `nes/audio_engine.asm` can start some or all of the next song's channels
   one 60Hz NMI frame later than the others at a song transition, because
   `audio_advance_song` is invoked mid-way through the same frame's 5-channel
   loop and channels already visited this frame don't get a chance to
   re-fetch the new song's first byte until the following frame.

A third, **LOW** doc-rot regression was found in `docs/AUDIO_BYTECODE_SPEC.md`
(pre-existing, unrelated to the jukebox feature): the `$87`/`CMD_DMC_LEVEL`
table entry was accurate when written (2026-07-04, closing #83/EXP-07) but
drifted stale again when the engine's `@cmd_dmc_level` consumer was deleted
under #309 (2026-07-17) without a matching doc update.

**Also worth noting (not a new finding, no action needed):** the prior
report's `NH-HW-2026-08-06-1` (`--arranger` noise-mode-bit fix for #392
merged only on an orphan branch) and `NH-HW-2026-08-06-2` (misleading
"Length counter halt" comment on a `$4003` length-*load* write) are **both
now resolved** on this branch — `25ee053` ("`--arranger` now sets the noise
mode bit…", PR #416) and the corrected `nes/audio_engine.asm:561` comment are
both ancestors of `HEAD`. Re-verified end-to-end (gm_instruments.py's
`periodic` field → `voice_allocator._allocate_noise`'s 3-tuple → the noise
frame dict's `mode` key → `pipeline_integration.py`'s `control = mode << 6` →
exporter's `(mode << 7) | period` into `$400E`) and the comment now correctly
reads "harmless: halted via `$4000`/`#$30` control byte, not this `$4003`
length-load field".

---

## Findings

### NH-HW-2026-08-07-1: `song build` with a single-song bank fails to link — jukebox symbol format emitted below the jukebox-mode threshold
- **Severity**: HIGH
- **Dimension**: Cross-cutting (new jukebox feature vs. Dimension 1/audio engine structure) — root cause lives at the `nes/audio_engine.asm` `.ifdef JUKEBOX_BUILD` boundary this audit tracks; also relevant to the mapper/project-builder and pipeline audits (`nes/project_builder.py`, `main.py:run_song_build`).
- **Location**: `nes/project_builder.py:308` (`if song_count and song_count > 1:`) and `:336` (`jukebox_mode = bool(song_count and song_count > 1)`), vs. `exporter/exporter_ca65.py:1533-1670` (`export_song_bank_bytecode`, which never special-cases `len(songs) == 1`), vs. `main.py:927-1027` (`run_song_build`, which always calls `export_song_bank_bytecode` and always passes `song_count=len(songs)` — no separate 1-song code path)
- **Status**: NEW (`gh issue list --repo matiaszanolli/midi2nes --limit 200 --state all` has no issue referencing `song build`, `jukebox`, or `song bank`; feature landed today in commit `c864426`)
- **Description**: `CA65Exporter.export_song_bank_bytecode` (used exclusively by `main.py:run_song_build`, the new `song build` CLI subcommand) always serializes every song with a `song{i}_`-prefixed symbol set — `song0_pulse1_sequence`, `song0_instrument_table`, etc. — and always emits the `song_table_ptr_lo/hi/bank`, `song_count`, and `song_instrument_ptr_lo/hi` lookup tables in place of the single-song exporter's fixed `pulse1_sequence`/`instrument_table`/`channel_start_banks` labels, **regardless of how many songs are being built** (its own docstring and `.export`/`init_music: jmp audio_init_song` lines have no `len(songs) == 1` branch). `NESProjectBuilder.prepare_project`/`_generate_main_asm`, however, only defines `JUKEBOX_BUILD` and switches `nes/audio_engine.asm` onto its jukebox `.ifdef` branches when `song_count > 1` — deliberately, per `test_song_count_one_leaves_output_unchanged` ("song_count=1 is still an ordinary single-song project"), a design intent that assumes a 1-song build would go through the *other* (`export_tables_with_patterns`) exporter. But `run_song_build` never makes that distinction: for a 1-song bank it still calls `export_song_bank_bytecode` and still passes `song_count=1` into `prepare_project`, so the emitted `music.asm` is in jukebox format while `audio_engine.asm` assembles its non-jukebox `.else` branches (`audio_init`'s fixed-label block, `EVAL_MACRO`'s direct `instrument_table+inst_offset,y` read) — referencing `pulse1_sequence`, `pulse2_sequence`, `triangle_sequence`, `noise_sequence`, `dpcm_sequence`, `instrument_table`, and `channel_start_banks`, none of which the jukebox-format `music.asm` defines. `export_song_bank_bytecode`'s own `init_music: jmp audio_init_song` is a second, independent break: `audio_init_song` is only `.export`ed inside the `.ifdef JUKEBOX_BUILD` block, so with `JUKEBOX_BUILD` undefined that symbol doesn't exist either.
- **Evidence**: Reproduced end-to-end against the real CC65 toolchain (`ca65`/`ld65` present in this environment), not just read-through:
  ```
  $ python3 -c "
  from exporter.exporter_ca65 import CA65Exporter
  from nes.project_builder import NESProjectBuilder
  from mappers.factory import MapperFactory
  songs = [{'frames': {'pulse1': {'0': {'note': 60, 'volume': 15, 'control': 0x30, 'pitch': 200}},
                        'pulse2': {}, 'triangle': {}, 'noise': {}, 'dpcm': {}}}]
  exp = CA65Exporter(); exp.export_song_bank_bytecode(songs, 'music.asm')
  builder = NESProjectBuilder('proj', mapper=MapperFactory.get_mapper('mmc3'))
  builder.prepare_project('music.asm', song_count=len(songs))
  "
  $ cd proj && bash build.sh
  ...
  Unresolved external 'audio_init_song' referenced in:
    music.asm(170)
  Unresolved external 'channel_start_banks' referenced in:
    audio_engine.asm(155) audio_engine.asm(162) audio_engine.asm(169) ...
  Unresolved external 'instrument_table' referenced in: audio_engine.asm(494) ...
  Unresolved external 'pulse1_sequence' referenced in: audio_engine.asm(151) ...
  Unresolved external 'pulse2_sequence' / 'triangle_sequence' / 'noise_sequence' / 'dpcm_sequence' ...
  ld65: Error: 8 unresolved external(s) found - cannot create output file
  ```
  The identical script with two songs (`songs = [{'frames': ...}, {'frames': ...}]`, `song_count=2`) links and produces `Done!` — confirming the break is specifically the `song_count == 1` boundary, not a general jukebox-format problem.
- **Impact**: `python main.py song build <bank>.json out.nes` produces **no ROM at all** (loud CC65 link failure, correctly surfaced by `main.py`'s `if not success: sys.exit(1)` — not a silently-reported success) for any song bank containing exactly one song. This is a fully realistic, likely-common path: a user's first `song build` attempt, or a deliberately single-track "jukebox" bank meant for later expansion. The regular (non-`song build`) pipeline remains a workaround for a single song, but the shipped `song build` subcommand itself is completely non-functional for its smallest legal input.
- **Related**: New feature #30/F-13 (commit `c864426`). No existing GitHub issue.
- **Suggested Fix**: Either (a) have `run_song_build` call the existing single-song `export_tables_with_patterns` + pass `song_count=None` when `len(songs) == 1` (matching `prepare_project`'s documented single-song contract), or (b) change the `jukebox_mode`/`JUKEBOX_BUILD` threshold in `nes/project_builder.py` to `song_count and song_count >= 1` whenever the source `music.asm` came from `export_song_bank_bytecode`, so a genuine 1-song jukebox build gets `JUKEBOX_BUILD` defined and resolves against `audio_init_song`/`song0_*`/`song_table_*` correctly. Add a regression test that runs `run_song_build` with a real (unmocked) `NESProjectBuilder` + CC65 compile against a 1-song bank — the existing `test_skip_validation_skips_validate_rom` uses a 1-song bank but mocks `NESProjectBuilder` entirely, so it does not exercise this path.

### NH-HW-2026-08-07-2: Jukebox auto-advance can start some/all channels one NMI frame late at a song transition
- **Severity**: MEDIUM
- **Dimension**: 8 (60Hz frame timing & frame counter init) — cross-ref new jukebox feature
- **Location**: `nes/audio_engine.asm:733-762` (`@end_of_stream`, the `.ifdef JUKEBOX_BUILD` auto-advance block)
- **Status**: NEW
- **Hardware ref**: `docs/APU_FRAME_COUNTER_REFERENCE.md` §4 "Engine Implementation Notes" — "midi2nes relies on the PPU's NMI to drive our 60Hz Macro Engine"; `.claude/commands/_audit-common.md`'s NES Hardware Constraints — "Playback runs at 60 FPS via NMI — frame data is one entry per 1/60s tick."
- **Description**: `audio_update`'s `@channel_loop` processes channels 0..4 (pulse1, pulse2, triangle, noise, dpcm) sequentially within one NMI-driven frame. When a channel hits `@end_of_stream` this frame, the new auto-advance block sets that channel's `channel_ended` flag, then scans **all 5** `channel_ended` flags (`ldx #0` / `@jukebox_scan_ended`); if every channel has ended (possibly across different frames, since the flag is sticky and every already-ended channel harmlessly re-triggers `@end_of_stream` every subsequent frame), it calls `jsr audio_advance_song`, which reloads `stream_ptr_lo/hi/bank` and zeroes `frame_wait`/`current_note`/`channel_ended` for **all 5** channels, then returns. Execution then falls through to `pla / tax` (restoring the *triggering* channel's own index, call it `k`) and `jmp @silence` for channel `k` — it does **not** loop back to `@fetch_byte` for channel `k` (or re-visit any channel with index `< k` already processed this frame). Consequently: channels with index `> k` (not yet visited this frame by `@channel_loop`) see `frame_wait = 0` when their turn comes later in the *same* frame and correctly start fetching the new song immediately; channels with index `<= k` (including the triggering channel `k` itself) only pick up the new song's first byte on the *next* frame — one 60Hz tick (≈16.7 ms) later. Because DPCM (index 4) is excluded from jukebox songs by `main.py:_song_has_dpcm_events`'s v1 guard, its stream is always the trivial `.byte $FF` and it always finishes at/near frame 0 — so it is never the last-finishing channel, meaning `k` is always one of the four audible tonal/noise channels (0-3). In the plausible case where the longest-playing channel is the last one processed in index order that frame (e.g. Noise, index 3, ringing out a final cymbal hit), `k = 3` and **all four audible channels** restart the new song one frame late; only the (silent, unused) DPCM slot gets the immediate restart. This is a jukebox-only defect — the manual Start-button skip (`audio_advance_song` called once from `main.asm`'s NMI handler, entirely outside/after `audio_update`'s channel loop) is unaffected and restarts all channels uniformly on the following frame.
- **Evidence**:
  ```asm
  ; nes/audio_engine.asm:733-762
  @end_of_stream:
      lda #0
      sta current_note, x
  .ifdef JUKEBOX_BUILD
      lda #1
      sta channel_ended, x
      txa
      pha
      ldx #0
  @jukebox_scan_ended:
      lda channel_ended, x
      beq @jukebox_not_all_ended
      inx
      cpx #5
      bne @jukebox_scan_ended
      jsr audio_advance_song      ; clears channel_ended itself on the way out
  @jukebox_not_all_ended:
      pla
      tax                          ; X restored to k (the triggering channel)
  .endif
      jmp @silence                 ; channel k re-silenced, NOT re-fetched this frame
  ```
  `audio_advance_song` (`:310-332`) unconditionally zeroes `frame_wait,x` for all `x` in 0..4 before returning, but nothing in the block above causes channel `k` (or any channel already processed earlier this frame, index `< k`) to re-check that zeroed `frame_wait` and jump back to `@fetch_byte` within the same frame.
- **Impact**: At every natural (non-Start-button) song transition in a multi-song jukebox ROM, one or more channels — in the worst realistic case, all four audible channels — are silent for exactly one extra 60Hz frame (≈16.7 ms) before the next song's first note sounds, while any channel with a higher index than the triggering one starts on time. This is a small, likely near-inaudible timing artifact bounded strictly to song-boundary instants (it does not accumulate or drift within a song), but it is a real, reproducible violation of the "one frame entry per NMI tick, uniformly across channels" playback model this engine otherwise holds to everywhere else.
- **Related**: New feature #30/F-13 (commit `c864426`). No existing GitHub issue. Does not affect single-song (non-`JUKEBOX_BUILD`) ROMs — confirmed entirely gated behind `.ifdef JUKEBOX_BUILD`.
- **Suggested Fix**: After `jsr audio_advance_song` succeeds, don't fall through to `@silence` for the triggering channel — instead re-enter this frame's dispatch for channel `k` (e.g. `jmp @fetch_byte` with `stream_ptr`/`stream_bank` reloaded from the just-updated `stream_ptr_lo/hi,x` / `stream_bank,x`) so it starts in the same frame as the higher-indexed channels. Simpler alternative: have `audio_advance_song` reset state for all 5 channels as it does today, but have the *outer* `audio_update` restart its `@channel_loop` from `x=0` once after any advance this frame, so every channel gets a fresh pass against the new song's `frame_wait=0` before the frame ends.

### NH-HW-2026-08-07-3: `docs/AUDIO_BYTECODE_SPEC.md` `$87`/`CMD_DMC_LEVEL` entry is stale again — regression of #83/EXP-07
- **Severity**: LOW
- **Dimension**: 4 (DPCM/DMC — level handling)
- **Location**: `docs/AUDIO_BYTECODE_SPEC.md:106` (`| **$87** | CMD_DMC_LEVEL | [level] | Writes a 7-bit DMC output level (level & $7F) directly to $4011. |`) and the table's own preamble at `:95-99`, which calls `$87` a "real, working" opcode
- **Status**: Regression of #83/EXP-07 (that issue's fix, commit `b7c99c8` on 2026-07-04, made this table entry accurate at the time — the engine really did have a working `@cmd_dmc_level` consumer then)
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2-§3 (one-shot 7-bit DAC load at `$4011`, not a per-note "volume" register)
- **Description**: `nes/audio_engine.asm`'s `@cmd_dmc_level` handler (and its dispatch `beq @cmd_dmc_level`) was deliberately removed as orphan dead code in commit `f78c618` (#309, "remove orphan @cmd_dmc_level handler from the playback engine") on 2026-07-17 — the producer side had already been dead since #72/D-09, and #309 correctly noted the consumer was equally unreachable and deleted it. `docs/AUDIO_BYTECODE_SPEC.md` was never updated to match: it still lists `$87`/`CMD_DMC_LEVEL` as a supported engine command in its opcode table, and its own preamble text (added under #83/EXP-07 specifically to stop the doc from claiming *unimplemented* commands) now makes the opposite mistake — claiming an opcode is "real, working" that the current `nes/audio_engine.asm` (confirmed via `grep -in dmc_level nes/audio_engine.asm`, zero hits) cannot decode at all. A `$87` byte reaching the live sequencer today falls through to `@unknown_command`, which `jmp`s to `@end_of_stream` and silently terminates that channel's stream — a materially different (and worse) outcome than what the spec describes.
- **Evidence**:
  ```
  $ grep -in dmc_level nes/audio_engine.asm exporter/exporter_ca65.py
  (no matches in either file)
  $ git log --oneline --all -S "cmd_dmc_level" -- nes/audio_engine.asm
  f78c618 fix: remove orphan @cmd_dmc_level handler from the playback engine (#309)
  a6a64c2 feat: implement DPCM playback command and DMC level adjustment in audio engine
  $ grep -n '87' docs/AUDIO_BYTECODE_SPEC.md
  106:| **$87** | `CMD_DMC_LEVEL` | `[level]` | Writes a 7-bit DMC output level (`level & $7F`) directly to `$4011`. |
  ```
- **Impact**: Documentation-only; no live producer ever emits `$87` (confirmed by `tests/test_ca65_export.py::test_dmc_level_command_path_removed`, still passing), so no ROM's actual playback is affected. Risk is purely to a future contributor who reads the spec, assumes `$87` is live, and either relies on it or re-wires a producer expecting the now-deleted consumer to still exist.
- **Related**: #83/EXP-07 (original doc-rot fix, now regressed), #309 (the engine-side removal that caused the regression), #72/D-09 (original producer removal).
- **Suggested Fix**: Delete the `$87`/`CMD_DMC_LEVEL` row from the opcode table (or mark it explicitly "removed, #309 — no longer decoded") and drop the "$87 ... real, working" claim from the preamble.

---

## Notes on scope boundaries

- `nes/song_bank.py`'s class docstring ("There is currently no song-bank ->
  ROM route... Multi-song ROM builds are tracked as a planned feature") and
  the equivalent line in `CLAUDE.md` are now stale doc-rot given `song build`
  exists as of this commit — flagged here for visibility but left to
  `/audit-tech-debt` or `/audit-pipeline` to file formally, since it isn't a
  hardware-register claim.
- Findings NH-HW-2026-08-07-1 and -2 sit partly outside this audit's usual
  register-level territory (symbol/link resolution and multi-frame
  scheduling, respectively, rather than a wrong byte written to `$40xx`) —
  included here because their root cause and all reproduction lives inside
  `nes/audio_engine.asm`, the file this audit is chartered to cover, and the
  task explicitly asked for scrutiny of the new jukebox-gated code. Consider
  cross-filing #1 under the mapper/pipeline audit labels as well.
- The mapper/DPCM-per-song v1 scope cut (`song build` rejects any song with
  real DPCM events) was verified working as documented and is not a defect.

## Suggested next step

```
/audit-publish docs/audits/AUDIT_NES_HARDWARE_2026-08-07.md
```
