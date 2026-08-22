# EXP-2026-08-21-3: FamiStudio export recognizes only string frame keys — int-keyed frames dict silently exports all rests

GitHub: https://github.com/matiaszanolli/midi2nes/issues/441

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-08-21.md

## Description
Both CA65 emitters deliberately accept int **or** str frame keys (frames built in-memory carry int keys; JSON round-trips produce str keys). The FamiStudio path checks only `str(frame)`, so an in-memory frames dict exports a file of nothing but `... ..` rest rows with zero warning. Verified: 10 int-keyed frames → 10 rows, 0 non-rest. This is precisely the divergence class #370 fixed for `.get()` defaults, one level up (key lookup instead of field lookup).

## Location
`exporter/exporter_famistudio.py:101` (`if str(frame) in events:` — no int-key fallback)

## Spec ref
CA65 exporter's dual-key tolerance (`exporter_ca65.py:230-233` direct path, `:1169` bytecode path: `channel_frames.get(str(frame_idx), channel_frames.get(frame_idx))`)

## Impact
Library-only (not CLI-reachable); the JSON-mediated path is unaffected. Silent empty output rather than a crash, on an input shape the sibling exporter documents as valid.

## Related
#370/EXP-2026-07-19-2 (same file, same divergence class — fixed for `.get()` field defaults); EXP-2026-08-21-2 (companion FamiStudio-export finding, filed separately).

## Suggested Fix
Mirror the CA65 lookup: `event = events.get(str(frame), events.get(frame))`.

## Completeness Checks
- [ ] **SIBLING**: Same pattern checked in related files (CA65 exporter already has the dual-key fallback at `exporter_ca65.py:230-233` and `:1169` — this fix brings FamiStudio export in line)
- [ ] **TESTS**: A regression test pins this specific fix (int-keyed frames dict → non-rest rows in FamiStudio export)
