---
description: "Fetch a GitHub issue, investigate, plan, implement, test, and commit the fix"
argument-hint: "<issue-number>"
---

# Fix Issue Pipeline

Shared context: `.claude/commands/_audit-common.md` (project layout, inter-stage
contracts, NES constraints) and `CLAUDE.md` (build/test commands, conventions).

## Phase 1: Fetch
```bash
gh issue view $ARGUMENTS --repo matiaszanolli/midi2nes --json title,body,labels,state
```
Save details to `.claude/issues/$ARGUMENTS/ISSUE.md` (immutable snapshot — no `State:` field;
GitHub stays authoritative).

## Phase 2: Classify Domain
The matched area becomes the narrow `pytest` target in Phase 6:

- **pipeline** → `main.py` dispatch + `tests/test_main.py`, `tests/test_e2e_pipeline.py`
- **nes-hardware** → `nes/emulator_core.py`, `nes/pitch_table.py`, `nes/envelope_processor.py` → `tests/test_audio_fixes.py`
- **patterns** → `tracker/pattern_detector_parallel.py`, `tracker/pattern_detector.py` → `tests/test_patterns.py`, `tests/test_enhanced_loop_patterns.py`
- **exporters** → `exporter/` → `tests/test_ca65_export.py`, `tests/test_exporter_integration.py`, `tests/test_compression*.py`
- **dpcm** → `dpcm_sampler/` → `tests/test_dpcm_*.py`, `tests/test_drum_*.py`, `tests/test_enhanced_drum_mapper.py`
- **arranger** → `arranger/` → `tests/test_arpeggio_patterns.py`
- **mappers / rom** → `mappers/`, `nes/project_builder.py`, `compiler/` → `tests/test_check_rom.py`
- **tempo** → `tracker/tempo_map.py`
- **config** → `config/config_manager.py` → `tests/test_config_manager.py`
- **core** → `core/` → `tests/test_core.py`

## Phase 3: Investigate
Read only the source files on the code path — don't pre-read a whole package, and don't
re-read files already in context. Trace the path inline. Confirm the bug reproduces (a
small MIDI under `test_midi/` or a crafted JSON in the scratchpad) before changing code.

**Specialist agents are a last resort.** Each is a fresh context window — only delegate
when the issue genuinely spans 2+ subsystems *and* you can't trace it yourself. Ask the
agent for a conclusion (file:line + cause), not file dumps.

**INVESTIGATION.md is optional.** Skip it for single-site fixes — the commit body covers
those. Write it only when the investigation uncovered non-obvious findings worth preserving
(a cross-stage JSON contract, a hardware quirk, a wrong-looking-but-correct invariant).

## Phase 4: Scope Check
If the fix touches >5 files, pause and confirm with the user before proceeding.

## Phase 5: Implement
Follow CLAUDE.md conventions and the user's global rules (improve existing code, don't
duplicate logic). Domain-specific musts:
- **NES values**: clamp to hardware range; Triangle has no volume/duty; use the correct
  per-channel pitch table (`docs/APU_PITCH_TABLE_REFERENCE.md`).
- **Inter-stage JSON**: if you change a stage's output shape, update its consumer in the
  same commit (see _audit-common § Inter-Stage Data Contracts).
- **Patterns/compression**: any change must preserve round-trip (decompressed == original).
- **No new dependencies** without user approval (`requirements.txt`).

## Phase 6: Verify
Scope first, widen at the end. Keep output quiet so logs don't flood context.

```bash
python -m pytest -q tests/test_<area>.py     # the Phase 2 target — fastest signal
python -m pytest -q                          # full suite — ONCE, final gate
```
For a ROM-affecting change, also run a real end-to-end build and a health check:
```bash
python main.py test_midi/<sample>.mid /tmp/audit/fix_<N>.nes
python -m debug.check_rom /tmp/audit/fix_<N>.nes
```
All tests must pass. Run the full suite a single time at the end, not per iteration. For a
fix confined to one area with no cross-stage surface, the scoped run + targeted e2e is
sufficient — note that you scoped it.

## Phase 7: Completeness Checks
Before committing, verify the rows that apply (mirrors `/audit-publish` step 7):
- [ ] **RANGE**: emitted NES values clamped to hardware range
- [ ] **CHANNEL**: Triangle no volume/duty; correct per-channel pitch table
- [ ] **CONTRACT**: stage JSON shape change propagated to the consumer
- [ ] **ROUNDTRIP**: pattern/compression change preserves playback
- [ ] **FALLBACK**: parallel-detector change keeps the sequential fallback working
- [ ] **CC65**: compiler change still surfaces nonzero exit + stderr
- [ ] **SIBLING**: same pattern checked in related files
- [ ] **TESTS**: regression test added
- [ ] **DOC**: any contradicted `docs/*.md` corrected

## Phase 8: Commit & Close
Branch off `master` if you are on it. Commit with a conventional message referencing the
issue (no AI co-author trailer, per the user's global rule):
```
fix: <description> (#<number>)
```
Then close:
```bash
gh issue close $ARGUMENTS --repo matiaszanolli/midi2nes --comment "Fixed in <commit-hash>"
```
