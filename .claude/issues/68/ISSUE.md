# D-05: One oversized .dmc aborts the entire DPCM pack via broad except Exception

Issue: #68 — https://github.com/matiaszanolli/midi2nes/issues/68
Labels: bug, high, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

**Severity:** HIGH · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`DpcmPacker.add_sample` raises `ValueError` when a file exceeds 4081 bytes. Both packer call sites wrap the *entire* loop + `generate_assembly` in a single `try / except Exception` that just prints a warning and continues with **no DPCM assembly appended at all**. So a single oversized sample anywhere in the index discards every sample's tables for the whole song, not just the offending one.

## Location
- `dpcm_sampler/dpcm_packer.py:23-24`
- `main.py:532-569` (and `253-269`)

## Evidence
23 of the shipped `dmc/*.dmc` files exceed 4081 bytes (confirmed: `find dmc -name '*.dmc' -size +4081c` → 23 files; largest 69347). `main.py:568-569` `except Exception as e: print(... Failed to pack DPCM samples ...)`. The `ValueError` from `add_sample:24` escapes the per-sample loop and skips `generate_assembly`/the append.

## Impact
Once D-01's path bug is fixed (files resolve), the first index entry that points at a >4081-byte `.dmc` aborts packing → the `.import dpcm_*_table` in `music.asm` resolves only to the project-builder stub (`project_builder.py:449-456`) → all DPCM silent, reported as a warning, not an error.

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §2/§4 — max sample length is `(L*16)+1` with `L<=255`, i.e. 4081 bytes; longer samples cannot be addressed.

## Related
D-01 (masks this today).

## Suggested Fix
Catch `ValueError` per-sample (skip + warn for that sample only), or pre-truncate/down-sample oversized `.dmc` files. Keep the rest of the catalog packing.

## Completeness Checks
- [ ] **SIBLING**: Same per-sample guard applied at both packer call sites (main.py:253-269 and 532-569)
- [ ] **TESTS**: A regression test pins this specific fix (oversized sample → others still pack)
