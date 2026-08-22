# Issue #427: PIPE-2026-08-21-5: import_bank validates bank-level shape but not per-song entries — a malformed bank crashes song build/song list with a raw KeyError

- **Finding**: PIPE-2026-08-21-5
- **Labels**: medium, pipeline, bug
- **Filed**: 2026-08-21 (audit-publish, AUDIT_PIPELINE_2026-08-21.md)
- **URL**: https://github.com/matiaszanolli/midi2nes/issues/427

---

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-21.md

## Description

#220/SAFE-09 added the bank-level guard in `SongBank.import_bank` (`nes/song_bank.py:200-227`) specifically so a corrupt or hand-edited bank fails with a clean message instead of a raw traceback, but the guard stops one level up: `data['songs']` values are stored as-is with no per-song-entry validation.

A song entry missing `'metadata'` (or with a non-dict value, or missing `'bank'` for `song list`) raises an uncaught `KeyError`/`TypeError` inside `run_song_build`'s sort key (`main.py:953-954`, `bank.songs[name]['metadata'].get('order', 0)` — outside the surrounding `try` that wraps only `import_bank`) or `run_song_list`'s print loop (`main.py:844-853`) — a raw traceback, the exact presentation #220 was closing off. (`main.py:962-963`'s `song_data.get('midi_path')` is defensive already.)

Banks written by `export_bank` always carry the keys, so this needs a hand-edited/truncated/version-drifted bank file — defense-in-depth, not a mainline break.

## Evidence

Code read: `import_bank` assigns `self.songs = data['songs']` with no per-entry validation; `run_song_build:954` indexes `['metadata']` unguarded inside the `sorted()` key lambda.

## Impact

Raw traceback instead of a clean `[ERROR]` on a malformed user file; exit is still nonzero and no ROM is produced, so no corruption — a robustness/UX gap.

## Related

#220/SAFE-09, #120/SAFE-01 (same defect class).

## Suggested Fix

In `import_bank`, validate each song entry is a dict with a dict `'metadata'` (raising the same `ValueError` style it already uses), or make the three consumer sites use `.get()` with defaults.

## Completeness Checks
- [ ] **CONTRACT**: The per-song entry shape `import_bank` guarantees matches what all consumers (`run_song_build`, `run_song_list`, `get_bank_size`) index
- [ ] **SIBLING**: All consumer sites of `bank.songs[...]` checked, not just the sort key (`song list` print loop, `midi_path` read, `size` sum)
- [ ] **TESTS**: A regression test pins this specific fix (malformed song entry → clean `[ERROR]`, nonzero exit, no traceback)
