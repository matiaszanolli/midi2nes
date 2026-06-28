---
description: "Audit accumulated tech debt — duplication, dead code, stale docs, stubs, magic numbers"
argument-hint: "[--focus <dims>] [--path <dir>]"
---

# Tech-Debt Audit

Find maintainability debt across the Python codebase — the slow-accumulating kind that
no single feature audit owns. Not a correctness audit (that's the subsystem skills); this
is about code that *works* but costs more to change than it should.

Shared protocol: `.claude/commands/_audit-common.md` (layout, dedup, finding format).
Severity: `.claude/commands/_audit-severity.md` — tech-debt findings are usually LOW,
escalating to MEDIUM when the debt actively hides bugs (a swallowed exception, a stub on a
live path) or contradicts a hardware doc.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 2,3`). Default: all.
- `--path <dir>` — restrict to a subtree (e.g. `--path exporter`). Default: whole repo.

## Extra Per-Finding Field
- **Dimension**: one of the 8 below.

## Dimensions

### Dimension 1: Logic Duplication
Repeated logic that should be shared (the user's standing rule: improve existing code, never
duplicate). Hot spots: the four exporters (`exporter/`) re-implementing register/byte
serialization; per-channel handling copy-pasted across `nes/`; the two parsers
(`tracker/parser.py` vs `tracker/parser_fast.py`) drifting; the two pattern detectors
(`tracker/pattern_detector.py` vs `tracker/pattern_detector_parallel.py`). `grep` for
near-identical blocks; report the canonical home.

### Dimension 2: Dead Code & Cruft
Unused functions/imports/modules, unreachable branches, root-level scratch files
(`implementation_examples.py`, `show_greeting.py`, `*.s`/`*.nes`/`*.log` artifacts checked
into the tree). Confirm no caller via `grep -rn` before flagging. Distinguish "dead" from
"only called by tests".

### Dimension 3: Stale Documentation & Comments
A `docs/*.md`, docstring, or comment that contradicts the code. Highest-value targets:
`CLAUDE.md` (it already notes the MMC1→MMC3 prepare drift — check for more), `docs/ROADMAP.md`,
`docs/WORK_PLAN_1.0.0.md`, `README.md`, and the APU reference docs vs the actual
`nes/pitch_table.py` / `nes/envelope_processor.py` constants. Doc-rot that misstates
hardware behavior is MEDIUM.

### Dimension 4: Stale Markers (TODO / FIXME / HACK / XXX)
```bash
grep -rnE 'TODO|FIXME|HACK|XXX' --include='*.py' .
```
Report markers that describe real unfinished work (not just notes). Group by subsystem.

### Dimension 5: Stub & Placeholder Implementations
Functions that `return None`/`pass`/raise `NotImplementedError`, or hardcode a value where
real logic is implied — especially on a live pipeline path (a stubbed exporter branch, a
no-op validation). A stub on a path the default `main.py input.mid out.nes` run hits is MEDIUM.

### Dimension 6: Magic Numbers & Hardcoded Constants
Bare numeric literals that should be named or sourced from a doc — APU register addresses
($4000–$4017), 11-bit timer maxima, the 60Hz frame rate, NTSC 1.789773 MHz, the MMC1/MMC3
bank sizes, the `LARGE_FILE_THRESHOLD`/`MIN_ROM_SIZE` constants. Where a `docs/APU_*.md`
or `docs/MAPPER_*.md` defines the value, cite it. (LOW unless the magic number is wrong.)

### Dimension 7: Error-Handling Debt
Bare `except:` / `except Exception: pass`, broad catches that hide the real error,
`print`-and-continue where the pipeline should stop. Overlaps `/audit-safety` — here, focus
on the *pattern* prevalence and a shared remedy, not each individual site.

### Dimension 8: Module / Function Size & Structure
Oversized modules or functions doing too much. `main.py` (~900 lines with hand-rolled argv
parsing), `exporter/exporter_ca65.py`, and the arranger files are likely candidates. Report
the split that would help, not just the line count.

## Cross-Dimension Dedup
A single root cause can surface in several dimensions (a duplicated block that is also a
stub that also has a stale comment). Report it once, in the most actionable dimension, and
cross-reference.

## Output
Write to: **`docs/audits/AUDIT_TECH_DEBT_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — counts per dimension, the 3 highest-leverage cleanups.
2. **Findings** — base format + `Dimension`.

Then suggest:
```
/audit-publish docs/audits/AUDIT_TECH_DEBT_<TODAY>.md
```
