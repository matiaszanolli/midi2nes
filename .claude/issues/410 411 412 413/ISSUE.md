# #410 — ARR-2026-08-06-3: _assign_channels's BASS/triangle overflow recheck is unreachable from the live analysis pipeline

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-08-06.md

## Description
`arranger/role_analyzer.py:382`'s `if track.role == MusicalRole.BASS and not triangle_assigned:` overflow recheck is only reached (via the shared `if not assigned:` block at `:380-381`) after every earlier per-preferred-channel branch failed to assign the track. For a track whose `preferred_channel == NESChannel.TRIANGLE` (the TRIANGLE branch at `:342-346`), that only happens when `triangle_assigned` is already `True` — making the `:382` recheck of `not triangle_assigned` trivially `False` for any such track. Since `_determine_role` is the only place that ever sets `preferred_channel = NESChannel.TRIANGLE`, and it does so exactly when `role == MusicalRole.BASS`, every BASS track produced by the live `analyze_midi_events → create_arrangement_plan` pipeline already has `preferred_channel == TRIANGLE` — so it can never reach line 382 with `triangle_assigned` still `False`. The branch is exercised today only via `tests/test_role_analyzer.py`'s hand-constructed `TrackAnalysis(preferred_channel=NESChannel.PULSE1, role=MusicalRole.BASS, ...)`, a combination `_determine_role` itself never produces. The same reasoning makes the `NESChannel.ANY_PULSE`/`NESChannel.FLEXIBLE` branch (`:370-378`) unreachable from the live pipeline too.

## Evidence
`role_analyzer.py:264-276` is an exhaustive `if/elif` over the only 4 keys `role_scores` initializes (BASS, MELODY, HARMONY, DECORATIVE), and each branch sets `preferred_channel` to TRIANGLE/PULSE1/PULSE2/PULSE2 respectively — no path leaves it as ANY_PULSE, FLEXIBLE, or any other GM-curated value (see the companion finding on GM_INSTRUMENT_MAP's discarded `channel`).

## Impact
Maintenance/confusion only — a reader could reasonably believe a real BASS track can hit this recheck, or that ANY_PULSE/FLEXIBLE tracks flow through the live system, when both only exist for direct `_assign_channels` unit tests. No behavioral bug.

## Suggested Fix
Either simplify `_assign_channels`'s overflow block to drop the now-redundant BASS/ANY_PULSE/FLEXIBLE special-casing, or, if `_assign_channels` is meant to remain independently robust to hand-built `TrackAnalysis` objects, add a one-line comment noting these branches only matter for non-`_determine_role`-derived input.

## Completeness Checks
- [ ] **TESTS**: Existing `_assign_channels`-direct tests still pass after any simplification
- [ ] **DOC**: Comment added clarifying these branches' live-path reachability, if not removed outright

---

# #411 — SAFE-2026-08-06-1: run_export's DPCM-pack block gives zero feedback when dpcm_index.json is missing (asymmetric with run_full_pipeline)

**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-08-06.md

## Description
`pack_dpcm_into_asm` returns `DpcmPackResult(index_found=False)` with `warning=None` when `dpcm_index.json` does not exist (`main.py:146-148`). Both call sites receive this result, but only `run_full_pipeline` branches on `index_found` to print an info line; `run_export` only ever checks `if dpcm_pack_warning:` (`main.py:714`), which is `None` in this case, so nothing prints at all — the subcommand's success line is the only output, identical to what a drum-free song would also produce.

This is the same divergence the 2026-08-05 audit identified (tracked at the time as `Existing: #380`), but #380's actual fix (extracting the shared `pack_dpcm_into_asm` helper) explicitly preserved this exact behavior rather than closing it — the helper returns `index_found=False` precisely so each call site can decide what to print, and `run_export` still decides "nothing."

## Evidence
```python
# main.py:709-720 (run_export) — no branch on index_found
pack_result = pack_dpcm_into_asm(
    frames, args.output, verbose=getattr(args, 'verbose', False))
dpcm_pack_warning = pack_result.warning
print(f" Exported CA65 ASM -> {args.output}")
if dpcm_pack_warning:          # None when index_found is False -- never fires
    ...

# main.py:1097-1109 (run_full_pipeline) — explicit index_found branch
pack_result = pack_dpcm_into_asm(frames, music_asm, verbose=args.verbose)
dpcm_pack_warning = pack_result.warning
if not pack_result.index_found:
    print("  ℹ️ No dpcm_index.json found, skipping DPCM packing.")
elif pack_result.warning:
    print(f"  ⚠️ Warning: {pack_result.warning}")
```

## Impact
Confined to the step-by-step `export` subcommand's `.asm` output. The gap bites when `export` runs from a different working directory, a fresh checkout missing the index, or a CI job with a different cwd — a song with percussion silently loses its drums in the exported ASM with no warning of any kind. ROM/ASM byte content is unaffected either way (no DPCM data is emitted regardless of whether the message prints) — messaging-only LOW, not data-corruption.

## Related
#380/TD-28 (closed — extracted the shared helper this finding's evidence lives inside, but explicitly left presentation divergent); #381 (the sibling legacy-mapping guard gap, a harder failure of the same root dependency in `run_full_pipeline`'s mapping stage).

## Suggested Fix
Add the same `if not pack_result.index_found:` info-line branch to `run_export` that `run_full_pipeline` already has (or, better, move that one line of presentation into `pack_dpcm_into_asm` itself as an optional always-consistent print gated by a shared `print_status=True` flag).

## Completeness Checks
- [ ] **TESTS**: A regression test pins `run_export`'s stdout/behavior when `dpcm_index.json` is missing
- [ ] **SIBLING**: `run_full_pipeline`'s equivalent branch re-checked for the same wording after the fix
- [ ] **DOC**: n/a

---

# #412 — TD-30: Duplicate defaultdict import in nes/emulator_core.py

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-06.md

## Description
`from collections import defaultdict` is imported twice in `nes/emulator_core.py` — once on line 1 and again on line 3, with the unrelated `from .pitch_table import PitchProcessor` import sandwiched between them. The second import shadows/redefines the first with no functional difference; it's inert cruft, caught via a `pyflakes` sweep.

## Evidence
```python
# nes/emulator_core.py:1-9
from collections import defaultdict
from .pitch_table import PitchProcessor
from collections import defaultdict
from .envelope_processor import (
    EnvelopeProcessor,
    velocity_to_volume,
    NOISE_DECAY_FRAMES,
    noise_strike_decay_volume,
)
```
`python3 -m pyflakes nes/emulator_core.py` → `nes/emulator_core.py:3:1: redefinition of unused 'defaultdict' from line 1`.

## Impact
None functionally — Python import caching makes the second `import` a no-op after the first. Purely a readability/maintainability nit. A repo-wide duplicate-import grep found this as the only instance.

## Suggested Fix
Delete the redundant `from collections import defaultdict` on line 3; keep the line-1 import. One-line diff, zero risk.

## Completeness Checks
- [ ] **TESTS**: n/a (no behavior change)

---

# #413 — DP-DPCM-07: _real_sample_size doesn't cache unresolvable (missing-file) lookups

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-08-06.md

## Description
`_real_sample_size` (`dpcm_sampler/enhanced_drum_mapper.py:227-250`) caches a successfully-resolved size in `self._sample_size_cache[sample_name]` before returning it, but both early-return `None` paths — no `filename` key, and `resolve_dpcm_sample_path` returning `None` — return directly without writing anything to the cache. The method's own docstring/callsite comment describe the cache as making a reused drum "cost one `os.path.getsize` call" per song, but that guarantee only holds for the resolved case. A catalog sample whose `filename` doesn't resolve to an existing file (index references a `.dmc` that was moved/deleted from the `dmc/` root) re-runs the full `resolve_dpcm_sample_path` candidate-path probe (up to 3 `Path.exists()` stats) on every single occurrence of that drum in the song, not just the first.

## Evidence
```python
def _real_sample_size(self, sample_name, sample_data):
    if sample_name in self._sample_size_cache:
        return self._sample_size_cache[sample_name]
    filename = sample_data.get('filename')
    if not filename:
        return None                      # <- not cached
    path = resolve_dpcm_sample_path(filename, self.dpcm_index_path)
    if path is None:
        return None                      # <- not cached
    size = os.path.getsize(path)
    self._sample_size_cache[sample_name] = size
    return size
```
`tests/test_enhanced_drum_mapper.py:613-621` (`test_unresolvable_sample_falls_back_to_placeholder`) covers correctness of the fallback but not the repeated-call cost; `tests/test_enhanced_drum_mapper.py:623-630` (`test_repeated_allocation_reuses_cached_size`) only exercises the successful-resolution cache path.

## Impact
Purely a performance/documentation-accuracy gap, not a correctness issue — the fallback to the 1024-byte placeholder still happens correctly every time. Extra filesystem stats are cheap relative to a full pipeline run; worst case is a song that hits one missing/mislabeled drum sample dozens or hundreds of times.

## Related
#341/DP-DPCM-02 (this cache was added to fix that issue's placeholder-size problem); #367/DP-DPCM-05 (the packer-side "partial miss" path this same missing-file scenario feeds into downstream).

## Suggested Fix
Cache the miss too — store `None` in `self._sample_size_cache[sample_name]` before returning on both early-exit paths; the cache-hit check already works correctly for a cached `None` value since `dict.__contains__` doesn't care about the stored value.

## Completeness Checks
- [ ] **TESTS**: A regression test asserts `resolve_dpcm_sample_path` is called exactly once for a repeated unresolvable sample
- [ ] **DOC**: Docstring/comment already correctly describes intended behavior; no change needed there once the cache is fixed
