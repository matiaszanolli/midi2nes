# Audit: Mappers / Project Builder / Compiler — 2026-08-06

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3, capacity), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, and the `main.py` `--mapper`
resolution / capacity pre-flight / `resolve_mapper` / `enforce_direct_export_dpcm_mapper`
call sites. All 10 SKILL.md dimensions covered; no `--focus` restriction. Audited tree:
branch `fix/issues-136-137-167-202` (HEAD `20f627e`), which is even with `master` for this
subsystem (no mapper/project-builder/compiler commits landed on this branch or `master`
since the prior pass).

**Method:** re-verified every claim in `AUDIT_MAPPERS_2026-08-05.md` against the live
checkout rather than trusting the prior pass's "fixed" verdicts, per this skill's
standing instruction to hunt for edge cases in *fixed* behavior. That prior pass's three
new findings (MAP-2026-08-05-1/2/3, filed as #388/#389/#390) were all closed on GitHub
with linked fix commits — but `git merge-base --is-ancestor` shows **none of those three
commits (`df924b1`, `6e10aec`) are ancestors of `master` or of this branch**; they exist
only on unmerged topic branches (`fix/issue-388-mmc1-debug-bank-overlay`,
`fix/issues-389-390-mapper-capacity-preflight`). Direct inspection of
`nes/project_builder.py`, `nes/debug_overlay.py`, and `mappers/capacity.py` in the audited
tree confirms the pre-fix code is exactly what's checked out today — the GitHub issue
"Closed" state does not reflect the audited codebase's actual behavior. All three are
reported below as still-present, re-verified against the file contents currently on disk
(not the closing commits' diffs).

**Dedup basis:** `/tmp/audit/issues.json` (19 open issues, default `gh issue list` state)
searched for `mapper`, `mmc1`, `mmc3`, `nrom`, `bank`, `capacity`, `debug`, `vector`,
`header`, `cc65`, `ld65`, `prg`, `nmi`, `compile` — no open issue duplicates the findings
below. `gh issue view` on #388/#389/#390 (closed) confirms each has a single closing
comment naming a fix commit; per §Deduplication step 5 ("If CLOSED: verify the fix is in
place. If regressed, report as Regression of #NNN") the fix was verified **not** in place,
so these are reported as the original issues still open in the audited tree, not as new
IDs and not as "regressions" (the code never changed here — the fix simply never merged).
All prior `docs/audits/AUDIT_MAPPERS_*.md` (2026-06-28 … 2026-08-05) reviewed.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 1 |
| **Total** | **3** |

**Highest-leverage fix:** merge the already-written, already-verified fix commit
`df924b1` (branch `fix/issue-388-mmc1-debug-bank-overlay`) into `master` — the code exists,
is correct, and was empirically confirmed via a real `ca65`/`ld65` build in the prior
audit pass; it simply isn't in the branch being shipped.

**One-line verdict:** The **default** single-command pipeline (MMC3, patterns-on,
no `--debug`) remains unaffected and produces a bootable 512 KB ROM end-to-end, but
`--mapper mmc1 --debug` (necessarily also `--no-patterns`) still reproducibly crashes on
the first NMI for any song needing more than MMC1's first 16 KB bank — the fix for this
was written a day ago but has not reached the branch this audit examined.

---

## Findings

### MAP-2026-08-06-1: `--debug` + `--mapper mmc1` still links `debug_update` into a switchable bank with no bank restore — fix exists but is unmerged
- **Severity**: CRITICAL
- **Dimension**: 5 (bank-switching correctness), cross-cutting with 2 (NMI 60Hz call) and 7 (project builder consistency)
- **Location**: `nes/project_builder.py:142-148` (debug overlay text appended to `music_content` with no leading `.segment` directive), `nes/project_builder.py:306-376` (`debug_update_call` has no bank-0 restore before `nmi:`'s `{debug_update_call}` interpolation), `nes/debug_overlay.py:605-624` (`generate_full_debug_system()` emits no `.segment` directive of its own), `mappers/mmc1.py:99,102` (`RODATA: load = PRG_BANK_00` — switchable — vs `CODE: load = PRGFIXED` — always-mapped), `exporter/exporter_ca65.py:622,695` (`mapper.direct_export_bank_size()` already exists and is used elsewhere in the exporter, but `project_builder.py`'s debug path never calls it)
- **Status**: Existing: #388 — **CLOSED on GitHub but the fix is not in the audited tree.** The closing comment names commit `df924b1` ("fix: give the --debug overlay its own CODE segment and restore bank 0 before debug_update on MMC1 (#388)") on branch `fix/issue-388-mmc1-debug-bank-overlay`. `git merge-base --is-ancestor df924b1 HEAD` and `... master` both report false — the commit is not merged anywhere it would take effect. Direct reads of `nes/project_builder.py` and `nes/debug_overlay.py` on this branch show the exact pre-fix code (`music_content += "\n" + overlay.generate_full_debug_system()` with no `.segment "CODE"` prefix, and `debug_update_call` with no bank-restore prelude), i.e. the underlying bug described in #388/MAP-2026-08-05-1 is unchanged.
- **Description**: `NESProjectBuilder.prepare_project` appends the `--debug` overlay's
  generated assembly directly onto the end of `music_content` with no `.segment`
  directive of its own — `debug_init`/`debug_update`/`debug_test_apu` inherit whichever
  `.segment` was last active in the file (in the realistic pipeline, `.segment "RODATA"`,
  left by the DPCM packer's stub tables, which are appended unconditionally whenever
  `dpcm_index.json` exists). For NROM and MMC3, `RODATA` and `CODE` load into the same
  physical PRG region, so this is harmless. For **MMC1**, `RODATA` shares the physical
  `PRG_BANK_00` region — one of the switchable 16 KB windows at CPU `$8000-$BFFF` — while
  `CODE`/`VECTORS` load into `PRGFIXED`, the always-mapped `$C000-$FFFF` bank. MMC1's
  direct-export bank-packing (`CA65Exporter._emit_table_read_lines`) bank-switches before
  every table read and never restores bank 0 afterward, so `play_music_frame` can leave an
  arbitrary bank selected on return. `nmi:` calls `jsr update_music` (leaving that residual
  bank active) immediately followed by `jsr debug_update` with no bank restore in between —
  if the last table read left a bank other than 0 active, the CPU fetches whatever bytes
  physically sit at `debug_update`'s linked offset in *that* bank (part of a note/timer
  table) and executes them as 6502 opcodes.
- **Evidence**: Re-read every file/line cited in the original AUDIT_MAPPERS_2026-08-05
  finding on this checkout — all match the pre-fix state verbatim:
  ```
  $ grep -n 'generate_full_debug_system\|segment "CODE"' nes/project_builder.py
  148:            music_content += "\n" + overlay.generate_full_debug_system()
  ```
  (no `.segment "CODE"` line precedes it, unlike the fix commit's diff which inserts one).
  ```
  $ grep -n 'debug_update_call = ' -A2 nes/project_builder.py
  306:        debug_update_call = ""
  ...
  321:            debug_update_call = """
  322:    ; Update debug overlay
  ```
  (no `mapper.generate_bank_switch_code(0)` prelude, unlike the fix commit's diff).
  ```
  $ git merge-base --is-ancestor df924b1 HEAD && echo YES || echo NO
  NO
  $ git merge-base --is-ancestor df924b1 master && echo YES || echo NO
  NO
  ```
- **Impact**: Unchanged from the original finding: every ROM built with
  `--mapper mmc1 --debug` (implicitly `--no-patterns`) whose direct-export tables need
  more than one 16 KB bank boots, runs `debug_init`/`debug_test_apu` correctly, then
  executes arbitrary data as code on the first NMI that follows a multi-bank table read —
  a near-certain crash/hang on hardware and accurate emulators.
- **Related**: #388 (original report, closed but unmerged); #255/MAP-2026-07-05-1
  (introduced the per-table bank-switching this bug depends on); #213 (a different, already
  and correctly fixed MMC1 boot issue — the old post-link vector fixup).
- **Hardware ref**: `docs/MAPPER_MMC1_REFERENCE.md` §3 (Mode 3: fixed last bank at
  `$C000-$FFFF`, switchable 16KB at `$8000-$BFFF` — only one physical page is CPU-visible
  at `$8000` at a time, so code placed there must either never run while a different bank
  is selected, or the caller must guarantee the right bank first).
- **Suggested Fix**: Merge `fix/issue-388-mmc1-debug-bank-overlay` (commit `df924b1`) — it
  is already written, already reviewed by the prior audit pass, and was verified via a
  live `ca65`/`ld65` build spanning 2+ MMC1 banks (linker map showed `debug_init`/
  `debug_update`/`debug_test_apu` correctly relocated into `CODE`/`PRGFIXED`). No new code
  needed; this is a merge/release-process gap, not an open design question.

---

### MAP-2026-08-06-2: Capacity pre-flight still sizes only the raw exporter output, not the debug overlay / DPCM-stub content appended afterward — fix exists but is unmerged
- **Severity**: MEDIUM
- **Dimension**: 4 (PRG capacity / overrun detection)
- **Location**: `nes/project_builder.py:132-140` (`check_mapper_capacity(music_asm_path, self.mapper)` still runs against the *source* file, before the debug-overlay/`fetch_sequence_byte`/DPCM-stub appends at lines 142-211), `main.py:490-491` / `main.py:1069-1070` (same ordering, unchanged)
- **Status**: Existing: #389 — **CLOSED on GitHub but the fix is not in the audited tree.** Closing comment names commit `6e10aec` on branch `fix/issues-389-390-mapper-capacity-preflight`; `git merge-base --is-ancestor 6e10aec HEAD`/`master` both report false. The comment directly above the `check_mapper_capacity` call in the audited file (`nes/project_builder.py:138`, "Runs on the source music.asm (before any transforms below), matching what the CLI check sizes") is the same pre-fix rationale quoted verbatim in the original finding, confirming the ordering was never changed here.
- **Description**: Unchanged from the original finding. Both call sites of
  `check_mapper_capacity` size `music.asm` exactly as produced by `CA65Exporter`/
  `DpcmPacker`, strictly before `prepare_project` appends the `--debug` overlay, the
  bytecode-only `fetch_sequence_byte` routine, or the DPCM stub-table fallback. For a song
  already close to a mapper's declared budget, that additional content (measured
  previously at ~800 bytes for the debug overlay alone) is invisible to the pre-flight's
  clean error message; an overflow it causes surfaces only as a raw `ld65` region-overflow,
  or — combined with MAP-2026-08-06-1 above — doesn't even fail cleanly on MMC1.
- **Evidence**: `nes/project_builder.py:140` still reads `check_mapper_capacity(music_asm_path, self.mapper)` where `music_asm_path` is the pre-transform path argument, not the post-append `music_content` string; the debug-overlay append happens at line 148, seven lines later, with no re-check afterward.
- **Impact**: Same as originally reported — defense-in-depth gap for near-boundary songs;
  `ld65` remains the exact backstop.
- **Related**: #389 (original report, closed but unmerged); MAP-2026-08-06-1 (interacts —
  a capacity overflow caused by the debug overlay on MMC1 wouldn't necessarily fail
  cleanly at all, per that finding).
- **Hardware ref**: `docs/MAPPER_MMC3_REFERENCE.md` §2 (the `PRG_FIX` budget the reserve
  approximates); n/a for NROM/MMC1's flat reserve.
- **Suggested Fix**: Merge `fix/issues-389-390-mapper-capacity-preflight` (commit
  `6e10aec`), which moves the capacity check to run against the final written
  `music.asm` after every `prepare_project` transform is folded in.

---

### MAP-2026-08-06-3: `estimate_segment_sizes` still undercounts `.byte "string", ...` lines by counting comma-separated tokens instead of string length — fix exists but is unmerged
- **Severity**: LOW
- **Dimension**: 4 (PRG capacity / overrun detection — the heuristic's documented weak spot)
- **Location**: `mappers/capacity.py:58-59` (`n = len([t for t in line[5:].split(',') if t.strip()])`)
- **Status**: Existing: #390 — **CLOSED on GitHub but the fix is not in the audited tree.** Same `6e10aec` commit as #389, on the same unmerged branch. The line quoted in the original finding is byte-for-byte identical in the audited checkout.
- **Description**: Unchanged from the original finding: a `.byte` line's comma-split token
  count is correct for numeric literals but treats a quoted string as exactly one token
  regardless of its real character length, undercounting any line like
  `.byte "MIDI2NES DEBUG v1.0", $00` by its string length minus one. Latent today per
  MAP-2026-08-06-2 above (the debug overlay, where this would matter most, isn't sized by
  the pre-flight at all yet) but would compound once that finding is fixed without this one.
- **Evidence**: `mappers/capacity.py:58` matches the code snippet quoted in the original
  #390 report verbatim; no quote-aware branch exists anywhere in `estimate_segment_sizes`.
- **Impact**: Purely a heuristic-accuracy gap; `ld65` remains the exact backstop.
- **Related**: #390 (original report, closed but unmerged); MAP-2026-08-06-2 (fixing that
  finding without this one raises this one's real-world stakes, as the original report noted).
- **Hardware ref**: n/a (assembler-text parsing, not NES hardware behavior).
- **Suggested Fix**: Merge `fix/issues-389-390-mapper-capacity-preflight` (commit
  `6e10aec`), which makes the `.byte` counter quote-aware (counts real string length,
  treats commas inside a quoted token as literal, not separators).

---

## Dimensions with no findings

| # | Dimension | Result |
|---|-----------|--------|
| 1 | iNES header ↔ nes.cfg | Re-verified from scratch: NROM/MMC1/MMC3 `MEMORY` region sums still equal each mapper's `prg_rom_size` (NROM 32KB, MMC1 7×16KB+16KB=128KB, MMC3 60×8KB+4×8KB=512KB); mapper-number nibbles `$00`/`$10`/`$40` correct against `docs/MAPPER_MMC3_REFERENCE.md` §2's Bank Select bitfield and MMC1's Control-register convention. MMC3's `PRG_A0`/`PRG_C0`/`PRG_80`/`PRG_FIX` physical-declaration order (banks 60/61/62/63) still correctly puts `PRG_80` at bank 62 and `PRG_FIX` at bank 63, matching PRG mode 1's hardwired windows (`docs/MAPPER_MMC3_REFERENCE.md` §3). |
| 2 | Reset/NMI/IRQ vectors + 60 Hz NMI | `nmi`/`reset`/`irq` all defined in `nes/project_builder.py:342-391`; `reset` enables NMI (`lda #$80 / sta $2000`, line 359-360) after `jsr init_music` (line 356); `nmi` unconditionally calls `jsr update_music` (line 375) before the (currently unsafe-on-MMC1, see MAP-2026-08-06-1) `{debug_update_call}` interpolation. `VECTORS` segment still correctly declared `start = $FFFA` on all three mappers. |
| 3 | APU init in boot path | Direct-export `init_music` (`exporter/exporter_ca65.py`) and bytecode `audio_init` (`nes/audio_engine.asm`) both still write `$4017`/`$4015` plus sweep-off before playback. Confirmed commit `24e51d2` (this branch) *added* a `$4011` (DMC DAC) zero to the direct-export reset path (#348) — a strict improvement, not a regression; no other commits touched this path since 2026-08-05. |
| 6 | MapperFactory auto-selection | `mappers/factory.py` unchanged since 2026-08-05: `direct_export_capacity()`/`auto_select(direct=True)` still rank MMC3 correctly for direct exports; the direct-export DPCM marker and bank-pack marker are still checked by `resolve_mapper()` in the documented order (bytecode → direct-DPCM → bank-pack); `NESProjectBuilder.prepare_project` still calls `check_mapper_capacity` itself independent of `main.py` (the *ordering* gap relative to debug-overlay content is MAP-2026-08-06-2, not a regression of this dimension). |
| 7 | Project builder writes buildable project | All 3 mappers still link (spot-checked NROM/MMC1/MMC3 `nes.cfg` segment sets against `main.asm`/`music.asm` segment usage — no orphaned or missing segments). MAP-2026-08-06-1 is a logical placement bug within a segment that exists on both sides, not a missing-segment/link-failure case — link still succeeds every time. |
| 8 | Compiler validation & CC65 surfacing | `compiler/cc65_wrapper.py`'s `check_toolchain`/`get_version` still resolve via `shutil.which()` first and guard each `subprocess.run` with `try/except (FileNotFoundError, subprocess.TimeoutExpired)`; `assemble()`/`link()` still raise `CompilationError` with `stderr` attached on nonzero return code; `compiler/compiler.py`'s broad `except Exception` still calls `traceback.print_exc()` only under `--verbose`. No commits touched either file since 2026-08-05. |
| 9 | ROM size check | `compiler/compiler.py:244-253` still checks the linked ROM's size against `mapper.prg_rom_size + INES_HEADER_SIZE` exactly when a mapper is passed, falling back to the flat `MIN_ROM_SIZE = 32768` floor only when `mapper is None` (unchanged, still a documented defense-in-depth gap for library callers that pass no mapper). |
| 10 | Default-mapper doc drift | `grep -niE 'always use mmc1|default.*mapper|mmc1' README.md CLAUDE.md docs/*.md` clean — no source or doc reasserts MMC1 as *the* default; `CLAUDE.md` and `README.md` consistently describe MMC3 as the pipeline default with MMC1/NROM selectable. |

Dimension 5 (bank-switching correctness) has one finding (MAP-2026-08-06-1, above) rather
than "no findings" for the same reason as the prior pass: MMC1's 5-write serial load
(re-checked against `docs/MAPPER_MMC1_REFERENCE.md` §1 — 5 writes to `$8000` for Control,
5 writes to `$E000` for the PRG bank register) and MMC3's R6/R7 selects (re-checked against
`docs/MAPPER_MMC3_REFERENCE.md` §2-3 — Mode 1 selected via `lda #$46/$47`, R6→`$C000-$DFFF`,
R7→`$A000-$BFFF`, matching the engine's DPCM/pattern-window usage) remain correct; the
finding is specifically about a *caller* (the debug overlay integration) not respecting
the bank-switching contract those primitives correctly implement — and the fix for that
caller-side bug is written but not merged.

---

## Process note (not a numbered finding)

Three issues from the immediately preceding audit pass (#388/#389/#390) are marked
**CLOSED** on GitHub with linked fix commits, but none of those commits have been merged
into `master` or into the branch this audit examined. This means an audit relying solely
on GitHub issue state (rather than re-reading the live code) would have under-reported
this pass by 3 findings. Recommend merging the three named branches
(`fix/issue-388-mmc1-debug-bank-overlay`, `fix/issues-389-390-mapper-capacity-preflight`)
before the next mappers audit pass, and treating "issue closed" as provisional until the
linked commit is confirmed reachable from the branch being audited.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-08-06.md
```
