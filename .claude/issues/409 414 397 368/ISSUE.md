# #409 — ARR-2026-08-06-2: Last-resort triangle fallback lets a lower-priority HARMONY/DECORATIVE track survive while a higher-priority MELODY track is dropped

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-08-06.md

## Description
`create_arrangement_plan` sorts `plan.tracks` by `priority` descending (`arranger/role_analyzer.py:287-289`) so higher-priority tracks get first claim on channels and any drop should fall to the lowest-priority contender. But the last-resort triangle fallback (reached only after PULSE1 and PULSE2 are both full, `:380-397`) is gated on `track.role != MusicalRole.MELODY` — not on priority, and not restricted to `MusicalRole.BASS` alone despite `tests/test_role_analyzer.py::test_third_melody_track_is_dropped_with_note`'s own docstring asserting "triangle is reserved for bass." In practice HARMONY and DECORATIVE roles are equally eligible for that fallback. Because the exclusion is role-based rather than priority-based, a MELODY track processed **earlier** (higher priority) can still be dropped when both pulse channels fill up, while a HARMONY/DECORATIVE track processed **later** (lower priority) is still allowed to claim the now-idle triangle — the opposite of "highest priority survives."

## Evidence
Reproduced against the live pipeline (3 MELODY tracks at priority 8, no bass, 1 HARMONY track at priority 6):
```python
from arranger.pipeline_integration import analyze_midi_events
events = {
    'lead1': [{'frame':0,'note':76,'volume':110,'channel':0,'program':80},
              {'frame':60,'note':76,'volume':0,'channel':0,'program':80}],
    'lead2': [{'frame':0,'note':79,'volume':110,'channel':1,'program':80},
              {'frame':60,'note':79,'volume':0,'channel':1,'program':80}],
    'lead3': [{'frame':0,'note':81,'volume':110,'channel':2,'program':80},
              {'frame':60,'note':81,'volume':0,'channel':2,'program':80}],
    'pad':   [{'frame':0,'note':55,'volume':60,'channel':3,'program':4},
              {'frame':0,'note':58,'volume':60,'channel':3,'program':4},
              {'frame':0,'note':62,'volume':60,'channel':3,'program':4},
              {'frame':600,'note':55,'volume':0,'channel':3,'program':4},
              {'frame':600,'note':58,'volume':0,'channel':3,'program':4},
              {'frame':600,'note':62,'volume':0,'channel':3,'program':4}],
}
plan, _, _ = analyze_midi_events(events)
# pulse1: [0] (lead1)   pulse2: [1] (lead2)
# triangle: [3] (pad, priority 6)   dropped: [2] (lead3, priority 8)
```
`lead3` (priority 8) is dropped while `pad` (priority 6) keeps playing on triangle.

## Impact
On any MIDI with 3+ purely-melodic/harmonic voices and no distinct bass line (a common case: three-part harmony with no separate bass, or a synth-pad-heavy arrangement), the arranger can silently drop a musically more important voice in favor of a less important one, contradicting its own stated priority-based drop policy. Playable but musically wrong; no crash or data corruption.

## Suggested Fix
Either (a) tighten the guard to `track.role == MusicalRole.BASS` only, matching the test's documented intent, or (b) if HARMONY/DECORATIVE-on-triangle is intentional, make the fallback priority-aware — only let a later, lower-priority track claim triangle if no earlier, higher-priority track was dropped for lack of it — and update the test docstring to describe the real (broader) rule.

## Completeness Checks
- [ ] **CONTRACT**: Priority-sort invariant documented and enforced consistently across all fallback branches, not just triangle
- [ ] **TESTS**: A regression test pins the mixed-role scenario (3 MELODY + 1 HARMONY, no BASS) to the correct drop order
- [ ] **DOC**: `test_third_melody_track_is_dropped_with_note`'s docstring corrected to match the actual (or fixed) rule

---

# #414 — REG-26: TestCA65CompilationIntegration lacks @pytest.mark.requires_cc65, hard-fails instead of skipping when CC65 is absent

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-08-06.md

## Description
Every other test class in the suite that shells out to real `ca65`/`ld65` is gated with `@pytest.mark.requires_cc65`, which `conftest.py`'s `pytest_runtest_setup` skips cleanly only when the toolchain is genuinely absent (`shutil.which`). `TestCA65CompilationIntegration` (`tests/test_ca65_export.py:706-975`, all 9 methods) — the suite's oldest "does the exporter still produce a compilable ROM" gate — was never migrated to this convention. Its helper `_compile_and_link` wraps the `subprocess.run(['ca65', ...])`/`subprocess.run(['ld65', ...])` calls in a bare `try/except Exception as e: return False, f"Error during compilation: {str(e)}"`, so a missing binary (`FileNotFoundError`) is caught and turned into a normal `(False, ...)` return — which every test then feeds into `self.assertTrue(success, ...)`, producing a real, loud **test FAILURE** (not a skip) that reads exactly like a genuine ROM-compile regression.

## Evidence
Directly reproduced by stripping `/usr/bin` (where `ca65`/`ld65` live) from `PATH` and re-running one test:
```
$ env PATH="<PATH without /usr/bin>" python -m pytest \
    tests/test_ca65_export.py::TestCA65CompilationIntegration::test_basic_project_compilation -v
...
AssertionError: False is not true : Compilation failed:
Error during compilation: [Errno 2] No such file or directory: 'ca65'
FAILED tests/test_ca65_export.py::TestCA65CompilationIntegration::test_basic_project_compilation
```
`grep -n "requires_cc65" tests/test_ca65_export.py` returns nothing, versus 3 other files (`test_debug_overlay.py`, `test_e2e_pipeline.py`, `test_rom_validation_integration.py`) that do use the marker.

## Impact
This repository has no CI workflow enforcing that CC65 is present wherever the suite runs, and CC65 is an external, manually-installed toolchain per CLAUDE.md. Any contributor without `ca65`/`ld65` on `PATH` who runs this file (the project's own documented practice of scoping pytest to specific files) sees 9 failures that look exactly like a real "ROM stopped compiling" regression, with no indication the actual cause is an absent dev-tool. No production/ROM impact when CC65 is present — verified all 9 tests pass correctly in that case.

## Related
REG-01/#39 (the original fix to this class); REG-10/REG-11/#128/#129 (the precedent this class should follow); `tests/conftest.py:19-43` (the shared `CC65_AVAILABLE` gate to reuse).

## Suggested Fix
Add `@pytest.mark.requires_cc65` to `TestCA65CompilationIntegration` (class-level, matching `TestPipelineFailureRecovery`'s pattern), so the class skips cleanly via the shared `conftest.py` gate when the toolchain is genuinely absent instead of failing. Optionally also narrow `_compile_and_link`'s `except Exception` to surface a truly unexpected error distinctly from "tool not found."

## Completeness Checks
- [ ] **TESTS**: Verified the class still runs (and passes) with CC65 present after adding the marker
- [ ] **CC65**: Confirms nonzero-exit + stderr still surface correctly once gated
- [ ] **SIBLING**: Marker style matches the 3 existing `requires_cc65` usages exactly

---

# #397 — TD-29: Stray zero-byte skip file checked into repo root

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH-DEBT_2026-08-05.md

## Description
A 0-byte file named `skip` is tracked at the repo root, added in commit `cadff6d` ("Add new skip file for pipeline audit tracking", 2026-07-06). The commit's other eight changed files are unrelated `.claude/issues/*` and `docs/audits/*` additions — `skip` appears to be an accidental artifact of an unrelated `touch`/`git add .` swept into that commit rather than an intentional addition. No code, test, script, or doc references a file named `skip` anywhere in the tree.

## Location
`skip` (repo root, tracked, 0 bytes)

## Evidence
```
$ git ls-files | grep -v '/'
... constants.py dpcm_index.json input.mid main.py requirements.txt skip validate_rom.py

$ git show cadff6d -- skip
diff --git a/skip b/skip
new file mode 100644
index 0000000..e69de29

$ grep -rn "'skip'\|\"skip\"" --include='*.py' .
(no matches)
```

## Impact
None functionally — the file is inert. Purely cosmetic/hygiene: a stray tracked file at repo root that new contributors may mistake for something meaningful, and that clutters `git ls-files` / root directory listings.

## Suggested Fix
`git rm skip` in a small hygiene commit. If it was meant to mark something (its commit message suggests "pipeline audit tracking"), replace it with a real, named artifact or drop the intent entirely — a content-less file conveys no information.

## Completeness Checks
- [ ] **RANGE**: n/a
- [ ] **CHANNEL**: n/a
- [ ] **CONTRACT**: n/a
- [ ] **ROUNDTRIP**: n/a
- [ ] **FALLBACK**: n/a
- [ ] **CC65**: n/a
- [ ] **SIBLING**: n/a
- [ ] **TESTS**: n/a — not testable code
- [x] **DOC**: n/a — no doc references it either

---

# #368 — DP-DPCM-06: drum_engine.py ships production-dead helpers, one with a latent noise-contract bug

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-19.md

**Dimension:** 1 (drum mapping) / tech-debt

**Location:**
- `dpcm_sampler/drum_engine.py:109-143` (`optimize_dpcm_samples`)
- `dpcm_sampler/drum_engine.py:146-166` (`DrumPatternAnalyzer`)

## Description
Both `optimize_dpcm_samples` and the `DrumPatternAnalyzer` class are imported only by tests (`tests/test_drum_mapping.py`; grep shows no production caller). `DrumPatternAnalyzer`'s `detect_patterns` / `detect_groove` / `optimize_mapping` are empty bodies (implicit `return None`), and `analyze_drum_track` feeds those `None`s forward — the class cannot do anything. Separately, `optimize_dpcm_samples` builds its noise fallback as `{"frame": ..., "velocity": ...}` with **no `note` key**, contradicting the noise-event contract the live `map_drums` path was fixed to honor (#195/NH-26: `process_all_tracks` derives a noise period via `midi_to_nes_pitch()` from `note`). It is inert today only because nothing wires it into the pipeline.

## Evidence
`drum_engine.py:138-141`:
```python
noise_fallback.append({
    "frame": event['frame'],
    "velocity": event['velocity'],
})   # no 'note' — would KeyError/mis-pitch in process_all_tracks
```
`DrumPatternAnalyzer.detect_patterns/detect_groove/optimize_mapping` (lines 157-167) have only docstrings/comment bodies, returning `None`.

## Impact
Dead surface area and drift risk; if either helper is ever re-wired the missing `note` key becomes a real `KeyError`/silent mis-pitch on the noise channel.

## Related
#195/NH-26 (noise `note` contract), #331/#302 (other dead public API).

## Suggested Fix
Delete both (and their tests) if the roadmap has no consumer, or finish `DrumPatternAnalyzer` and add the `note` key to `optimize_dpcm_samples`'s fallback so it matches the live contract.

## Completeness Checks
- [ ] **CHANNEL**: Noise events carry a `note` so the correct noise period is derived
- [ ] **SIBLING**: Same pattern checked in related drum/noise fallback paths
- [ ] **TESTS**: If kept, a test pins the `note`-bearing fallback contract; if deleted, dead tests removed too
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
