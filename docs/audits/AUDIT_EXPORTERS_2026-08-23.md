# Exporters Audit — 2026-08-23

Scope: `exporter/exporter_ca65.py` (direct `export_direct_frames`, MMC3 macro-bytecode
`export_tables_with_patterns`, jukebox `export_song_bank_bytecode` + shared
`_build_song_bytecode`), `exporter/exporter_nsf.py`, `exporter/exporter_famistudio.py`,
and their consumers (`nes/project_builder.py`, `nes/audio_engine.asm`, `main.py`
export/song-build dispatch). Cross-checked against `docs/AUDIO_BYTECODE_SPEC.md` and
`docs/MACRO_USAGE_GUIDE.md`.

**Method**: `git log --since="2026-08-21"` on every file this domain touches identified
nine relevant commits (`fa179ae`, `03446c5`, `e6ab23e`, `70ae14f`, `bd5d431`, `0a16a93`,
`a9a7a21`, `a63be2d` visualizer-only/out-of-scope, `394cddb` — my own prior commit this
session, `song build` memory fix). Read each diff in full against
`AUDIT_EXPORTERS_2026-08-21.md`'s nine findings plus its four cross-audit-dedup items,
rather than trusting titles. Cross-referenced every EXP-2026-08-21-N /
NH-HW-2026-08-21-N number against `gh issue list --state all --limit 500` (372 issues).
Because `394cddb` (this session, `/fix-issue 504 505 506`) rewrote
`export_song_bank_bytecode`'s song-consumption loop, this audit treats that method as
freshly-changed code for Dimensions 1 and 9, not a verify-the-fix pass.

## Summary

### Counts by severity
| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 4 |
| **Total**| **5** |

### Counts by dimension
| Dimension | Count |
|-----------|-------|
| D1 CA65 well-formedness / builder compat | 1 |
| D2 APU register serialization | 0 |
| D3 Pattern-vs-empty paths | 0 |
| D4 Byte-range safety | 0 |
| D5 Bytecode-spec conformance | 2 |
| D6 Macro emission | 0 |
| D7 Cross-exporter consistency | 0 |
| D8 Format-string / CLI choices | 0 |
| D9 Multi-song jukebox export | 2 |

### Three highest-impact findings
1. **EXP-2026-08-23-2 (MEDIUM, D9, carried from 2026-08-07/08-21)** —
   `export_song_bank_bytecode`/`_build_song_bytecode` still has no self-contained DPCM
   guard; a direct API consumer (any caller other than `main.py`'s `run_song_build`)
   can feed it DPCM frames and get a silently out-of-bounds DMC trigger. Third
   consecutive audit to find this unfixed and unfiled.
2. **EXP-2026-08-23-1 (LOW, D5)** — `docs/AUDIO_BYTECODE_SPEC.md` still documents `$87
   CMD_DMC_LEVEL` as a real, working opcode, but the handler that made that claim true
   (`@cmd_dmc_level`) was deleted from `nes/audio_engine.asm` by `#309` on 2026-07-17 —
   *after* `#83/EXP-07` had fixed the doc to say exactly that on 2026-07-04. The doc
   fix regressed silently when the code moved out from under it. Flagged as
   NH-HW-2026-08-21-7 two audits ago; still never filed.
3. **Verification highlight** — six of the nine 2026-08-21 findings (EXP-2026-08-21-1,
   -2, -3, -7, -8, -9) plus both HIGH/CRITICAL cross-audit items (32-instrument ceiling,
   51-song 8-bit indexing) are now genuinely fixed with regression tests, closed
   GitHub issues (#439, #440, #441, #442, #443, #444, #429, #426), and (for the
   32-frame retrigger and 51-song cap) real `ld65`-level verification recorded in
   their commit messages. This was a highly productive fix cycle — see "Verification
   of prior fixes" below for the full mapping.

## Verification of prior fixes (from AUDIT_EXPORTERS_2026-08-21.md)

| 2026-08-21 finding | Fixed by | Verified |
|---|---|---|
| EXP-2026-08-21-1 (32-frame retrigger click) | #439 (`70ae14f`) | `docs/AUDIO_BYTECODE_SPEC.md:15` now documents same-note-byte-is-tie semantics citing #439; `nes/audio_engine.asm`'s `@is_note` no longer unconditionally resets phase on a same-pitch repeat |
| EXP-2026-08-21-2 (FamiStudio pattern/key numbering) | #440 (`70ae14f`) | `exporter_famistudio.py` full-pattern keys now use a per-channel counter, matching `SEQUENCE`'s numbering |
| EXP-2026-08-21-3 (FamiStudio int-key frames) | #441 (`70ae14f`) | dual-key `.get(str(frame), .get(frame))` lookup now present |
| EXP-2026-08-21-7 (volume macro byte-range) | #442 (`bd5d431`) | `vol = max(0, min(15, ...))` clamp confirmed at both note-start and continuation sites, `exporter_ca65.py:1324` |
| EXP-2026-08-21-8 (bank-window comment) | #443 (`bd5d431`) | `nes/project_builder.py` comment corrected |
| EXP-2026-08-21-9 (direct-export size summary) | #444 (`bd5d431`) | summary now reuses `estimate_direct_export_size` |
| Cross-audit: 32-instrument ceiling (NH-HW-2026-08-21-1) | #429 (`03446c5`) | `_register_instrument` now guards at `0x1F`, not `0xFF` |
| Cross-audit: 51-song 8-bit indexing (PIPE/NH-HW-2026-08-21-3) | #426 (`fa179ae`) | `max_songs` bound at `exporter_ca65.py:1766` still derived from `len(SEQUENCE_CHANNELS)`, not hardcoded |
| Cross-audit: phantom DPCM rejection (PIPE-2026-08-21-1) | #425 (`fa179ae`) | `_song_has_dpcm_events` (now `main.py:984`) still the sole caller-side guard — see EXP-2026-08-23-2 below for why this doesn't close the exporter-side gap |
| EXP-2026-08-21-4 (D9, no exporter-side DPCM guard) | **not fixed** | re-verified below as EXP-2026-08-23-2 |
| EXP-2026-08-21-5 (D5, spec doc missing `song_table`) | **not fixed** | re-verified below as EXP-2026-08-23-3 |
| EXP-2026-08-21-6 (D9, bank-overflow error lacks song identity) | **not fixed** | re-verified below as EXP-2026-08-23-4 |
| Cross-audit: `$87` spec doc vs removed handler (NH-HW-2026-08-21-7) | **not fixed** | re-verified below as EXP-2026-08-23-1 (was never filed under either domain — filing here) |

Also spot-checked unrelated to the above: `e6ab23e`'s #430 (last-frame drop) and #432
(uninitialized `last_*_note` seed) both touched `exporter_ca65.py`'s direct-export
proc-generation code (`:688-1005`) with real `cc65`-verified fixes and regression
tests; `0a16a93`'s #482 (DPCM sentinel) touched the same seed block again correctly.
Neither is bytecode-path or jukebox-path code, so neither interacts with this
session's `export_song_bank_bytecode` refactor (`394cddb`) — confirmed by re-reading
both diffs in full.

## Self-review of this session's own change (`394cddb`, #505/#506)

`export_song_bank_bytecode`'s per-song consumption loop was rewritten this session to
accept a lazily-consumed iterable instead of a materialized list. Audited as new code:

- **Segment discipline held.** `_build_song_bytecode` itself (the function that
  re-declares `.segment "CODE_8000"` before each song's instrument/macro tables,
  `exporter_ca65.py:1483`) was not touched — only the outer loop that calls it once
  per song changed from `for prefix, song in zip(song_labels, songs_list)` to the same
  shape over a generator. `test_accepts_a_lazily_consumed_generator_with_explicit_song_count`
  (added this session) pins byte-identical output between the list and generator
  paths, structurally confirming no segment/symbol placement drift.
- **New asymmetric-validation gap (filed below, EXP-2026-08-23-5).** The
  `songs_consumed != song_count` guard added this session (`:1826-1830`) only catches
  a lazy iterable yielding *fewer* items than declared. `zip(song_labels, songs)`
  silently stops at `song_labels`' length if `songs` yields *more* — a caller passing
  an inconsistent song_count in the "too many" direction gets silent truncation, not
  an error. No live caller triggers this today (`main.py`'s only call site always
  passes a matching count), so this is LOW/defense-in-depth, not a live bug.

## Findings

### EXP-2026-08-23-1: `docs/AUDIO_BYTECODE_SPEC.md` still documents `$87 CMD_DMC_LEVEL` as a working opcode after the engine handler that implemented it was deleted
- **Severity**: LOW
- **Dimension**: 5 (Bytecode-Spec Conformance)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md:106,113`
- **Location**: `docs/AUDIO_BYTECODE_SPEC.md:106` ("...omitted `$87`/`$FE`, both real, working opcodes (#83/EXP-07)"), `:113` (`$87` table row: "Writes a 7-bit DMC output level... directly to `$4011`") vs. `nes/audio_engine.asm:376-434` (dispatcher: `cmp #$FE` → `@cmd_bank_jump`, `cmp #$85` → `@cmd_dpcm_play`, `cmp #$80` → `CMD_INSTRUMENT`, anything else including `$87` falls through to `@unknown_command`, which `jmp @end_of_stream` — halts the sequence)
- **Status**: NEW (no GitHub issue covers this exact drift; `#83`/`#72`/`#309` each cover one side of the timeline, not the resulting mismatch — see below)
- **Description**: `#83/EXP-07` (2026-07-04, commit `b7c99c8`) corrected the spec to
  document `$87 CMD_DMC_LEVEL` as real and working, which was true at the time. `#309`
  (2026-07-17, commit `f78c618`, titled "remove orphan `@cmd_dmc_level` handler from
  the playback engine") then deleted that exact handler as dead code — accurately, since
  `#72` had already removed the only producer that could emit `$87` — but nobody
  re-touched the spec doc `#83` had just fixed. The doc now claims a "real, working"
  opcode that the shipped engine no longer decodes at all; hitting `$87` today would
  silently halt that channel's sequence via `@unknown_command`, not write a DMC level.
  This exact mismatch was already spotted once, as a cross-audit-dedup item
  (NH-HW-2026-08-21-7) in `AUDIT_EXPORTERS_2026-08-21.md`, attributed to the
  nes-hardware domain — but it was never filed as a GitHub issue under either domain,
  so it survived unfixed for a second audit cycle.
- **Evidence**: `git log --oneline --all -- nes/audio_engine.asm | grep dmc_level` →
  `f78c618 fix: remove orphan @cmd_dmc_level handler from the playback engine (#309)`,
  dated after `b7c99c8`'s spec fix (`#83`). Current dispatcher grep for
  `@cmd_dmc_level`/`$87` in `nes/audio_engine.asm` returns nothing.
- **Impact**: Doc-rot only — no exporter path emits `$87` (confirmed `#72`'s removal
  holds: no `$87`/`DMC_LEVEL` string anywhere in `exporter/exporter_ca65.py`), so no
  ROM is affected. A future implementer trusting the spec table would write a `$87`
  emitter expecting a working DMC-level command and get a silently truncated sequence
  instead.
- **Related**: `#83`/`#72`/`#309` (each already closed, none covers this resulting
  gap); cross-referenced from `AUDIT_EXPORTERS_2026-08-21.md`'s cross-audit-dedup
  item 3.
- **Suggested Fix**: Either restore the `@cmd_dmc_level` handler (if DMC-level control
  is wanted) or, more consistent with `#72`'s "no live producer" rationale, remove the
  `$87` row from the spec table (or mark it "removed, #309 — was implemented by #83,
  deleted as dead code") the same way `$FE`'s in-macro loop-byte was marked
  reserved/not-implemented in `#163/NH-21`.

### EXP-2026-08-23-2: `export_song_bank_bytecode`/`_build_song_bytecode` still has no self-contained DPCM guard — enforcement lives entirely in the CLI caller
- **Severity**: MEDIUM
- **Dimension**: 9 (Multi-Song Jukebox Export)
- **Spec ref**: `nes/project_builder.py` (1-byte DPCM stub tables in a jukebox build); `docs/ROADMAP.md` ("song build" v1 rejects DPCM)
- **Location**: `exporter/exporter_ca65.py:1245-1600` (`_build_song_bytecode` — its only DPCM-specific check is the per-note range guard at `:1353-1362`, `if note >= 0x60: raise ValueError`, which rejects an out-of-range sample id but not the presence of a `dpcm` channel at all); `exporter/exporter_ca65.py:1719-1912` (`export_song_bank_bytecode` — no channel-presence check anywhere in the method); sole enforcement is `main.py:984` (`_song_has_dpcm_events`) called from the `_songs_for_build` generator at `main.py:1065-1070`
- **Status**: Existing — reported as EXP-2026-08-07-2 (`AUDIT_EXPORTERS_2026-08-07.md`) and re-carried as EXP-2026-08-21-4 (`AUDIT_EXPORTERS_2026-08-21.md`); re-verified today against current code (this session's own `394cddb` commit rewrote this method's surrounding loop and still did not add the check); **no GitHub issue has ever been filed** across three audit cycles (0 open issues at last snapshot; no closed match for "dpcm" + "jukebox"/"song bank" in title)
- **Description**: Unchanged in substance from the prior two reports: calling the
  public `export_song_bank_bytecode` directly with DPCM-bearing frames (bypassing
  `main.py`'s `run_song_build`) silently emits a real `song{i}_dpcm_sequence` with
  trigger bytes, while no `DpcmPacker` runs anywhere in the jukebox export path — so
  the engine indexes the project builder's 1-byte stub `dpcm_*_table`s past their end
  and feeds garbage bank/addr/len straight into a live DMC DMA trigger ($4010-$4013).
  Every other hard invariant this method enforces (instrument count via
  `_register_instrument`, DPCM note range, bank budget, empty `songs`, and now this
  session's `song_count`/actual-yield mismatch) raises `ValueError` from inside the
  exporter itself; DPCM-channel presence is the one invariant that doesn't.
- **Evidence**: `grep -n "dpcm" exporter/exporter_ca65.py` inside
  `_build_song_bytecode`/`export_song_bank_bytecode` (`:1245-1912`) returns only the
  per-note range check (`:1353`) and the channel-name string used for iteration/
  table-key purposes — no `raise`/`ValueError` tied to DPCM channel presence.
- **Impact**: Confined today to non-`main.py` callers (library consumers, tests,
  future CLI paths — the CLI itself is protected by `_song_has_dpcm_events`), but it
  is the one jukebox invariant a direct API consumer can violate silently, with a
  failure mode of out-of-bounds table reads driving live DMA registers.
- **Related**: `#30/F-13`; EXP-2026-08-07-2 and EXP-2026-08-21-4 (identical prior
  reports); `#425` (the caller-side `_song_has_dpcm_events` check this relies on,
  fixed and holding).
- **Suggested Fix**: Raise `ValueError` from `export_song_bank_bytecode` (or
  `_build_song_bytecode`) for a non-empty `dpcm` channel in any song's frames,
  mirroring `_song_has_dpcm_events`'s check but owned by the exporter itself instead
  of only its one current caller.

### EXP-2026-08-23-3: `docs/AUDIO_BYTECODE_SPEC.md` still doesn't document the jukebox `song_table` format
- **Severity**: LOW
- **Dimension**: 5 (Bytecode-Spec Conformance) / 9 (Multi-Song Jukebox Export)
- **Spec ref**: `docs/AUDIO_BYTECODE_SPEC.md` (grep for `song_table`/`song_count`/`song_instrument_ptr`/`jukebox` across all 153 lines returns zero matches)
- **Location**: `exporter/exporter_ca65.py:1816-1852` (emits `song_table_ptr_lo/hi`, `song_table_bank`, `song_count`, `song_instrument_ptr_lo/hi`) vs. the unchanged spec doc
- **Status**: Existing — reported as EXP-2026-08-07-3, re-carried as EXP-2026-08-21-5; unchanged since; no GitHub issue filed
- **Description**: The `song_index*5 + channel` parallel-array layout and the
  per-song instrument-pointer table remain documented only in code
  docstrings/comments (`export_song_bank_bytecode`'s own docstring,
  `exporter_ca65.py:1745-1751`). The spec's §2.1 still shows only the single-song
  `channel_start_banks` example with no jukebox-mode counterpart.
- **Impact**: Doc-rot / drift risk only — the exporter and engine
  (`nes/audio_engine.asm`'s `load_song_streams_indexed`) were independently
  re-confirmed consistent with each other in this and the prior audit (stride 5,
  `SEQUENCE_CHANNELS` order).
- **Related**: EXP-2026-08-07-3, EXP-2026-08-21-5 (identical prior reports); `#83/EXP-07`
  (prior reconciliation of the same doc for a different gap); EXP-2026-08-23-1 (a
  second, separate gap in the same doc).
- **Suggested Fix**: Add a §2 subsection documenting the five jukebox symbols, the
  `*5` stride, and channel order.

### EXP-2026-08-23-4: Multi-song bank-overflow error still loses which song failed
- **Severity**: LOW
- **Dimension**: 9 (Multi-Song Jukebox Export)
- **Spec ref**: N/A (error-message quality)
- **Location**: `exporter/exporter_ca65.py:1556-1562` (the `ValueError` names `channel` and the bank number but no song), `:1810-1820` (the per-song loop — rewritten this session, `prefix` and a 0-based `songs_consumed` counter are both in scope but the loop still doesn't catch/re-raise `_build_song_bytecode`'s `ValueError` with either)
- **Status**: Existing — reported as EXP-2026-08-07-4, re-carried as EXP-2026-08-21-6; code touched by this session's `394cddb` (the loop itself was rewritten for laziness) but the underlying gap is unchanged; no GitHub issue filed
- **Description**: Unchanged in substance — a multi-song bank hitting the shared
  60-bank budget fails loudly and correctly (`ValueError`, atomic write means no
  partial `music.asm`), but the message names only the channel that tipped it over,
  forcing the user to bisect the bank to find the oversized song. This session's
  refactor of the surrounding loop (for `#505`/`#506`) actually makes a fix cheaper
  than before: `songs_consumed` is now a running 0-based song index already
  maintained in the loop for the other new validation check, so a `try/except`
  wrapping the `_build_song_bytecode` call has both `prefix` and `songs_consumed`
  available to prepend to the error without any new bookkeeping.
- **Evidence**: `exporter_ca65.py:1811` (`for prefix, song in zip(song_labels,
  songs):`) has no `try`/`except` around the `_build_song_bytecode` call at `:1812`.
- **Impact**: Unchanged from prior reports — correct failure, poor diagnostics only.
- **Related**: EXP-2026-08-07-4, EXP-2026-08-21-6 (identical prior reports); `#505`/`#506`
  (this session's fix that happens to leave the loop in a cheaper-to-fix shape).
- **Suggested Fix**: Wrap the `_build_song_bytecode` call in a `try/except ValueError
  as e: raise ValueError(f"song index {songs_consumed} ('{prefix.rstrip('_')}'): {e}")
  from e`.

### EXP-2026-08-23-5: `export_song_bank_bytecode`'s new `song_count` guard only catches a lazy iterable yielding *fewer* songs than declared, not *more*
- **Severity**: LOW
- **Dimension**: 1 (CA65 Well-Formedness & Builder Compatibility — API contract hardening on newly-changed code)
- **Spec ref**: N/A (defensive API contract, not an assembly/hardware conformance gap)
- **Location**: `exporter/exporter_ca65.py:1810-1830` (the per-song loop, added this session for `#505`/`#506`)
- **Status**: NEW (self-review of this session's own `394cddb` commit — not present before this session, since `songs` was previously always a materialized `list` and `song_count` was always `len(songs)`, making this class of mismatch structurally impossible)
- **Description**: `zip(song_labels, songs)` stops as soon as the shorter of the two
  iterables is exhausted. The `songs_consumed != song_count` check added this session
  correctly catches a lazy `songs` iterable that yields *fewer* items than its
  declared `song_count` (raises `ValueError`). It does not catch the opposite: a
  `songs` generator that yields *more* items than `song_count` declares. In that case
  `zip` simply stops after `song_count` items, silently discarding the extra songs
  with no error or warning — every `.export`/`song_table`/`song_instrument_ptr` line
  was already sized for the declared `song_count`, so nothing downstream breaks, but
  the caller's remaining songs vanish from the ROM with no signal.
- **Evidence**: `exporter_ca65.py:1811` `for prefix, song in zip(song_labels,
  songs): ... songs_consumed += 1`, followed at `:1826-1830` by a check that only
  fires on `songs_consumed != song_count` — true in the "fewer" direction, but a
  `songs` generator with more than `song_count` items also produces
  `songs_consumed == song_count` (zip stopped it there), so the check can't
  distinguish "exactly right" from "more available but not asked for."
  `main.py`'s sole call site is unaffected (`song_count = len(ordered_names)` always
  matches exactly what `_songs_for_build()` yields).
- **Impact**: No live caller can trigger this today — `main.py`'s `run_song_build` is
  the only call site in the codebase and always passes a matching count. Purely a
  latent API-contract gap for a future caller.
- **Related**: `#505`/`#506` (the commit that introduced both the lazy-iterable
  support and this asymmetry).
- **Suggested Fix**: After the loop, attempt one more `next(iter(songs), _SENTINEL)`
  (or check the underlying iterator directly, since `songs` may not be a fresh
  iterator after `zip` partially consumed it — simplest: iterate manually with
  `iter(songs)` instead of relying on `zip`'s early stop, so an (N+1)th item can be
  detected) and raise the same `song_count` mismatch `ValueError` if one exists.

## Cross-Dimension Dedup

EXP-2026-08-23-2 (D9) and EXP-2026-08-23-4 (D9) both live in
`export_song_bank_bytecode`'s per-song loop but are independent root causes (a
missing channel-presence guard vs. a missing error-context wrap) — reported
separately per the shared protocol rather than merged. EXP-2026-08-23-1 and
EXP-2026-08-23-3 are both spec-doc gaps in the same file (`docs/AUDIO_BYTECODE_SPEC.md`)
but cover unrelated sections (§3 command table vs. missing §2 jukebox subsection) —
reported separately since fixing one doesn't touch the other.

## Suggested next step

```
/audit-publish docs/audits/AUDIT_EXPORTERS_2026-08-23.md
```
