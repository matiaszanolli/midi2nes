# #297 — MAP-2026-07-06-1: compile defaults to MMC3, cannot recover a NROM-prepared project

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-06.md · **Status:** NEW (related to #269)

## Description
The step-by-step flow is `… → export → prepare → compile`, and each subcommand takes `--mapper` independently. `resolve_mapper` recovers the intended mapper from `music.asm` for two cases: the MMC3 macro-bytecode marker (`_requires_mmc3_bytecode_engine`) and the MMC1 direct-export bank-pack marker (`_direct_export_packed_mapper_name`, emitted only when `mapper.direct_export_bank_size() is not None`, i.e. MMC1 — `exporter/exporter_ca65.py:206-207`). A **NROM** direct export emits neither marker (`direct_export_bank_size()` is `None`), so `resolve_mapper('mmc3', nrom_music_asm)` returns MMC3.

`compile` then links the project with its own NROM `nes.cfg` (a valid 32 KB+16 ROM) but the exact-size check (`compiler/compiler.py:199-209`) compares the 32,784-byte result against MMC3's expected 524,304 and raises `CompilationError: … does not match the expected MMC3 size`. Because `run_prepare`'s printed guidance (`main.py:496-497`) omits `--mapper`, a user who did `prepare --mapper nrom` and follows that guidance hits this. (`compile --mapper` defaults to `mmc3` at `main.py:1165` and offers no `auto`.)

## Evidence
```
$ python3 -c "from main import resolve_mapper; import tempfile; \
  p=tempfile.mktemp(); open(p,'w').write('.segment \"RODATA\"\n .byte 0,1\n'); \
  print(resolve_mapper('mmc3', p).name)"
MMC3            # NROM project, default compile -> MMC3; size check expects 524304, ld65 built 32784
```
`resolve_mapper` has no NROM branch (no marker for a flat NROM export). The `build.sh` path is unaffected (it uses the project's own `nes.cfg`); only the `compile` subcommand mis-sizes. For MMC1 the outcome is a *clear* error (bank-pack marker → "run … with --mapper mmc1"); only NROM produces the *misleading* MMC3 message.

## Impact
`main.py compile` is effectively unusable for a NROM-prepared project unless the user knows to add `--mapper nrom` (which the tool never tells them). The valid NROM ROM is rejected and moved aside as `<name>.nes.failed`. Not silent and no broken ROM ships — but it rejects a correct build with a wrong-mapper diagnostic and contradicts the tool's own printed instruction. Narrow blast radius (only the split `prepare`/`compile` flow with a non-default mapper).

## Suggested Fix
Either (a) have `run_prepare` print the resolved `--mapper` in its `compile` instruction (`… compile {output} <out.nes> --mapper {mapper.name.lower()}`) and add a NROM-recovery marker so `resolve_mapper` doesn't default a marker-less project to MMC3; or (b) have `compile` read the mapper from the project's `nes.cfg` (the authoritative record of what `prepare` built) instead of re-guessing from `music.asm`. Best addressed alongside #269 (add `auto` to `compile --mapper`, resolving against the project's `nes.cfg`).

## Completeness Checks
- [ ] **CONTRACT**: `prepare`'s printed `compile` instruction and `compile`'s mapper resolution agree on the prepared mapper
- [ ] **CC65**: a NROM-prepared project compiles + passes the exact-size check without a manual `--mapper`
- [ ] **SIBLING**: NROM, MMC1, and MMC3 prepared projects all round-trip through `compile` (and `auto`, per #269)
- [ ] **TESTS**: a test drives `prepare --mapper nrom` → `compile` and asserts a valid ROM
