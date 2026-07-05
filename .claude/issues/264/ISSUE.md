# TD-20: Unused imports are repo-wide (47 sites in 9 directories) — tracked issues cover only 2  (#264)

**Severity:** LOW · **Domain:** tech-debt · **Dimension:** Dead Code & Cruft · **Source:** AUDIT_TECH-DEBT_2026-07-05.md

## Description
`pyflakes` over all tracked `*.py` (excluding `tests/` and `venv/`) reports **56** `imported but unused` sites; only 9 fall in `main.py`/`debug/`, already tracked by #227 and #228. The remaining **47** are untracked, spread across `arranger/` (17), `tracker/` (6), `exporter/` (5), `dpcm_sampler/` (4), `core/` (3), `mappers/` (3), `nes/` (3), `utils/` (3), `benchmarks/` (2), `config/` (1).

The `arranger/` package is the worst offender: `arranger/pipeline_integration.py` alone imports `Any`, `Optional`, `defaultdict`, `get_instrument_mapping`, `get_drum_mapping`, `NESChannel`, `FrameByFrameAllocator`, `VoiceAllocator`, `ArpStyle` — none referenced in that file. These are genuine dead imports, not `__all__` re-exports (the package's `__all__` lives in `arranger/__init__.py`, which imports *from* the submodules, not the reverse).

Representative sites: `arranger/pipeline_integration.py:8-13`, `tracker/parser.py:4-5`, `tracker/parser_fast.py:4-5`, `mappers/base.py:9-10`, `core/dto.py:10-11`, `nes/debug_overlay.py:14`, `config/config_manager.py:3`.

## Evidence
```
python -m pyflakes $(git ls-files '*.py' | grep -v '^tests/' | grep -v venv)  → 56 "imported but unused"
  filtering out ^main\.py|^debug/  → 47 remain
grep -c defaultdict arranger/pipeline_integration.py  → 1 (import only)
```
Re-verified 2026-07-05: 56 total / 47 outside main.py+debug/.

## Impact
LOW — no pipeline/ROM effect. Misleads readers about each module's real dependency surface and inflates the import graph. Two identical dead-import lines in `tracker/parser.py` and `tracker/parser_fast.py` (`FRAME_MS`, `TempoOptimizationStrategy`) are a small duplication-drift signal between the two parsers.

## Suggested Fix
One mechanical `pyflakes`/`ruff --select F401` sweep across the repo; add `ruff` (or a `pyflakes` pre-commit hook) so this class stops re-accumulating. Scope the fix to imports only — the co-reported `f-string is missing placeholders` warnings are cosmetic no-ops.

## Related
Extends #227 (TD-15, `main.py`), #228 (TD-16, `debug/`), #112 (P-04) — same pattern, different files.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (all 9 dirs swept, not just arranger/)
- [ ] **TESTS**: A `ruff`/`pyflakes` gate pins this fix so F401 stops re-accumulating
- [ ] **DOC**: No doc contradicts the change (import-only)
