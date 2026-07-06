# Audit: Mappers / Project Builder / Compiler — 2026-07-06

Subsystem audited: `mappers/` (base, factory, nrom, mmc1, mmc3), `nes/project_builder.py`,
`compiler/compiler.py`, `compiler/cc65_wrapper.py`, the exporter seam
(`exporter/exporter_ca65.py`, `dpcm_sampler/dpcm_packer.py`), and the `main.py` `--mapper`
resolution / capacity-preflight call sites. All 10 SKILL.md dimensions covered, no
`--focus` restriction.

This is a re-audit following the mapper-relevant commits that landed after the prior
`AUDIT_MAPPERS_2026-07-05.md` pass:
- `7af88a4` (#281/#282) — gate direct-export DPCM to MMC3, reject on MMC1/NROM
- `833174b`/`8bbfe9a` (#283/#284/#285) — guard direct-export bank-pack mapper mismatch, fix MMC1 doc
- `757ff86` (#291) — place CODE_8000 tables at the MMC3 mode-1 fixed `$8000` bank

These four commits correspond exactly to the four findings of the 07-05 pass
(MAP-2026-07-05B-1..B-4), which are **all now fixed** — verified this pass, not re-reported.

**Dedup basis:** `/tmp/audit/issues.json` (29 open issues, prefetched) searched for
`mapper`, `compile`, `auto`, `nrom`, `mmc1`, `mmc3`, `bank`, `capacity`, `align`; and all
prior `docs/audits/AUDIT_MAPPERS_*.md`. The only open mapper/compile issue is **#269**
(PL-08, below); no prior report covers this pass's two NEW findings.

## ⚠️ Prompt-injection note
No injected instructions were encountered in any tool output during this audit. All
findings come from reading source files, `git log`, and a direct `resolve_mapper` repro.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 1 |
| **Total (NEW)** | **2** |

Plus one pre-existing open issue (**#269**) confirmed, not re-filed.

**One-line verdict:** The **default** pipeline (MMC3, patterns-on) produces a bootable ROM —
vectors at `$FFFA`–`$FFFF` point at real code, `reset` enables NMI (`sta $2000`) and calls
`init_music`, `nmi` calls `update_music`, the APU is initialized, the iNES header agrees with
`nes.cfg` for all three mappers, the #291 physical-bank ordering (`PRG_80`=bank 62,
`PRG_FIX`=bank 63) is correct, and the capacity pre-flight is wired before `ld65`. No
CRITICAL/HIGH regressions. The two NEW findings are a step-by-step-CLI UX/defense gap
(MEDIUM) and a bounded, packer-guarded pre-flight undercount (LOW).

**Highest-leverage fix:** MAP-2026-07-06-1 (MEDIUM) — the `prepare` success message tells the
user to run `main.py compile <dir> <out>` with **no** `--mapper`, but `compile` defaults to
`mmc3` and cannot recover a marker-less NROM project from its `music.asm`, so a NROM-prepared
project fails compile with a misleading "does not match MMC3 size" error.

---

## Findings (most severe first)

### MAP-2026-07-06-1: Step-by-step `compile` defaults to MMC3 and cannot recover a NROM-prepared project — rejects a valid NROM ROM with a misleading MMC3 size-mismatch; the `prepare` message tells users to run it that way
- **Severity**: MEDIUM
- **Dimension**: 7 (project builder writes a consistent, buildable project) / 9 (ROM size check)
- **Location**: `main.py:496-497` (`run_prepare` prints `python main.py compile {output} <output.nes>` with no `--mapper`); `main.py:1165` (`compile` `--mapper` `choices=['nrom','mmc1','mmc3'], default='mmc3'`); `main.py:218-260` (`resolve_mapper`); `main.py:438` (`run_compile` re-resolves the mapper from the project's own `music.asm`); size check at `compiler/compiler.py:199-209`.
- **Status**: NEW (related to Existing #269)
- **Description**: The supported step-by-step flow is `… → export → prepare → compile`, and each subcommand takes `--mapper` independently. `resolve_mapper` recovers the intended mapper from `music.asm` for two cases: the MMC3 macro-bytecode marker (`_requires_mmc3_bytecode_engine`) and the MMC1 direct-export bank-pack marker (`_direct_export_packed_mapper_name`, emitted only when `mapper.direct_export_bank_size() is not None`, i.e. MMC1 — `exporter/exporter_ca65.py:206-207`). A **NROM** direct export emits neither marker (`direct_export_bank_size()` is `None`), so `resolve_mapper('mmc3', nrom_music_asm)` returns MMC3. `compile` then links the project with its own NROM `nes.cfg` (a valid 32 KB+16 ROM) but the exact-size check compares the 32,784-byte result against MMC3's expected 524,304 and raises `CompilationError: ... does not match the expected MMC3 size`. Because `run_prepare`'s printed guidance omits `--mapper`, a user who did `prepare --mapper nrom` and follows that guidance hits this. (For MMC1 the outcome is a *clear* error — `resolve_mapper` sees the bank-pack marker and raises "…bank-packed for MMC1 … run prepare/compile with --mapper mmc1" — but it still requires the flag the printed instruction never mentions. Only NROM produces the *misleading* MMC3 message.)
- **Evidence**:
  ```
  $ python3 -c "from main import resolve_mapper; import tempfile,os; \
    p=tempfile.mktemp(); open(p,'w').write('.segment \"RODATA\"\n .byte 0,1\n'); \
    print(resolve_mapper('mmc3', p).name)"
  MMC3            # NROM project, default compile -> MMC3; size check expects 524304, ld65 built 32784
  ```
  `resolve_mapper` has no NROM branch (no marker for a flat NROM export); `run_prepare` output at `main.py:496-497` contains no `--mapper`. The `build.sh` path is unaffected (it uses the project's own `nes.cfg`); only the `compile` subcommand mis-sizes.
- **Impact**: `main.py compile` is effectively unusable for a NROM-prepared project unless the user knows to add `--mapper nrom` (which the tool never tells them). The valid NROM ROM is rejected and moved aside as `<name>.nes.failed` by the backup/restore contract. Not silent and no broken ROM ships — but it rejects a correct build with a wrong-mapper diagnostic and contradicts the tool's own printed instruction. Narrow blast radius (only the split `prepare`/`compile` flow with a non-default mapper; the single-command full pipeline threads one mapper consistently and is unaffected).
- **Related**: **#269 / PL-08** (OPEN) — `compile --mapper` has no `auto`, so a `prepare --mapper auto` project also has no matching `compile` invocation; same root (compile can't recover the prepared mapper). MAP-2026-07-05B-3 (the MMC1 direction, fixed by #283/#285).
- **Hardware ref**: n/a (CLI/tooling, not a register claim).
- **Suggested Fix**: Either (a) have `run_prepare` print the resolved `--mapper` in its `compile` instruction (`… compile {output} <out.nes> --mapper {mapper.name.lower()}`), and add a NROM-recovery path/marker so `resolve_mapper` doesn't default a marker-less project to MMC3; or (b) have `compile` read the mapper from the project's `nes.cfg` (the authoritative record of what `prepare` built) instead of re-guessing from `music.asm`. Address alongside #269 (add `auto` to `compile --mapper`, resolving against the project's `nes.cfg`).

---

### MAP-2026-07-06-2: Capacity pre-flight undercounts DPCM `.align 64` padding (bounded, packer-guarded, ld65-backstopped)
- **Severity**: LOW
- **Dimension**: 4 (PRG capacity / overrun detection)
- **Location**: `main.py:148-166` (`estimate_segment_sizes` counts `.incbin` bytes / `.byte`/`.word` element counts, but not `.align` padding); `dpcm_sampler/dpcm_packer.py:98-108` (`generate_assembly` emits `.align 64` before each sample's `.incbin`); consumed by `MMC3Mapper.validate_segment_sizes` (`mappers/mmc3.py:218-246`, per-bank `DPCM_NN`+`BANK_NN` sum).
- **Status**: NEW
- **Description**: `estimate_segment_sizes` scores a `.incbin "…", 0, N` as `N` (or the file size) and ignores the `.align 64` directive that precedes each packed DPCM sample, so a `DPCM_NN` segment's estimated size is short of its real ROM footprint by up to 63 bytes per sample. Per SKILL Dimension 4, a heuristic that can *under*-count and let an oversized bank pass the pre-flight into a raw `ld65` region overflow is a concern. In practice, however, `DpcmPacker` itself packs by `aligned_size = ceil(size/64)*64` and enforces `bank_total ≤ BANK_SIZE (8192)` at pack time (`dpcm_packer.py:38,60-64`), so the *normal* pipeline never emits a `DPCM_NN` bank whose real (aligned) size exceeds 8 KB — the pre-flight undercount cannot be reached through the packer. It matters only for a hand-edited `music.asm` whose per-bank aligned total sits in the ≤63-byte-per-sample window between the estimate and 8192, and even then `ld65` errors cleanly on the region overflow. So this is a purely cosmetic accuracy gap in a defense-in-depth backstop, not a real overrun path.
- **Evidence**: `estimate_segment_sizes` (`main.py:153-164`) has no `.align` branch; `dpcm_packer.py:100` unconditionally emits `.align 64` inside each `DPCM_NN` segment, while `dpcm_packer.py:60-64` already caps each bank's *aligned* total at `BANK_SIZE`. Read-only confirmation; no repro needed (the packer prevents the trigger).
- **Impact**: A marginally-oversized *hand-edited* DPCM bank could print "✓ fits" from the pre-flight and then fail at `ld65` with a region-overflow instead of a clean pre-flight message. No effect on packer-produced ROMs. Cosmetic.
- **Related**: MMC3/MMC1 `validate_segment_sizes` per-bank checks (correct otherwise); Dimension 4's "misleading pre-flight message" guidance.
- **Hardware ref**: n/a.
- **Suggested Fix**: In `estimate_segment_sizes`, round each `.incbin` contribution up to the next `.align` boundary when a preceding `.align N` is active (or add the alignment slack once per aligned block), so the pre-flight's `DPCM_NN` totals match the packer's `aligned_size`. Low priority given the packer already guarantees the invariant.

---

## Previously identified, now fixed (dedup per `_audit-common.md`)

All four findings of `AUDIT_MAPPERS_2026-07-05.md` are **confirmed fixed** this pass:

- **MAP-2026-07-05B-1 (was CRITICAL)** — direct-export `play_dpcm` hardcoded MMC3 `$8000`/`$8001`
  bank writes regardless of mapper. Fixed by `enforce_direct_export_dpcm_mapper` (`main.py:263-296`,
  #281): a non-empty `dpcm` channel forces MMC3 under `--mapper auto` and raises a clean
  `ValueError` for explicit `mmc1`/`nrom`. Wired into `run_export` (`main.py:549`) and the
  full pipeline (`main.py:907`). No MMC1/NROM direct-export DPCM ROM can be built anymore.
- **MAP-2026-07-05B-2 (was HIGH)** — MMC1/NROM `nes.cfg` had no `DPCM_NN` region, so a packed
  sample failed to link. Same fix (#282): the DPCM channel now forces MMC3, whose `nes.cfg`
  defines the `DPCM_NN` regions.
- **MAP-2026-07-05B-3 (was MEDIUM)** — no guard on an `export`-vs-`prepare` `--mapper` mismatch
  for direct-export bank-packing. Fixed by `_direct_export_packed_mapper_name` +
  `resolve_mapper`'s `packed_for` branch (`main.py:192-260`, #283/#285): a MMC1-bank-packed
  `music.asm` is honored under `auto` and rejected with a clear message on an explicit mismatch.
  (The NROM sub-case is the residual MAP-2026-07-06-1 above.)
- **MAP-2026-07-05B-4 (was LOW)** — `docs/MAPPER_MMC1_REFERENCE.md` §4 described an unimplemented
  Mode-2 DPCM design. Reconciled by #284/#286/#287 (`git log`: `0225e35`, `833174b`).

Also re-verified unchanged/correct this pass:
- **#291 (MMC3 CODE_8000)** — `generate_linker_config` declares the last four banks in physical
  order `PRG_A0`,`PRG_C0`,`PRG_80`,`PRG_FIX` (`mappers/mmc3.py:75-79`), so `PRG_80` lands on
  physical bank 62 (the mode-1 fixed `$8000` window) and `PRG_FIX`+`VECTORS` on bank 63. The
  bytecode exporter emits the instrument/macro tables into `CODE_8000` (`exporter/exporter_ca65.py:993`).
- **#28 (exact ROM size)** / **#214 (post-process on `compile()`)** / **#32 (traceback under `--verbose`)** —
  all hold (`compiler/compiler.py:191-214,252-260`).
- **Dimensions 2/3** — `reset`/`nmi`/`irq` defined, `reset` does `sta $2000` + `jsr init_music`,
  `nmi` does `jsr update_music`, `VECTORS` = `nmi,reset,irq` at `$FFFA/$FFFC/$FFFE`
  (`nes/project_builder.py:424-473`). No regression.

## Still-open, not re-filed

- **#269 / PL-08** (OPEN) — `compile --mapper` has no `auto`; a `prepare --mapper auto` project
  has no matching `compile` invocation. Confirmed still present (`main.py:1165`,
  `choices=['nrom','mmc1','mmc3']`). See MAP-2026-07-06-1 (same root cause).

## Dimension coverage map

| Dim | Area | Result |
|-----|------|--------|
| 1 | iNES header ↔ nes.cfg | Verified. NROM `$02`/32KB, MMC1 `$08`/128KB (7×16KB swap + 16KB fixed), MMC3 `32`/512KB. MMC3 MEMORY regions sum to exactly 524,288 (60×0x2000 + 3×0x2000 + 0x1FFA + 6). Mapper nibbles `$00`/`$10`/`$40` = 0/1/4. No mismatch. |
| 2 | Vectors + 60Hz NMI | `nmi`/`reset`/`irq` all defined; `reset` enables NMI + `jsr init_music`; `nmi` `jsr update_music`; VECTORS at `$FFFA`. No finding. |
| 3 | APU init | Direct + bytecode paths init `$4015`/`$4017` before playback; DPCM force-MMC3 path unchanged. No finding. |
| 4 | PRG capacity/overrun | Pre-flight wired before `ld65` on both `prepare` and full-pipeline paths; MMC3/MMC1 per-bank checks correct. **MAP-2026-07-06-2 (LOW)**: `.align` padding undercounted (packer-guarded). |
| 5 | Bank switching | MMC1 5-write serial load and MMC3 R6/R7 selects match the reference docs; #291 physical-bank order correct. No finding. |
| 6 | MapperFactory auto-select | `auto_select` reached via `resolve_mapper`; bytecode/bank-pack/DPCM force+reject guards all present and raise cleanly. No finding. |
| 7 | Project builder buildability | MMC3/NROM/MMC1 all assemble+link; segments consistent. **MAP-2026-07-06-1 (MEDIUM)**: `compile` can't recover a NROM-prepared mapper; misleading size-mismatch. |
| 8 | Compiler / CC65 surfacing | `assemble`/`link` raise on nonzero return with stderr; `--verbose` traceback; post-process runs from `compile()`. No finding. |
| 9 | ROM size check | Exact `mapper.prg_rom_size + 16` when a mapper is passed; both CLI callers pass one. (The mis-resolved mapper in MAP-2026-07-06-1 is a Dim-7 recovery gap, not a Dim-9 logic bug.) |
| 10 | Default-mapper doc drift | `CLAUDE.md`/`README.md` consistently describe MMC3 default; MMC1 §4 doc reconciled (#284). No finding. |

---

Next step:
```
/audit-publish docs/audits/AUDIT_MAPPERS_2026-07-06.md
```
