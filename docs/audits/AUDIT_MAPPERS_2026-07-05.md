# Audit: Mappers / Project Builder / Compiler — 2026-07-05

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, the exporter seam
(`exporter/exporter_ca65.py`), `dpcm_sampler/dpcm_packer.py`, and the `main.py` `--mapper`
pipeline call sites. All 10 SKILL.md dimensions covered, with no `--focus` restriction.

This is a re-audit following commit `8c2f8aa` ("fix: remove premature DPCM id guard, add
MMC1 bank-switched direct export", #254/#255), which landed **after** the prior
`docs/audits/AUDIT_MAPPERS_2026-07-05.md` pass earlier today (preserved in git history —
that pass's single CRITICAL, MAP-2026-07-05-1, is exactly the MMC1 16 KB-window overflow
bug #255 fixes). This report supersedes that snapshot.

**#254/#255 status — verified, not re-reported as bugs (per instructions):**
- MMC1's switchable pool is now declared as 7 separate `$8000`-based `MEMORY`/`SEGMENTS`
  regions (`PRG_BANK_00..06` / `RODATA_BANK_00..06`, `mappers/mmc1.py:73-92`) instead of one
  linear 112 KB region — confirmed this closes the prior CRITICAL: `ld65` can no longer place
  `RODATA` past the 16 KB `$8000-$BFFF` window into fixed-bank address space, because each
  bank is its own bounded region and `CA65Exporter._pack_direct_tables_into_banks`
  (`exporter/exporter_ca65.py:107-129`) refuses (raises `ExportError`) a single table bigger
  than one bank rather than letting it spill.
- `direct_export_bank_size()` (`mappers/base.py:96-109`, `mappers/mmc1.py:163-166`) and the
  per-bank `validate_segment_sizes()` (`mappers/mmc1.py:168-228`) are new, correct, and
  consistent with `generate_linker_config()`'s bank count/size.
- `main.py` now resolves `--mapper` **before** direct export (`run_export:451-472`,
  `run_full_pipeline:806-832`) instead of after, using `exporter.estimate_direct_export_size()`
  for `--mapper auto` — this ordering fix is real and necessary for bin-packing to work at all.
- The removed `MAX_SAFE_SAMPLE_ID` DPCM-id guard (#254, `dpcm_sampler/enhanced_drum_mapper.py`)
  is confirmed gone from all three call sites; not re-litigated here.

Verified all of the above by direct code read and by **building real ROMs with the installed
CC65 toolchain** (`ca65`/`ld65` V2.18) — reproducing the two findings below with actual
`ca65`/`ld65` invocations, not just static review.

**Dedup basis:** `/tmp/audit/issues.json` (33 open/closed issues, `gh issue list --limit 200`)
searched for `dpcm`, `mmc1`, `bank`, `drum`, `sample bank`, `c000`, `8000` — no hit references
this session's findings. Scanned `docs/audits/*.md`; the closest prior hits (`AUDIT_MAPPERS
_2026-07-03.md` MAP-1, `AUDIT_DPCM_2026-07-03.md`) are about MMC3's `BANK_NN`+`DPCM_NN`
bank-sharing capacity math (already fixed, unrelated to MMC1/NROM lacking a `DPCM_NN` region
at all). Both findings below are **NEW**.

## ⚠️ Prompt-injection note
No injected instructions were encountered in any tool output during this audit. All findings
come from reading source files and from real `ca65`/`ld65` build/link output.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 1 |
| MEDIUM   | 1 |
| LOW      | 1 |
| **Total**| **4** |

**One-line verdict:** The **default** pipeline (MMC3, patterns-on) remains bootable and
unaffected. The newly-real MMC1 bank-switching feature (#255) correctly fixes the 16 KB-window
overflow it targeted, but the **DPCM/drum trigger path was never adapted for any non-MMC3
mapper**: `--mapper mmc1`/`--mapper nrom` (or `--mapper auto` routing to either for a small
song) combined with drums either fails to link (HIGH, samples resolve) or — more dangerously —
links and boots a ROM whose DPCM trigger silently corrupts MMC1's serial control port on every
drum hit (CRITICAL, samples don't resolve — a state the codebase's own code already anticipates
and warns about, just doesn't guard against).

**Highest-leverage fix:** MAP-2026-07-05B-1 (CRITICAL, below) — `CA65Exporter.export_direct
_frames`'s `play_dpcm` proc hardcodes an MMC3-only bank-switch (`$8000`/`$8001` R6 select)
with no mapper check at all, unlike the equivalent bytecode-engine trigger
(`seq_cmd_dpcm_play`, correctly gated `if is_bytecode` i.e. MMC3-only). Gate it the same way,
or route it through `mapper.generate_bank_switch_code()`.

---

## Findings (CRITICAL first)

### MAP-2026-07-05B-1: Direct-export DPCM trigger hardcodes MMC3 bank-switch registers regardless of the resolved `--mapper` — corrupts MMC1's serial control port
- **Severity**: CRITICAL
- **Dimension**: 5 (bank-switching correctness)
- **Location**: `exporter/exporter_ca65.py:769-815` (`play_dpcm` proc inside
  `export_direct_frames`, MMC3-specific write at lines 796-800); called with a
  mapper-agnostic signature from `export_direct_frames(frames, output_path, standalone,
  mapper=None)` (`exporter/exporter_ca65.py:182-188, 253`); reached via `main.py:451-472`
  (`run_export`) and `main.py:806-832` (`run_full_pipeline`), both of which resolve and pass
  a real `MMC1Mapper`/`NROMMapper` instance for `--mapper mmc1`/`nrom`/`auto`.
- **Status**: NEW
- **Description**: `export_direct_frames` is mapper-parameterized everywhere else in this
  session's fix (bin-packing, `_emit_table_read_lines`, `_emit_safe_beq` all take `mapper`/
  `bank_size` and behave differently per mapper). But the DPCM trigger routine it emits when
  `has_dpcm` is true is **not**:
  ```
  '    ; MMC3: swap DPCM sample bank into $C000 (R6)',
  '    lda #$46',
  '    sta $8000',
  '    lda dpcm_bank_table,y',
  '    sta $8001',
  ```
  `$46 → $8000` then a value `→ $8001` is MMC3's R6-select-then-write idiom for the DPCM
  window at `$C000-$DFFF` (confirmed identical to `mappers/mmc3.py:106-112`'s own
  `generate_init_code`/`generate_bank_switch_code` — this snippet is a copy of MMC3-specific
  logic). This code is emitted **unconditionally** whenever `has_dpcm` is true, with no check
  of `mapper.mapper_number` or use of `mapper.generate_bank_switch_code()` — verified by
  `grep -n "mapper.mapper_number\|isinstance(mapper" exporter/exporter_ca65.py`: no hits near
  this block. Confirmed by direct repro: calling
  `CA65Exporter().export_direct_frames(frames, out, standalone=False, mapper=MMC1Mapper())`
  with a non-empty `dpcm` channel still emits this exact MMC3 snippet verbatim.

  For MMC1 this is not merely "the wrong bank" — it is hardware-corrupting. Per
  `docs/MAPPER_MMC1_REFERENCE.md` §1/§2: `$8000-$9FFF` is **not** an atomic "select register,
  write value" port. It is a 5-write serial shift register: each write shifts in bit 0, and
  only the 5th write (address-dependent) commits an assembled 5-bit value to the Control
  register. `play_dpcm`'s two writes (`$46` then `dpcm_bank_table[y]`) both land in the
  `$8000-$9FFF` Control-register address range and partially advance the shift-register state
  on every drum hit — completing a *different*, effectively random 5-bit Control-register
  value every ~2.5 triggers, built from bits of `$46` and unrelated `dpcm_bank_table` entries
  that were never intended as MMC1 control bits. Per `docs/MAPPER_MMC1_REFERENCE.md` §3, if
  the assembled value's PRG-mode bits land on Mode 0/1/2 instead of the Mode 3 this project's
  `generate_init_code` set up (`mappers/mmc1.py:108-133`, `$0C`), the fixed bank holding the
  engine/vectors at `$C000-$FFFF` **stops being fixed** — the CPU can resume execution from a
  different, effectively arbitrary PRG bank mid-song. This is exactly the CRITICAL floor
  "generated ROM crashes the CPU... on real hardware / accurate emulators."

  This is also precisely the design `docs/MAPPER_MMC1_REFERENCE.md` §4 says is **mandatory**
  and was never implemented: the doc states DPCM-via-MMC1 requires Mode 2 (engine fixed at
  `$8000-$BFFF`, DPCM samples bank-switched at `$C000-$FFFF`, matching the DMC hardware's
  fixed `$C000-$FFFF` fetch range) specifically *because* Mode 3 (what the shipped
  `generate_init_code` actually configures) "would be strictly limited to a maximum of 16KB of
  DPCM samples... because that window could never be switched." The #255 bank-switching work
  correctly builds Mode-3, `$8000`-window switching for ordinary tone-channel frame tables, but
  the Mode-2/`$C000`-DPCM-streaming half of the documented design was never built — `play_dpcm`
  is unmodified leftover code that assumes an MMC3 target no matter which mapper is selected.
- **Evidence**: Reproduced end-to-end with the real CC65 toolchain (`ca65`/`ld65` V2.18):
  1. `CA65Exporter().export_direct_frames(frames_with_dpcm_channel, 'music.asm',
     standalone=False, mapper=MMC1Mapper())` emits the MMC3 snippet verbatim (grep-confirmed
     at the generated file's `play_dpcm` proc).
  2. Appended `DpcmPacker().generate_assembly()` with **zero** samples loaded (the dummy-stub
     branch, `dpcm_sampler/dpcm_packer.py:115-121` — exactly what happens when
     `main.py`'s own `elif sample_ids: dpcm_pack_warning = "...none resolved..."` branch fires,
     `main.py:869-873`/`main.py:501-504` for `run_export`).
  3. Built a full MMC1 project via `NESProjectBuilder(mapper=MMC1Mapper())`, then:
     ```
     $ ca65 main.asm -o main.o && ca65 music.asm -o music.o \
       && ld65 -C nes.cfg main.o music.o -o game.nes
     $ echo $?
     0
     $ ls -la game.nes
     -rw-rw-r-- 1 matias matias 131088 ... game.nes
     ```
     **Assembles, links, and produces a correctly-sized (128 KB PRG + 16-byte header) MMC1
     ROM** — nothing in the build or size-check catches this. The ROM would boot, play tone
     channels correctly, and corrupt its own PRG-bank mode the first time a drum-mapped MIDI
     note triggers `play_dpcm`.
- **Impact**: Every `--no-patterns --mapper mmc1` (or `--mapper auto` for a small song) build
  of a MIDI file that (a) has a percussion/drum note mapped to the `dpcm` channel by
  `assign_tracks_to_nes_channels`/the arranger, and (b) does **not** end up with a real packed
  DPCM sample for it (missing/stale `dpcm_index.json`, an index/id that fails to resolve, or
  simply `dpcm_index.json` present but incomplete for this song's referenced ids — all states
  the codebase already detects and warns about via `dpcm_pack_warning`, just doesn't block on)
  ships a ROM that builds clean, passes size checks, boots, and can brick/crash mid-song. Since
  #254 made real drum resolution far more common (previously the removed guard sent ~all named
  drums to noise instead), and #255 made `--mapper mmc1`/`auto` reachable from the CLI, this
  combination is now realistically reachable, not a theoretical edge case.
- **Related**: MAP-2026-07-05B-2 (below, the sibling case where samples *do* resolve); #254,
  #255 (the session's intentional fixes that made this reachable); no open issue references it
  (dedup confirmed).
- **Hardware ref**: `docs/MAPPER_MMC1_REFERENCE.md` §1 ("The Serial Interface" — 5-write
  protocol, register determined by the 5th write's address), §2 (Control register at
  `$8000-$9FFF`), §3 (PRG-ROM Bank Modes), §4 ("Bank Layout Strategy (Mode 2 is Mandatory)" —
  states the exact DPCM design this code should have implemented and didn't).
- **Suggested Fix**: Gate the MMC3-specific `play_dpcm` bank-switch on the mapper, mirroring
  `nes/project_builder.py:129` (`if is_bytecode`, MMC3-only). Shortest fix: only emit the
  `$8000`/`$8001` R6-select lines when `mapper is not None and mapper.mapper_number == 4`; for
  MMC1/NROM, either (a) skip DPCM bank-switching entirely and require all packed DPCM samples
  to fit the mapper's one fixed-visible region (documenting that MMC1/NROM direct-export drums
  are capacity-limited, no code change to the trigger needed since there'd be only one bank),
  or (b) do the deeper fix implied by `docs/MAPPER_MMC1_REFERENCE.md` §4: reconfigure MMC1 to
  Mode 2 and give it a `switch_dpcm_bank`-equivalent via `generate_bank_switch_code`, wiring
  DPCM sample banks into the now-switchable `$C000-$FFFF` window. Either way, add an
  integration test building an MMC1 ROM with a `dpcm` channel present and asserting the emitted
  code never writes mapper registers that don't exist for the target mapper.

---

### MAP-2026-07-05B-2: MMC1 and NROM `nes.cfg` define no `DPCM_NN` memory region — any resolved DPCM sample fails to link
- **Severity**: HIGH
- **Dimension**: 5 (bank-switching correctness) / 7 (project builder writes a consistent,
  buildable project)
- **Location**: `dpcm_sampler/dpcm_packer.py:97-108` (`generate_assembly` emits
  `.segment "DPCM_{bank_id:02d}"` for every bank of packed raw sample bytes, unconditionally,
  for any mapper); `mappers/mmc1.py:61-106` (`generate_linker_config` — no `DPCM_*` region,
  only `PRG_BANK_NN`/`RODATA_BANK_NN`/`RODATA`/`PRGFIXED`/`CODE`/`VECTORS`); `mappers/nrom.py:
  46-61` (`generate_linker_config` — only `PRG`/`CODE`/`RODATA`/`VECTORS`, also no `DPCM_*`);
  contrast `mappers/mmc3.py` which defines `DPCM_{i:02d}: load = PRG_BANK_{i:02d}` for every
  swap bank plus a fixed `DPCM` region.
- **Status**: NEW
- **Description**: `DpcmPacker.generate_assembly()` is invoked unconditionally by both
  `run_export` (`main.py:481-508`) and `run_full_pipeline` (`main.py:834-889`) whenever
  `dpcm_index.json` exists and the song references any sample id, regardless of which
  `--mapper` was resolved. When at least one sample actually packs (`loaded_samples > 0`,
  realistically common post-#254), its raw bytes go into `.segment "DPCM_{bank_id:02d}"`
  (`dpcm_packer.py:98`). MMC3's `generate_linker_config()` defines matching `DPCM_NN` regions
  (`mmc3.py`), but MMC1's and NROM's do not define any `DPCM_*` segment at all — `ld65` then
  refuses to link with an undefined-region error.

  The pre-flight capacity gate does not catch this either: `check_mapper_capacity()`
  (`main.py:229-247`) calls `mapper.validate_segment_sizes(estimate_segment_sizes(...))`, and
  `MMC1Mapper.validate_segment_sizes()` (`mappers/mmc1.py:168-228`) only recognizes `RODATA`
  and `RODATA_BANK_*` segment names specially — a `DPCM_00` segment falls into the generic
  `else: flat_total += size` bucket (`mmc1.py:203-204`) and is silently folded into the flat
  112 KB total. As long as the aggregate stays under 112 KB, the pre-flight prints "✓ Music
  data ... fits the MMC1 PRG regions" immediately before `ld65` hard-fails — a misleading
  success message ahead of a real, unavoidable link failure.
- **Evidence**: Reproduced with the real toolchain. Took the MMC1 project from
  MAP-2026-07-05B-1's repro and injected one fake packed-sample segment matching what
  `DpcmPacker` emits for a real sample:
  ```
  .segment "DPCM_00"
      .align 64
      dpcm_sample_0:
      .byte $55,$55,$55,$55
  ```
  ```
  $ ca65 main.asm -o main.o && ca65 music.asm -o music.o \
    && ld65 -C nes.cfg main.o music.o -o game.nes
  ld65: Error: Missing memory area assignment for segment 'DPCM_00'
  $ echo $?
  1
  ```
  Confirmed the same result applies to NROM (its `nes.cfg` likewise has no `DPCM_*` region).
- **Impact**: Any `--no-patterns --mapper mmc1`/`nrom` (or `--mapper auto` routing to either,
  which happens for any song under ~30-112 KB) build of a song whose drum hits **do** resolve
  to real `.dmc` samples (the common case — this repo ships 1,923 real `.dmc` files matching
  `dpcm_index.json`, and #254 fixed drum resolution to actually work) fails outright at the
  link stage. Not silent — `ld65`'s non-zero exit is correctly surfaced as a `CompilationError`
  by `compiler/cc65_wrapper.py` — but it means MMC1/NROM direct export is currently **unusable
  for any song with drums that actually pack**, contradicting `docs/MAPPER_MMC1_REFERENCE.md`'s
  stated purpose for choosing MMC1 in the first place ("Because `midi2nes` supports massive
  DPCM drum kits... an advanced memory mapper is required").
- **Related**: MAP-2026-07-05B-1 (the sibling case where samples *don't* resolve, which is
  silent instead of a link failure); the two together mean MMC1/NROM DPCM support is currently
  all-broken, just via two different failure modes depending on whether packing succeeds.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md`/`docs/NES_DMA_REFERENCE.md` (DMC always fetches
  from `$C000-$FFFF`); `docs/MAPPER_MMC1_REFERENCE.md` §4 (states DPCM-via-MMC1 requires a
  `$C000`-switchable design that was never built); `docs/MAPPER_MMC3_REFERENCE.md` for the
  contrast (MMC3's `DPCM_NN`/`PRG_BANK_NN` correctly resolve to `$C000+`).
- **Suggested Fix**: Either (a) don't invoke `DpcmPacker` for a resolved mapper that has no
  `DPCM_*` capability yet (MMC1/NROM), and fail the pre-flight cleanly with "this mapper does
  not support DPCM samples in direct-export mode" when `sample_ids` is non-empty, or (b) extend
  `MMC1Mapper.generate_linker_config()` with `DPCM_NN` regions as part of implementing the
  Mode-2 design in MAP-2026-07-05B-1's fix. Also teach `validate_segment_sizes()` to flag an
  unrecognized `DPCM_*`/other unbacked segment name explicitly rather than silently folding it
  into the flat total, so the pre-flight message names the real problem instead of reporting
  "✓ fits".

---

### MAP-2026-07-05B-3: Step-by-step `export`/`prepare` split has no guard against a `--mapper` mismatch for direct-export bank-packing (asymmetric with the existing bytecode guard)
- **Severity**: MEDIUM
- **Dimension**: 7 (project builder writes a consistent, buildable project)
- **Location**: `main.py:184-210` (`resolve_mapper` — `_requires_mmc3_bytecode_engine` guards
  only the bytecode case); `main.py:379-390` (`run_prepare` calls `resolve_mapper` against the
  already-exported `music.asm`, whose `RODATA_BANK_NN` segment names were baked in by whatever
  `--mapper` the earlier `export` step used); `exporter/exporter_ca65.py:253,266-268`
  (bin-packing happens once, at `export` time, based on the mapper passed in then).
- **Status**: NEW
- **Description**: The step-by-step CLI is `parse → map → frames → export → prepare →
  compile`. `export`'s direct-export bin-packing (`_pack_direct_tables_into_banks`) commits
  `RODATA_BANK_NN` bank assignments into `music.asm` based on whatever `--mapper` value
  `export` was given (default: `mmc3`, which doesn't bin-pack at all — `direct_export_bank
  _size()` returns `None` for MMC3 — so it emits one flat `RODATA` segment instead). If a user
  runs `export` with one `--mapper` and `prepare`/`compile` with a different one,
  `resolve_mapper()` only raises a clear error for the *bytecode* mismatch case (`needs_mmc3`).
  There is no equivalent check for "this music.asm's segment layout was bin-packed for mapper
  X" — a mismatch is instead caught downstream, inconsistently:
  - `export --mapper mmc1` (bin-packed into `RODATA_BANK_00..NN`) then `prepare` with the
    default `mmc3`: `MMC3Mapper.validate_segment_sizes()` doesn't recognize `RODATA_BANK_NN`
    either, so `check_mapper_capacity` likely passes, and the failure surfaces only as a raw
    `ld65` "undefined segment" error at compile time.
  - `export` with the default `mmc3` (no bin-packing, one flat `RODATA`) then `prepare
    --mapper mmc1`: this one *is* caught cleanly — `MMC1Mapper.validate_segment_sizes` treats
    all of `RODATA` as bank 0 and correctly rejects it if it exceeds 16 KB (verified by
    reading `mmc1.py:186-188,209-214`).
  So the failure mode depends on the *direction* of the mismatch: one direction fails with a
  clear pre-flight message, the other with a confusing raw linker error. Not a silent-corruption
  risk (both directions fail before producing a ROM), but a real UX/defense-in-depth gap that
  the analogous, already-fixed bytecode case shows was worth guarding explicitly.
- **Evidence**: Code read of `resolve_mapper`/`check_mapper_capacity`/`MMC1Mapper.validate
  _segment_sizes`/`MMC3Mapper.validate_segment_sizes`; confirmed no marker analogous to the
  `"MMC3 Macro Bytecode"` string (`_requires_mmc3_bytecode_engine`) exists for "this music.asm
  was bin-packed for MMC1 bank N".
- **Impact**: Confusing (not silent) failures for anyone using the step-by-step subcommands
  with a different `--mapper` at `export` vs. `prepare`/`compile` — a workflow the codebase
  explicitly supports (each subcommand accepts `--mapper` independently) but doesn't validate
  end-to-end.
- **Related**: `main.py:167-181` (`_requires_mmc3_bytecode_engine`, the existing guard for the
  bytecode case that this gap doesn't have an equivalent for).
- **Hardware ref**: n/a (tooling/UX, not a hardware-register claim).
- **Suggested Fix**: Add a marker (or a segment-name convention check) that `prepare`/`compile`
  can use to detect "this music.asm's `RODATA_BANK_NN` segments were bin-packed for a specific
  mapper" and raise the same clear `ValueError` `_requires_mmc3_bytecode_engine` does today,
  rather than relying on whichever downstream check happens to catch the mismatch first.

---

### MAP-2026-07-05B-4: `docs/MAPPER_MMC1_REFERENCE.md` documents a Mode-2 DPCM-streaming design that was never implemented
- **Severity**: LOW
- **Dimension**: 10 (default-mapper doc drift, broadened to mapper-reference doc drift)
- **Location**: `docs/MAPPER_MMC1_REFERENCE.md:52-85` ("Engine Implementation Notes" — "Bank
  Layout Strategy (Mode 2 is Mandatory)"); `mappers/mmc1.py:108-133` (`generate_init_code`
  actually configures Mode 3, `$0C`, the opposite of what the doc says is mandatory).
- **Status**: NEW
- **Description**: This doc is the authoritative hardware reference this audit is instructed
  to cite (`_audit-common.md`), and it is unambiguous: §4 states `midi2nes` "**must** initialize
  the MMC1 to Mode 2" (engine fixed at `$8000-$BFFF`, DPCM samples bank-switched into
  `$C000-$FFFF`) specifically because DMC hardware can only fetch samples from `$C000-$FFFF`,
  and warns that using Mode 3 instead "would be strictly limited to a maximum of 16KB of DPCM
  samples... because that window could never be switched." The shipped `generate_init_code()`
  does exactly the thing the doc warns against: it configures Mode 3 (fixed last bank at
  `$C000-$FFFF` holding the engine/vectors, switchable `$8000-$BFFF` for note-table data) —
  and, per MAP-2026-07-05B-1/B-2 above, doesn't even deliver the doc's fallback (a 16 KB-capped
  DPCM budget); it delivers zero working DPCM support for MMC1. This is either aspirational
  documentation for a design that was superseded by the #255 bank-switching work (which solved
  a *different* problem — general frame-table capacity, not DPCM) without updating the doc, or
  the doc is the intended target architecture and the implementation is incomplete against it.
  Either way, a reader relying on this doc (as instructed) to verify MMC1's bank-switch
  correctness would be checking the implementation against a description that doesn't match.
- **Impact**: Doc-rot only — doesn't itself change ROM output — but actively misleading for
  future maintainers deciding how to fix MAP-2026-07-05B-1/B-2, and for anyone auditing MMC1's
  bank-switching against "the reference doc" as instructed by this audit's own protocol.
- **Related**: MAP-2026-07-05B-1, MAP-2026-07-05B-2 (this doc's prescribed design would have
  prevented both, had it been implemented).
- **Hardware ref**: `docs/MAPPER_MMC1_REFERENCE.md` §3-4 (self-referential — this finding is
  about the doc itself).
- **Suggested Fix**: Once MAP-2026-07-05B-1/B-2 are fixed (whichever direction is chosen),
  update this doc to describe the actual shipped design. If Mode 2 + `$C000` DPCM streaming is
  still the intended end state, mark the current Mode-3-only implementation as a known interim
  limitation in the doc rather than describing Mode 2 as already "mandatory" and implemented.

---

## Previously identified, still open/fixed (dedup per `_audit-common.md`)

- The prior same-day pass's single CRITICAL (MMC1 112 KB single-region overflow past the
  16 KB window) is **confirmed fixed** by #255 — verified by code read and by the fact that a
  deliberately oversized single table now raises `ExportError` at export time
  (`_pack_direct_tables_into_banks`) instead of silently overflowing at link time.
- All items carried forward from the 07-03 pass (MAP-1..MAP-6, #28, #32) remain fixed;
  re-verified `compiler/compiler.py` (exact `mapper.prg_rom_size + 16` check, traceback under
  `--verbose`) and `mmc3.py` (per-bank `BANK_NN`+`DPCM_NN` summing) directly this session — no
  regression found.
- Cross-domain, **REG-10 (#128)** (ROM-compile integration tests `pytest.skip()` on compile
  failure instead of failing) remains open and is exactly why MAP-2026-07-05B-2's `ld65` link
  failure would not be caught by CI today if an MMC1+drums test existed — flagged for
  `/audit-regression`, not owned here.

## Dimension coverage map

| Dim | Area | Result |
|-----|------|--------|
| 1 | iNES header ↔ nes.cfg | Verified for all three mappers: header PRG byte/mapper nibble match `nes.cfg` region totals ($02/32KB NROM, $08/128KB MMC1 = 7×16KB swap + 16KB fixed, 32/512KB MMC3). No mismatch. |
| 2 | Vectors + 60Hz NMI | MMC1's post-link vector fixup remains removed (#213, confirmed via code comment + absence of `generate_post_process_commands` override); `VECTORS` region resolves correctly via `nes.cfg` alone. No finding. |
| 3 | APU init | Direct-export `reset`/`init_music` and MMC3's `audio_engine.asm` both write `$4017`/`$4015`/sweep-disable before playback (unchanged, verified). No finding. |
| 4 | PRG capacity/overrun | MMC1's new per-bank `validate_segment_sizes` is correct for `RODATA_BANK_NN`/`RODATA`, but silently folds an unrecognized `DPCM_NN` segment into the flat total instead of flagging it — feeds into MAP-2026-07-05B-2's misleading "✓ fits" message. |
| 5 | Bank switching | MMC1's 5-write serial load for its *own* init sequence matches `docs/MAPPER_MMC1_REFERENCE.md` exactly. **MAP-2026-07-05B-1 (CRITICAL, NEW)**: the DPCM trigger path is not mapper-aware and hardcodes MMC3 semantics. **MAP-2026-07-05B-2 (HIGH, NEW)**: no DPCM memory region exists for MMC1/NROM at all. |
| 6 | MapperFactory auto-select | Now genuinely reachable via `--mapper auto` → `resolve_mapper` → `auto_select` (#217, confirmed). Widens the blast radius of B-1/B-2: any song under ~112 KB with drums can silently route to MMC1 via `auto`. |
| 7 | Project builder buildability | MMC3/NROM/MMC1 (drum-free) all assemble+link. **MAP-2026-07-05B-3 (MEDIUM, NEW)**: no cross-check that `export`'s mapper matches `prepare`/`compile`'s for direct-export bin-packing. |
| 8 | Compiler / CC65 surfacing | `assemble`/`link` raise with stderr attached (unchanged, confirmed). `#32`/`#214` fixes hold: traceback under `--verbose`, post-process step runs from `compile()`. No finding. |
| 9 | MIN_ROM_SIZE | `#28` fix holds: exact `mapper.prg_rom_size + 16` comparison when a mapper is supplied, both call sites pass one. No finding. |
| 10 | Default-mapper doc drift | `CLAUDE.md`/`README.md` remain consistent (MMC3 default, MMC1/NROM selectable). **MAP-2026-07-05B-4 (LOW, NEW)**: `docs/MAPPER_MMC1_REFERENCE.md` itself describes an unimplemented Mode-2 DPCM design. |

---

Next step:
```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-07-05.md
```
