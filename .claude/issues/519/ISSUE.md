**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-24.md

## Description
`export_tables_with_patterns`/`export_direct_frames` correctly do a full atomic replace of `music.asm` via `atomic_write_text` (`core/io_utils.py:13-39`, `mkstemp` + `os.replace`) before DPCM packing ever runs. But the DPCM trailer append itself, in `pack_dpcm_into_asm` (shared by `run_export` and `export_frames_and_resolve_mapper`), is a single direct, non-atomic write:

```python
# main.py:212-213
with open(asm_path, 'a') as f:
    f.write("\n\n" + packer.generate_assembly())
```

If interrupted partway (disk full, killed process), the already-atomically-replaced `music.asm` is left with a truncated DPCM assembly trailer — caught by the enclosing broad `except Exception`, but the resulting message, `"DPCM packing failed ({e}) — the exported ASM has NO drums even though dpcm_index.json may reference some"`, describes a clean "no drums" state, not the actual corrupted-file state.

## Impact
Narrow trigger (OS-level write failure/process kill mid-append only), and self-detecting — a corrupted trailer produces a loud `ca65` assembly error at the next `prepare`/`compile` step rather than a silently broken ROM, so this cannot by itself reach a bootable-but-wrong ROM. Blast radius is a confusing error message.

## Related
Distinct from the already-fixed accumulation bug (#380/TD-28, re-verified still fine) — this is about the append call's atomicity, not about running export twice.

## Suggested Fix
Build the appended trailer into the same `atomic_write_text` call (append `packer.generate_assembly()` to the in-memory content before the one atomic write), or write the DPCM trailer to its own temp file and `os.replace` the concatenation. At minimum, reword the except-path message to not claim "no drums" when a partial write may have occurred.

## Completeness Checks
- [ ] **SIBLING**: The earlier `music.asm` write (via `atomic_write_text`) is already atomic — the fix should bring the DPCM append to the same standard rather than leaving an inconsistent mix
- [ ] **TESTS**: A regression test could simulate a mid-append failure and assert the error message doesn't claim "no drums" when a partial write occurred
