# TD-44: input.mid — a 31KB third-party copyrighted MIDI tracked at the repo root, and it isn't the file README's benchmarks describe

- **Issue**: #464

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** NEW

## Description
The tracked `input.mid` is a third-party sequenced song (track names: "Sequenced by Steven Picken", "Edited by MaliceX", "(C) 2002-2003 Steven Picken"; 14 tracks, 31,146 bytes, file mtime 2007). README's "Test Results (input.mid — 51KB, 15 tracks)" benchmark section describes a different file, so the tracked sample is not even the documented baseline. No test depends on the file existing (test references use the name only as a CLI-args placeholder).

## Evidence
```
$ ls -la input.mid
-rwxr-xr-x 1 matias matias 31146 Sep 14  2007 input.mid

$ python3 -c "import mido; m=mido.MidiFile('input.mid'); print(len(m.tracks))"
14
```
Track metadata contains "Sequenced by Steven Picken" / "Edited by MaliceX", vs `README.md:37,44` ("51KB, 15 tracks, 13,362 events").

## Impact
A copyrighted asset of unclear provenance distributed with the repo, plus benchmark numbers that can't be reproduced against the file that ships. Legal/repro hygiene, no runtime impact.

## Suggested Fix
Remove `input.mid` from tracking (the benchmark suite already has deterministic synthetic fixtures per #372/#373) and update README's example section to reference a generated fixture; or replace it with an original, license-clean demo MIDI whose stats match the README table.

## Related
TD-29/#397 (prior stray root file, fixed); #372/#373 (deterministic benchmark fixtures — the synthetic-fixture machinery that could replace this).

## Completeness Checks
- [ ] **DOC**: README's benchmark section is updated to match whatever file (if any) actually ships
