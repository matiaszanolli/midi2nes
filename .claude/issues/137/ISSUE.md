# TD-08: Stale DPCM .incbin TODO in exporter_ca65 — work is done by DpcmPacker elsewhere

**Severity:** LOW · **Domain:** documentation · **Source:** AUDIT_TECH_DEBT_2026-06-29.md

## Description
The macro-bytecode export (the **default** patterns path) emits a `.segment "DPCM"` block whose only content is a TODO comment claiming `.incbin` statements are not yet inserted. In practice the real DPCM `.incbin` lines and lookup tables are produced by `dpcm_sampler/dpcm_packer.py:88` and appended to `music.asm` by the pipeline (`main.py:531-565`). The TODO is therefore stale: it describes work that is done in another module. This is the only TODO/FIXME/HACK/XXX in non-test source.

**Location:** `exporter/exporter_ca65.py:858`

## Evidence
`grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py' .` → single hit at `exporter_ca65.py:858`. DPCM `.incbin` actually emitted at `dpcm_packer.py:81-88`; packed into the project at `main.py:255` and `main.py:531`.

## Impact
Misleading — implies a missing feature on the default path when DPCM packing exists. Not a stub on the live path (the work happens). The empty `.segment "DPCM"` here vs the packer's `DPCM_NN` segments is a separable correctness concern, not in scope.

## Suggested Fix
Replace the TODO with a comment stating DPCM `.incbin`/tables are appended by `DpcmPacker` (with a pointer), or remove the empty segment if the packer owns it entirely.

## Related
TD-12; mapper/segment findings M-1/M-6 (#22) in `AUDIT_MAPPERS_2026-06-28.md`.

## Completeness Checks
- [ ] **DOC**: The stale marker is corrected to reflect that `DpcmPacker` owns the `.incbin`/tables
- [ ] **SIBLING**: No other stale "not yet inserted" markers in the exporter
