**Severity:** MEDIUM · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-06-29.md

## Description
The full-pipeline DPCM packing step wraps `json.load(dpcm_index.json)`, `sorted(... key=lambda x: x['id'])`, `sample['filename']`/`sample['id']`/`sample.get('pitch', 15)`, and `packer.generate_assembly()` in one broad `except Exception as e: print("... Warning: Failed to pack DPCM samples ...")` and continues. A malformed `dpcm_index.json` (bad JSON, or any sample dict missing the `id`/`filename` key) raises `JSONDecodeError`/`KeyError`, is swallowed, and the ROM is built with **no drums** — the song is silently changed with only a warning line.

Per `_audit-severity.md`, "a MIDI event class dropped on the floor with no warning, changing the song" is a CRITICAL floor; downgraded here to MEDIUM because (a) it prints a visible warning, and (b) DPCM/drums are an optional add-on whose absence does not break the ROM — closer to "swallowing on an optional path" than full silent data loss.

## Location
- `main.py:532`–`572` (full pipeline)
- mirrored in `run_export` at `main.py:253`–`269`

## Evidence
`main.py:568`: `except Exception as e: print(f"  ⚠️ Warning: Failed to pack DPCM samples: {str(e)}")`. The `try` covers `json.load`, `sorted(dpcm_index.values(), key=lambda x: x['id'])`, and `sample['filename']`/`sample['id']` — any `KeyError`/`JSONDecodeError` there drops all drums. The `run_export` mirror (`main.py:268`) has the same shape.

## Impact
A drum-mapping/index regression produces a silently drumless ROM that a user mistakes for a good build. Affects every ROM using DPCM samples.

## Related
- **Distinct from #68 (D-05).** #68 is an *oversized `.dmc`* raising `ValueError` from `add_sample` that aborts the whole pack. This is a *corrupt/partial `dpcm_index.json`* (bad JSON / missing `id`/`filename`) raising `JSONDecodeError`/`KeyError` in the index-load/sort path — a different exception source that #68's per-sample `ValueError` guard would not catch. Same code region, different failure mode.
- Distinct from #23 (F-10, DPCM `'a'`-mode append clobbering).

## Suggested Fix
Narrow the catch — let a malformed-index error (`KeyError`/`JSONDecodeError`) abort with a typed error instead of warn-and-continue, OR at minimum surface "ROM built WITHOUT drums" prominently in the success banner (mirroring the `pattern_loss_warning` mechanism at `main.py:628`).

## Completeness Checks
- [ ] **CONTRACT**: If `dpcm_index.json` shape changes, the loader keys (`id`/`filename`) are validated, not blindly indexed
- [ ] **SIBLING**: Same fix applied at both DPCM-pack sites (full pipeline `:532`–`572` and `run_export` `:253`–`269`)
- [ ] **TESTS**: A regression test pins this fix (corrupt/partial index → typed error or prominent drumless warning, not silent)
