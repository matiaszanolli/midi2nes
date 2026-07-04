# #176 — PL-03: The fallback's "the ROM is INCOMPLETE" warning is false

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
When the sequential fallback samples events down to `DETECTOR_MAX_EVENTS` (1000), the
pipeline prints and re-prints at success: "the ROM is INCOMPLETE. Re-run with
--no-patterns for full fidelity." But sampled `events` feed only pattern detection, whose
output affects the ROM solely via `patterns` truthiness (serializer selection) — every
emitted byte derives from the full `frames` dict (confirmed in the macro path which
iterates `range(max_frame + 1)` over `frames`). The ROM contains the whole song either way.
The message is also inconsistent with the parallel path, which samples to 15000, printing
only an inline "lossy" note and no INCOMPLETE banner — two sampling events of the same kind
get opposite messaging.

## Location
`main.py:522-530` (`pattern_loss_warning` text), `main.py:661-662` ("INCOMPLETE OUTPUT"
success-banner line); ground truth `exporter/exporter_ca65.py:862-874`.

## Evidence
`main.py:525-528` (warning text) vs `exporter/exporter_ca65.py:873-874`
(`if not patterns: return self.export_direct_frames(...)` — the only read of pattern data)
and `:964-965` (frame loop over `frames`, not `events`).

## Impact
Users with large files hitting the fallback are told their ROM is broken when it is not,
and are directed to `--no-patterns` — which switches to the direct-frame serializer,
typically producing a much larger ROM (and closer to the MMC3 capacity gate) for zero
fidelity gain. Only the compression metrics are affected by sampling.

## Related
Closed #10 (introduced the warning), #100 (fixed its numbers), #4 (references are analysis-only — the fact that makes the claim false); PAT-02 (patterns audit, same defect, deduped here as canonical).

## Suggested Fix
Reword both messages to what is true: "pattern analysis was sampled (N->M events);
compression stats are approximate; ROM content is unaffected." Drop the `--no-patterns`
advice, and align the parallel path's sampling message with the fallback's.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **TESTS**: A regression test pins this specific fix

---

# #177 — PL-04: `validate_rom` silently passes when the diagnostics engine itself fails

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
The post-build gate wraps `from debug.rom_diagnostics import ROMDiagnostics` +
`diagnose_rom(...)` in `except Exception:` and returns True (ROM accepted), printing a
warning only if verbose. `diagnose_rom` handles unreadable ROMs internally
(`_create_error_result` -> "ERROR" -> fatal), so this outer except fires on genuine
infrastructure failures (import error in the `debug` package, an unexpected bug in
diagnostics) — exactly the cases where the boot-fatal vector/APU gate (#6) silently stops
existing. In a default (non-verbose) run there is zero indication that validation was
skipped.

## Location
`main.py:157-163`.

## Evidence
`main.py:157-163` — `except Exception as e: if verbose: print(...); return True`. The
docstring itself flags it: "treated as non-blocking, matching prior behavior."

## Impact
Defense-in-depth gap on the one gate that keeps unbootable ROMs (bad $FFFA-$FFFF vectors,
missing APU init) from shipping as "✅ SUCCESS". Requires a second failure (broken
diagnostics) to bite, hence MEDIUM rather than HIGH, but the swallow is fully silent by
default.

## Related
Closed #6 (the gate this bypasses), #15 (gate shared with `compile`); open #130 (TD-02, duplicate validators).

## Suggested Fix
Always print the "ROM validation could not run: {e} — ROM NOT validated" warning (not just
under verbose); consider exiting nonzero unless `--skip-validation` was passed, since the
user explicitly has that escape hatch.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix

---

# #178 — PL-05: A validation-failed (unbootable) ROM is left at the output path

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-01.md

## Description
`compile_rom` copies the linked ROM to the user's output path, then `validate_rom` runs.
If validation reports a boot-fatal defect, both callers `sys.exit(1)` — but the freshly
written unbootable `.nes` stays at the output path. On the default path the `finally`
restore repairs this only if the output existed before the run (backup taken at
`main.py:432-437`); a first-time build leaves the bad ROM behind. `run_compile` never
creates a backup at all, so it both (a) overwrites a pre-existing good ROM with no restore
path (a parity break with the default path's backup contract) and (b) always leaves the
failed ROM on disk.

## Location
`main.py:191-213` (`run_compile`: no backup, no cleanup on validation failure),
`main.py:679-683` (`finally` restore is a no-op when `backup_path is None`),
`compiler/compiler.py:144` (ROM copied to the output path before validation runs).

## Evidence
`run_compile` body (`main.py:197-213`) contains no `backup`/`unlink` logic;
`_restore_backup` (`main.py:140-145`) is a no-op for `backup_path=None`.

## Impact
The cardinal fail-fast rule ("no broken `.nes` left where the user expects a good one") is
violated in the artifact sense: the failure is loudly reported with a nonzero exit, but a
known-unbootable ROM persists at the destination — a later `ls`-and-flash, or any workflow
ignoring exit codes, ships it. Workaround exists (heed the error).

## Related
Closed #26 (restore unification), #15 (`compile` subcommand); PL-04.

## Suggested Fix
On validation failure with no backup, rename the bad ROM to `<name>.nes.failed` (or delete
it) before exiting; give `run_compile` the same backup-create/restore/cleanup contract as
the default path (factor the default path's backup block into a helper both use).

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
