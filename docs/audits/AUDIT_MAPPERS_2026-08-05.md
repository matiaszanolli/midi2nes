# Audit: Mappers / Project Builder / Compiler — 2026-08-05

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3, capacity), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, and the `main.py` `--mapper`
resolution / capacity pre-flight / `resolve_mapper` / `enforce_direct_export_dpcm_mapper`
call sites. All 10 SKILL.md dimensions covered; no `--focus` restriction.

**Method:** every claim re-verified against live code; the previous pass's 3 findings
(#361/#362/#363, all MEDIUM) were confirmed fixed by re-reading `mappers/factory.py`,
`mappers/mmc3.py:direct_export_capacity`, `main.py:resolve_mapper`, and
`nes/project_builder.py:prepare_project` (commit `36348ce`). This pass then went further
than a re-verification pass and reproduced real builds end-to-end with the live CC65
toolchain (`ca65`/`ld65` at `/usr/bin`) across NROM/MMC1/MMC3, including `--debug` builds
and deliberately boundary-sized songs, to hunt for gaps the static review alone would miss.
That reproduction found a new CRITICAL bug (MAP-2026-08-05-1) in the `--debug` + MMC1
combination that no prior audit pass had exercised.

**Dedup basis:** `/tmp/audit/issues.json` (38 open issues, `gh issue list --state` default
which is open-only) searched for `mapper`, `compile`, `auto`, `nrom`, `mmc1`, `mmc3`,
`bank`, `capacity`, `dpcm`, `direct`, `marker`, `resolve`, `debug`, `overlay`, `vector`,
`header`, `cc65`, `ld65`, `prg`, `nmi` — no hits relevant to the new findings below. All
prior `docs/audits/AUDIT_MAPPERS_*.md` (2026-06-28 … 2026-07-19) reviewed; none mention
`--debug` interacting with mapper bank-switching. `git log` confirms only 2 commits touched
this subsystem since the 2026-07-19 pass (`36348ce` fixing #361-363, and `7a2054d`, an
unrelated triangle-envelope fix), so the surface here is otherwise unchanged from last pass.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 0 |
| MEDIUM   | 2 |
| LOW      | 0 |
| **NEW this pass** | **3** |

**One-line verdict:** The **default** single-command pipeline (MMC3, patterns-on,
no `--debug`) still produces a bootable 512 KB ROM end-to-end and remains unaffected by
this pass's findings, but `--mapper mmc1 --debug` (necessarily also `--no-patterns`, MMC1's
only export mode) reproducibly crashes on the **first NMI** for any song that needs more
than MMC1's first 16 KB switchable bank — i.e. almost any song actually exercising MMC1's
reason to exist over NROM.

---

## Findings

### MAP-2026-08-05-1: `--debug` + `--mapper mmc1` links `debug_update` into a switchable bank that direct-export playback leaves un-selected, so the first NMI after boot executes raw table bytes as code
- **Severity**: CRITICAL
- **Dimension**: 5 (bank-switching correctness), cross-cutting with 2 (NMI 60Hz call) and 7 (project builder consistency)
- **Location**: `nes/project_builder.py:142-148` (debug overlay text appended to `music_content` with no leading `.segment` directive), `nes/project_builder.py:366-376` (`nmi:` calls `jsr update_music` then `jsr debug_update` with nothing in between), `mappers/mmc1.py:99,102` (`RODATA: load = PRG_BANK_00` — switchable — vs `CODE: load = PRGFIXED` — always-mapped), `exporter/exporter_ca65.py:149-174` (`_emit_table_read_lines` bank-switches before every table read and never restores bank 0 afterward), `main.py:596-618` / `main.py:999-1022` (DPCM packer stub tables — ending in `.segment "RODATA"` — appended to `music.asm` unconditionally whenever `dpcm_index.json` exists, regardless of whether the song has any DPCM content)
- **Status**: NEW
- **Description**: `NESProjectBuilder.prepare_project` appends the `--debug` overlay's
  generated assembly directly onto the end of `music_content` (`music_content += "\n" +
  overlay.generate_full_debug_system()`) with **no `.segment` directive of its own** at the
  top — `debug_init`/`debug_update`/`debug_test_apu` inherit whichever `.segment` was last
  active in the file. In the realistic pipeline (any invocation from the project root,
  where `dpcm_index.json` ships by default), `DpcmPacker.generate_assembly()` is appended
  to `music.asm` **unconditionally** whenever `dpcm_index.json` exists — even for a song
  with zero DPCM/drum notes, in which case it emits 4-byte dummy lookup tables — and its
  output always ends in `.segment "RODATA"` (`dpcm_sampler/dpcm_packer.py:119-130`). So the
  debug overlay's real 6502 instructions land in `RODATA`, not `CODE`.

  For NROM and MMC3 this is harmless: both mappers load `RODATA` and `CODE` into the *same*
  physical PRG region, so it doesn't matter which segment name the debug code nominally
  used. For **MMC1**, `RODATA` shares the physical `PRG_BANK_00` region — one of the 7
  switchable 16 KB windows at CPU `$8000-$BFFF` — while `CODE` (and `VECTORS`) load into
  `PRGFIXED`, the *always-mapped* `$C000-$FFFF` bank. `debug_init`/`debug_update` therefore
  get linked to an address in `$8000-$BFFF` that is only valid *while bank 0 happens to be
  switched in*.

  MMC1's direct-export bank-packing (`CA65Exporter._emit_table_read_lines`,
  `exporter/exporter_ca65.py:149-174`, added by #255) bank-switches before **every** table
  read (`note`/`control`/`timer_lo`/`timer_hi` per channel) and never switches back to bank
  0 afterward — the switch is a one-way "select whichever bank holds this table" operation.
  `play_music_frame`/`play_pulse1` (etc.) therefore leave *whatever bank the last table
  read needed* switched in when they `rts`. `nmi:` (`nes/project_builder.py:366-376`) calls
  `jsr update_music` (which ends by leaving that residual bank active) immediately followed
  by `jsr debug_update` with **no bank restore in between**. If the last table read left a
  bank other than 0 active, `jsr debug_update` jumps to `debug_update`'s *linked* address
  inside bank 0's physical data — but the CPU actually fetches whatever bytes are present
  in the *currently switched-in* bank at that same offset (part of a note/timer table),
  executing arbitrary data as 6502 opcodes.

  `debug_init`/`debug_test_apu` are safe at boot only because MMC1's `generate_init_code()`
  explicitly selects bank 0 immediately before `reset` calls them
  (`mappers/mmc1.py:generate_init_code`, `nes/project_builder.py:348,354`) — the bug is
  isolated to the *recurring* `jsr debug_update` inside every subsequent NMI.
- **Evidence**: Reproduced end-to-end. Exporting a 28.8 KB direct song with `--mapper mmc1`
  (from the repo root, so `dpcm_index.json` is picked up and its stub tables get appended)
  and building with `debug_mode=True`:
  ```
  $ grep -n "debug_init:\|\.segment\|debug_update:" proj/music.asm | tail -6
  1823:.segment "CODE"
  2015:.segment "RODATA"
  2037:debug_init:
  2067:.segment "ZEROPAGE"
  2070:.segment "BSS"
  2083:debug_update:
  ```
  `pulse1_note`/`pulse1_control` bin-packed into `RODATA_BANK_00`; `pulse1_timer_lo`/
  `pulse1_timer_hi` (the *last* two tables `play_pulse1` reads) bin-packed into
  `RODATA_BANK_01` — confirmed via the bank-switch comments the exporter emits:
  ```
  $ grep -n "Bank-switch for\|RODATA_BANK" music.asm
  13:.segment "RODATA_BANK_00"
  918:.segment "RODATA_BANK_01"
  1845:    ; Bank-switch for pulse1_note (...)         [-> bank 0]
  1906:    ; Bank-switch for pulse1_timer_lo (...)     [-> bank 1, left active]
  1930:    ; Bank-switch for pulse1_timer_hi (...)     [-> bank 1, left active]
  ```
  Assembling and linking with `ca65`/`ld65` (exit 0, no errors) and inspecting the map file:
  ```
  RODATA_BANK_00        008000  00B83F  ...
  RODATA_BANK_01        008000  00B83F  ...   <- same CPU range, different physical bank
  RODATA                00B840  00BB5C  ...   <- shares PRG_BANK_00's physical page
  debug_init                00B844 RLA
  debug_update              00B879 RLA
  debug_test_apu             00BAAC RLA
  ```
  `debug_update` is linked at CPU `$B879`, inside the switchable window, physically present
  only in bank 0's page of the ROM. After `play_pulse1` runs (leaving bank 1 selected),
  `jsr debug_update` at `$B879` executes whatever byte happens to sit at that offset inside
  **bank 1** (part of the `pulse1_timer_hi` table) instead of the real handler. No bank
  restore exists anywhere in `play_music_frame`/`play_pulse1`
  (`grep -n "@done:" music.asm` shows `rts` immediately, nothing else) or in the
  `nmi:`/`debug_update_call` template.
- **Impact**: Every ROM built with `--mapper mmc1 --debug` (implicitly `--no-patterns`,
  since MMC1 cannot run the bytecode engine) whose direct-export tables need more than one
  16 KB bank — i.e. any song exercising MMC1's actual purpose (its extra headroom over
  NROM's 30 KB). The ROM boots, `debug_init`/`debug_test_apu` run correctly, but the very
  first NMI's `jsr debug_update` executes arbitrary data as code: a near-certain crash/hang
  on real hardware and accurate emulators, or at best silently corrupted machine state that
  then also derails the *next* frame's music playback (registers/flags clobbered by
  whatever "instructions" the garbage bytes happened to decode to). `zero test coverage`:
  `tests/test_nes_project_builder.py`'s `debug_mode=True` cases all use the default mapper
  (MMC3), never MMC1 — confirmed via `grep -n "debug_mode=True" -A20 ... | grep mapper`
  showing only the MMC3-default assertion.
- **Related**: #255/MAP-2026-07-05-1 (introduced MMC1's per-table bank-packing/switching,
  which this finding's crash depends on); #213 (removed MMC1's old vector-fixup bug — a
  different, now-fixed MMC1 boot issue); no existing open issue covers this.
- **Hardware ref**: `docs/MAPPER_MMC1_REFERENCE.md` (switchable $8000-$BFFF window vs the
  fixed $C000-$FFFF bank — only one physical 16 KB page is CPU-visible at $8000 at a time,
  so any code placed there must either never be called while a different bank is selected,
  or the caller must guarantee the right bank is active first; `docs/NES_APU_REFERENCE.md`
  n/a here — this is a pure addressing/bank-state bug, not an APU register issue).
- **Suggested Fix**: Two complementary fixes: (1) In `nes/project_builder.py`, prepend an
  explicit `.segment "CODE"` line before appending the debug overlay text (and before the
  `fetch_sequence_byte`/DPCM-stub content, for the same reason), so debug code always lands
  in the mapper's *always-mapped* fixed region regardless of what segment happened to be
  active last — this is the direct fix and also removes the current reliance on incidental
  segment inheritance, which is fragile even where it happens to be harmless (NROM/MMC3).
  (2) Defense in depth: have `play_music_frame` (or the `nmi:` template when
  `mapper.direct_export_bank_size() is not None`) explicitly re-select bank 0 (or whatever
  bank debug code lives in) before returning/before `jsr debug_update`, so a future segment
  placement mistake fails safe. Add a regression test that builds an MMC1 `--debug` project
  with data spanning ≥2 banks and asserts (via the linker map or a bank-aware disassembly
  check) that every `.global`-exported symbol callable from the always-mapped region is
  itself linked into the always-mapped region.

---

### MAP-2026-08-05-2: The capacity pre-flight sizes only the exporter's raw `music.asm`, never the debug overlay / `fetch_sequence_byte` / DPCM-stub content `NESProjectBuilder` appends afterward
- **Severity**: MEDIUM
- **Dimension**: 4 (PRG capacity / overrun detection)
- **Location**: `nes/project_builder.py:140` (`check_mapper_capacity(music_asm_path, self.mapper)` — reads and sizes the *source* file passed in) vs. `nes/project_builder.py:142-148` (debug overlay, ~800+ real bytes measured below, appended *after* the check), `main.py:490-491` / `main.py:1069-1070` (the CLI's own pre-flight call, same ordering — before `NESProjectBuilder(..., debug_mode=...)` is even constructed)
- **Status**: NEW
- **Description**: Both call sites of `check_mapper_capacity` — `main.py`'s own
  pre-`prepare_project` call and `NESProjectBuilder.prepare_project`'s internal call
  (`#363/MAP-2026-07-19-3`'s fix) — run against the `music.asm` exactly as produced by
  `CA65Exporter`/`DpcmPacker`, strictly *before* `prepare_project` appends the `--debug`
  overlay, the bytecode-only `fetch_sequence_byte` routine, or the DPCM stub-table fallback.
  For a song already close to a mapper's declared budget, none of that additional content
  is accounted for by the pre-flight's clean error message — an overflow it causes surfaces
  only as a raw `ld65` region-overflow (or, per MAP-2026-08-05-1, doesn't even fail cleanly
  when it lands in the wrong logical place). Measured empirically: enabling `--debug` on a
  single-channel NROM direct-export project added the debug overlay's actual code
  (802 bytes) to the `CODE` segment in one test where no DPCM stub content had already
  claimed the `RODATA`/`CODE` tail-position — comfortably inside NROM's flat 2 KB
  code/vectors reserve in that case, but the reserve is a static constant
  (`BaseMapper.get_data_capacity`'s "~2KB for code/vectors", `mappers/base.py:169`;
  MMC3's `FIXED_BANK_ENGINE_RESERVE = 2048`, `mappers/mmc3.py:20`) sized for the base
  playback engine, not for an optional ~800-byte debug addition stacked on top of it — for
  a song that already consumes most of that reserve (a full 5-channel engine, or MMC3's
  much tighter `PRG_FIX` budget of ~6,138 bytes after reserve), `--debug` could still push
  the real total past the true region size while the pre-flight's "fits" message says
  otherwise.
- **Evidence**: `nes/project_builder.py:132-140`'s own comment states the check "Runs on
  the source music.asm (before any transforms below) ... matching what the CLI check
  sizes" — i.e. this is a deliberate, documented, but incomplete scope; it was never
  extended to cover what `prepare_project` itself adds afterward. Confirmed via a built
  NROM project (`ca65`/`ld65` + `-m map.txt`): `CODE` segment size was 249 bytes without
  `--debug` and 1,051 bytes with it — an 802-byte addition the pre-flight (run beforehand,
  and which in any case only counts `.byte`/`.word`/`.incbin` — see MAP-2026-08-05-3) never
  sees.
- **Impact**: Defense-in-depth only for mappers/songs where the true remaining slack
  exceeds the debug overlay's real size (confirmed safe for NROM/MMC3 in the specific cases
  tested this pass); becomes a real (if still `ld65`-caught) failure mode for a
  near-boundary song, and interacts with MAP-2026-08-05-1's segment-placement bug on MMC1
  in a way that isn't even guaranteed to fail at link time.
- **Related**: #363/MAP-2026-07-19-3 (moved the capacity gate into `NESProjectBuilder`
  itself, but did not extend its scope past the raw exporter output); #212/#127 (the
  region-aware capacity math this gap sits alongside).
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §2 (the `PRG_FIX` budget the reserve
  approximates); n/a for NROM/MMC1's flat reserve.
- **Suggested Fix**: Move the `check_mapper_capacity` call in `prepare_project` to *after*
  the debug overlay / `fetch_sequence_byte` / DPCM-stub content is appended to
  `music_content` (sizing the actual final `music.asm` that gets written and assembled),
  rather than the pre-transform source file. `main.py`'s own earlier call can stay for its
  fast, clean early-exit UX, but should no longer be treated as the last word — or should
  itself factor in an estimate for `--debug`'s known overhead when `args.debug` is set.

---

### MAP-2026-08-05-3: `estimate_segment_sizes` undercounts `.byte "string literal", ...` lines by counting comma-separated tokens instead of actual string length
- **Severity**: LOW
- **Dimension**: 4 (PRG capacity / overrun detection — the heuristic's documented weak spot)
- **Location**: `mappers/capacity.py:58-59` (`n = len([t for t in line[5:].split(',') if t.strip()])` — treats a quoted string as exactly one token/one byte, regardless of its length)
- **Status**: NEW
- **Description**: `estimate_segment_sizes` counts bytes on a `.byte` line by splitting on
  `,` and counting the resulting tokens — correct for `.byte $01, $02, $03` (3 tokens = 3
  bytes) but wrong for `.byte "MIDI2NES DEBUG v1.0", $00`: the string token contains no
  comma, so it's counted as **one** byte instead of its real 19 characters, undercounting
  this single line by 18 bytes. The debug overlay (`nes/debug_overlay.py`) emits 7 such
  string lines (a startup banner, 5 error strings, one "P1: " label) that would undercount
  by roughly 140 bytes combined if they were ever visible to the estimator at all — which,
  per MAP-2026-08-05-2, they currently aren't (the debug overlay is appended after the
  check runs), so this bug is latent/compounding rather than independently triggering an
  overflow today. It is also visible on the mapper header lines themselves: NROM's and
  MMC1's `generate_header_asm()` both emit `.byte "NES", $1A` (4 real bytes: N, E, S,
  `$1A`) which the estimator counts as 2 tokens.
- **Evidence**:
  ```
  $ python3 -c "
  from mappers.capacity import estimate_segment_sizes
  ... .byte \"NES\", \$1A / .byte \$02 / .byte \$00 / .byte \$00 / .byte \$00 x8 ...
  "
  segment sizes: {'HEADER': 13, 'RODATA': 30716}
  ```
  Real declared header content is 15 bytes (4+1+1+1+8; the 16th byte comes from `nes.cfg`'s
  `HEADER` region `fill=yes` zero-padding, harmless since `$00` is the correct value for
  the unset flags-7 byte) — the estimator reports 13, undercounting the string line by 2.
- **Impact**: Purely a heuristic-accuracy gap; `ld65` remains the exact backstop for any
  song this pushes past the true limit, so no ROM ships broken because of this alone. Rated
  LOW rather than MEDIUM because in every case found this pass the affected lines are
  either the fixed, tiny (16-byte) header, or content excluded from the check entirely
  today by MAP-2026-08-05-2 — fixing that finding would raise this one's real-world stakes
  and its severity should be revisited then.
- **Related**: MAP-2026-08-05-2 (the debug overlay content where this would actually bite);
  the `_audit-mappers` skill's Dimension 4 explicitly asks auditors to check for exactly
  this class of undercount.
- **Hardware ref**: n/a (assembler-text parsing, not NES hardware behavior).
- **Suggested Fix**: When a `.byte` line's token contains a quoted string, count its
  actual character length (handling escaped quotes if `ca65` syntax allows them) instead of
  treating it as one token; add a case for `.byte "some, string", $00` — the comma inside
  the string is also currently mis-parsed as a token separator, which would *overcount* in
  that specific case, so the fix should quote-aware-split rather than naively adjust the
  count.

---

## Dimensions with no findings

| # | Dimension | Result |
|---|-----------|--------|
| 1 | iNES header ↔ nes.cfg | `MEMORY` region sums still equal each mapper's `prg_rom_size`; mapper nibbles `$00`/`$10`/`$40` correct. NROM/MMC1 headers declare only 15 explicit bytes (rely on `nes.cfg`'s `fill=yes` zero-pad for the 16th, flags-7, byte) vs MMC3's 16 explicit bytes — functionally harmless (see MAP-2026-08-05-3) and not itself a header/`nes.cfg` mismatch. |
| 2 | Reset/NMI/IRQ vectors + 60 Hz NMI | `nmi`/`reset`/`irq` defined; `reset` enables NMI; `nmi` calls `jsr update_music` unconditionally on all 3 mappers. (The `--debug` interaction with MMC1's bank state is reported separately as MAP-2026-08-05-1 rather than folded in here, since it's a bank-switching bug, not a vector/definition bug — `nmi` itself is correctly defined and reachable.) |
| 3 | APU init in boot path | Direct `init_music` writes `$4017`/`$4015` + sweep-off; bytecode `audio_init` writes `$4011`/`$4017`/`$4015`. Unchanged since 2026-07-19 (no commits touched these paths). |
| 6 | MapperFactory auto-selection | #361/#362/#363 fixes verified in place: `direct_export_capacity()`/`auto_select(direct=True)` rank MMC3 correctly for direct exports (`mappers/mmc3.py:179-191`, `mappers/factory.py`); the direct-export DPCM marker (`"; Direct export DPCM (MMC3-only)"`) is stamped unconditionally whenever `frames.get('dpcm')` (`exporter/exporter_ca65.py:231-232`) and checked by `resolve_mapper` before the bank-pack marker (`main.py:259-296`, order: bytecode → direct-DPCM → bank-pack, matching the "can't be both" invariant); `NESProjectBuilder.prepare_project` calls `check_mapper_capacity` itself (`nes/project_builder.py:140`), independent of `main.py`. |
| 7 | Project builder writes buildable project | All 3 mappers still link (NROM/MMC1/MMC3, with and without `--debug`, confirmed via live `ca65`/`ld65` builds this pass). Every segment referenced in generated `main.asm`/`music.asm` exists in the active `nes.cfg`. (MAP-2026-08-05-1 is a *logical* placement bug within a segment that does exist on both sides, not a missing-segment/link-failure case — link succeeds every time.) |
| 8 | Compiler validation & CC65 surfacing | Unchanged since 2026-07-19 (no commits touched `compiler/compiler.py` or `compiler/cc65_wrapper.py`); `validate_project`/`assemble`/`link`/`check_toolchain` behavior re-confirmed by this pass's many live compiles all surfacing errors correctly when deliberately induced (e.g. the missing-DPCM-symbol case hit while constructing test fixtures produced a clean `ca65` error, not a silent pass). |
| 9 | ROM size check | Exact per-mapper check confirmed via live builds this pass: NROM 32,784 B, MMC1 131,088 B, MMC3 524,304 B — all match `prg_rom_size + 16` exactly. |
| 10 | Default-mapper doc drift | `grep -niE 'always use mmc1|default.*mapper|mmc1' README.md CLAUDE.md docs/*.md` clean — no source or doc reasserts MMC1 as *the* default; MMC3 consistently documented as default with MMC1/NROM selectable. |

Dimension 5 (bank-switching correctness) has one finding (MAP-2026-08-05-1, above) rather
than "no findings" — MMC1's 5-write serial load and MMC3's R6/R7 selects were re-checked
against `docs/MAPPER_MMC1_REFERENCE.md`/`docs/MAPPER_MMC3_REFERENCE.md` and remain correct;
the new finding is specifically about a *caller* (the debug overlay integration) not
respecting the bank-switching contract those primitives correctly implement.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-08-05.md
```
