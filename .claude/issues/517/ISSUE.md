# PIPE-2026-08-24-1: ROM validation gate is static byte-pattern matching, not execution-based — cannot detect a structurally-valid-but-silent ROM

Labels: bug, critical, pipeline

**Severity:** CRITICAL · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-24.md

## Description
`validate_rom` (`main.py:552-595`) is the *only* runtime-behavior gate anywhere in the pipeline, shared by all three ROM-build entry points (`run_full_pipeline`, `run_compile`, `run_song_build` via `build_and_validate_rom`). It delegates entirely to `ROMDiagnostics.diagnose_rom`, whose two boot-fatal checks are both purely static:

- `_check_reset_vectors` (`debug/rom_diagnostics.py:224-243`) only range-checks the raw vector bytes (`0x8000-0xFFFF`) — it never confirms the RESET vector actually equals the assembled address of the `reset:` label, or that the target bank is reachable at power-on.
- `_check_apu_patterns` (`debug/rom_diagnostics.py:245-260`) does `rom_data.count(pattern)` — a byte-substring search over the **entire 512 KB ROM file**, not scoped to code reachable from the reset vector or to whichever bank is actually selected at runtime.

Combined, these answer "does this byte sequence appear somewhere in the file, and are the vector bytes numerically in range" — not "does this ROM, run from its RESET vector, actually initialize the APU and produce audio." A ROM can pass both checks (`HEALTHY`, nonzero `apu_pattern_count`, in-range vectors) while being **completely silent** at runtime — exactly what happened with a freshly-built MMC3 `canyon.mid` ROM this session (root cause: MAP-2026-08-24-1, a separate but related defect, now fixed).

## Evidence
```python
# debug/rom_diagnostics.py:240-241
valid = all(0x8000 <= vec <= 0xFFFF for vec in vectors.values())

# debug/rom_diagnostics.py:252-254
for pattern, description, priority in self.APU_PATTERNS:
    count = rom_data.count(pattern)   # substring search over the WHOLE ROM file
    total_count += count
```
```python
# main.py:573-576
if not rom_result.reset_vectors_valid:
    fatal_defects.append("invalid reset/NMI/IRQ vectors ($FFFA-$FFFF)")
if rom_result.apu_pattern_count == 0:
    fatal_defects.append("no APU initialization code found")
```

## Impact
Every ROM-build entry point reports a structurally-valid-but-silent ROM as bootable/healthy. Users get false confidence from `[ERROR]`-free, `✓ ROM Health: HEALTHY` output on a ROM that doesn't actually play. Not specific to DPCM/MMC3/canyon.mid — this is the entire compile/validate stage boundary, every mapper, every song.

## Related
This is very likely why open issue #3 ("Output seems silent") has stood unreproduced-by-tooling since 2025-10-13 — the pipeline's own safety net structurally cannot catch that class of failure. Recommend cross-linking to #3 rather than treating as unrelated. Historical precedent for this exact bug *class*: `mappers/mmc3.py:71-74`'s documented PRG-bank-ordering bug ("every note played garbage/silence... no crash") was never caught by `validate_rom` either.

## Suggested Fix
Two complementary directions: (1) make `_check_reset_vectors` compare the RESET vector against the assembled address of the `reset` label (via `ld65 -Ln`/`-m` map output) rather than just range-checking; (2) add a minimal execution-based APU smoke test — run N frames from RESET on a lightweight NES core and assert at least one APU channel's register is written a non-degenerate value. Note: `debug/rom_tester.py` is *not* an automated playback harness despite CLAUDE.md's "Full ROM build/playback test harness" description (doc-rot) — it only shells out to `open -a Nestopia <rom>` (macOS-only) and asks a human to check; it performs no verification and can't be wired into `validate_rom` as-is.

## Completeness Checks
- [ ] **SIBLING**: Same static-only gap applies to all three ROM-build entry points (`run_full_pipeline`, `run_compile`, `run_song_build`) — fix should cover all three, not just one
- [ ] **TESTS**: A regression test should assert `validate_rom` can catch a ROM whose reset vector doesn't match the assembled `reset` label, or whose APU pattern only exists in unreachable/dead bytes
- [ ] **DOC**: `CLAUDE.md`'s description of `debug/rom_tester.py` as a "Full ROM build/playback test harness" is inaccurate (doc-rot) and should be corrected alongside this fix

