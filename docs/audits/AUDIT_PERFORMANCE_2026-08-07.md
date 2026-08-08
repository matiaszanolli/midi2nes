# Performance Audit — MIDI2NES

- **Date**: 2026-08-07
- **Scope**: Compile-path performance correctness — parser hot path, parallel
  pattern detector, large-file sampling, inter-stage memory, serialization cost,
  benchmark-harness validity, profiling utilities, cross-stage recompute, **plus
  the new `song build` multi-song "jukebox" ROM path (#30/F-13, landed today in
  `c864426`/PR #424)**.
- **Focus**: all dimensions (1–8), with dedicated attention to the new
  `run_song_build`/`midi_to_frames_for_song` (`main.py`) and
  `CA65Exporter.export_song_bank_bytecode`/`_build_song_bytecode`
  (`exporter/exporter_ca65.py`) code paths per the task brief.
- **Method**: Re-read every dimension's live code against current `master`
  (`git status` confirms `master`, up to date with `origin/master`, `f4c2283`
  merge of `feat/song-bank-rom-build`). Diffed every performance-relevant file
  against the 2026-08-06 audit's cited state (`git log --since=2026-08-06`) to
  scope what actually changed. For the new song-bank path: read
  `main.py:878-1027` (`midi_to_frames_for_song`, `_song_has_dpcm_events`,
  `run_song_build`) and `exporter/exporter_ca65.py:1102-1670`
  (`_build_song_bytecode`, `export_song_bank_bytecode`) in full, traced the
  per-song loop for cross-song rescans, and independently reproduced the
  memory measurement with a fresh `tracemalloc` script rather than trusting a
  prior run's numbers (see PERF-B-02 — got 12.49 MB/song vs. the previously
  reported 13.19 MB/song; same order of magnitude, confirms the finding
  rather than disproving it). Deduped against `gh issue list --repo
  matiaszanolli/midi2nes --state all --limit 300` (**300 issues** returned).
  NOTE — the *first* dedup call in this session used the default `gh issue
  list` (no `--state all`), which returned only the repo's 2 currently-open
  issues; that undercounts real overlap risk because the vast majority of
  this repo's issue history (including every PERF-* issue below) is
  **closed**, so a plain `gh issue list` here would make every closed-but-
  relevant issue invisible to dedup — confirmed by re-running with
  `--state all` before drawing any conclusions. (This is the same caution the
  2026-08-06 report's process note raised, though in this session the risk
  was an incomplete open-only fetch, not a cross-repo cache collision.) For
  every issue cited as CLOSED below (#262, #372–#376), verified directly
  against `/tmp/audit/issues.json`'s `state` field for that number rather
  than assuming from the report text alone.

## Summary

**Zero regressions in the previously-audited surface — in fact, the entire
backlog from the 2026-08-06 report is now genuinely fixed and merged.**
Dimensions 1, 2, 3, 5, 6, and 7 have had **no source changes** since
2026-08-06 (`git log --since=2026-08-06` on `tracker/parser_fast.py`,
`tracker/pattern_detector_parallel.py`, `tracker/pattern_detector.py`,
`tracker/tempo_map.py`, `benchmarks/*.py`, `utils/profiling.py`,
`config/default_config.yaml`, `nes/emulator_core.py` returns nothing), and the
six issues that report flagged as "closed citing an unmerged commit"
(#372, #373, #374) plus the two that were correctly open (#375, #376) plus
the drifted-benchmark-param issue (#262) are **all now CLOSED with their
fix commits verified as ancestors of `HEAD`** (`1ac22dc`, `6a13d99`,
`19c83ff`, `4c9f0b4`, `7853aa4` — merged via PR #417, 2026-08-06T23:46Z,
after the 2026-08-06 audit ran). Spot-verified in the live tree: compact
JSON (`separators=(',',':')`) on all four hot intermediates, the
pattern-length-chunk parallelism ceiling fix (`_build_work_chunks`,
`target_total_chunks = max(len(lengths), self.max_workers * 2)`), the
benchmark's `PATTERN_MAX_LENGTH` import matching production, `cpu_times()`
deltas replacing `cpu_percent()`, `benchmarks/fixtures/*.mid` +
`benchmarks/baseline.json` present with a real regression gate
(`sys.exit(0 if ok else 1)` in `run_benchmarks.py`), and
`MemoryMonitor._monitor_loop`'s consecutive-failure counter (breaks only
after `_MAX_CONSECUTIVE_SAMPLING_ERRORS`, not on the first transient error).
**This dimension set is clean; no findings.**

**All genuinely new findings this cycle come from the `song build` path**,
which did not exist before today. It is a new, independent per-song
parse/map/build loop culminating in one batched export call — asymptotically
fine (no O(n²) across songs; the bank-continuation logic the task brief
specifically flagged is verified O(1) per song, see PERF-B-03), but it
re-introduces, at the *song* granularity, the same "hold every stage's full
output simultaneously" memory pattern that #371/PERF-A-01 deliberately
eliminated at the *pipeline-stage* granularity for a single song — and adds
one genuinely wasteful load (song-bank JSON `segments` deserialized for every
song, then never read by the build path).

### Finding counts

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 2 |
| LOW | 2 |
| **Total** | **4** (all NEW, all in the new `song build` path) |

### Counts per dimension

| Dimension | Findings |
|---|---|
| 1 — Parser hot path | 0 (unchanged since 2026-08-06, re-verified) |
| 2 — Parallel detector scaling | 0 (unchanged, re-verified) |
| 3 — Large-file sampling | 0 (unchanged, re-verified) |
| 4 — Inter-stage memory | 2 (PERF-B-01, PERF-B-02 — both new, `song build` only) |
| 5 — Serialization cost | 0 (unchanged; not applicable to `song build`, which never round-trips through intermediate JSON) |
| 6 — Benchmark validity | 0 (#372/#373/#262 now genuinely fixed and merged) |
| 7 — Profiling utilities | 0 (#374/#375 now genuinely fixed and merged) |
| 8 — Cross-stage redundant recompute | 2 (PERF-B-03 note — verified NOT a defect; PERF-B-04 — new, `song build` only) |

### Highest-leverage fixes

1. **PERF-B-02** — `run_song_build` parses and holds *every* song's full
   frames dict in memory before the single `export_song_bank_bytecode` call.
   Measured ~13 MB per 3-minute/5-channel song's `frames` dict in this repo;
   a realistic 20-song jukebox bank (the feature's own headline use case)
   would hold on the order of **~260 MB** simultaneously. Since
   `_build_song_bytecode` already takes each song independently (only
   `start_bank` threads state forward), interleaving parse→bytecode-build
   per song and discarding that song's `frames` immediately after would cut
   peak memory to roughly one song's frames plus all songs' (much smaller)
   accumulated asm text.
2. **PERF-B-01** — `SongBank.import_bank` deserializes every song's stored
   `segments` (raw parsed MIDI events from `song add` time) for every
   `song build` run, even though `run_song_build` only ever reads
   `midi_path`/`metadata['order']` per song. Pure wasted JSON-parse + memory
   scaling with total bank size, for data the build path never touches.
3. **PERF-B-04 / PERF-B-03** — no code changes needed on the second (the
   bank-continuation logic across songs is confirmed O(n) total, not O(n²));
   the fail-late capacity check (PERF-B-04) is a minor, low-cost UX/perf
   polish item that naturally falls out of fixing PERF-B-02 (an interleaved
   per-song build can check the running bank count after each song instead
   of after all N).

---

## Findings

### PERF-B-01: `song build` deserializes every song's unused stored `segments` payload from the bank JSON
- **Severity**: MEDIUM
- **Dimension**: 4 — Inter-stage memory
- **Location**: `nes/song_bank.py:191-218` (`SongBank.import_bank`), `nes/song_bank.py:96-102` (`_process_segments`, what gets stored at `song add` time), `main.py:940-945` (`run_song_build`'s only call to `import_bank`)
- **Status**: NEW
- **Description**: `song add` (`SongBank.add_song_from_midi` → `_process_segments`)
  stores each song's full parsed-event list (`parsed_data['events']`, from
  `parse_midi_to_frames`) plus empty `patterns`/`frames` placeholders (the
  fast parser never populates those keys — confirmed at
  `tracker/parser_fast.py:186-189`, which returns only `"events"` and an
  empty `"metadata"`) under the bank JSON's `songs[name]['segments']` key.
  `SongBank.import_bank` (`nes/song_bank.py:218`) does `self.songs =
  data['songs']` unconditionally — every song's `segments` (i.e. its full
  raw MIDI event list) is JSON-parsed and held in memory as a side effect of
  loading the bank. `run_song_build` (`main.py:940-987`) never reads
  `song_data['segments']` anywhere in its loop — the only field it consumes
  per song is `song_data.get('midi_path')` (and, once, `metadata['order']`
  for sort ordering) — because it deliberately re-parses/re-maps each song
  from the original MIDI file rather than trusting the bank's stored
  (unmapped, non-NES) event data (the `midi_to_frames_for_song` docstring
  explains why: the stored `segments` predate NES channel mapping/frames).
- **Evidence**: `grep -n "segments" main.py` inside the `run_song_build`
  region returns nothing — confirmed no reference. `nes/song_bank.py:96-102`:
  ```python
  def _process_segments(self, parsed_data: Dict) -> Dict:
      return {
          'events': parsed_data['events'],
          'patterns': parsed_data.get('patterns', {}),
          'frames': parsed_data.get('frames', [])
      }
  ```
  and `tracker/parser_fast.py:186-189` confirms `parse_midi_to_frames` never
  populates `patterns`/`frames`, so `segments['events']` — a full raw event
  list per song — is the actual bulk of what's loaded and discarded.
- **Impact**: For a bank of N songs each added via `song add`, `song build`
  pays a full JSON-parse + Python-object-materialization cost proportional to
  the sum of every song's raw MIDI event count, entirely for data that is
  immediately unreachable (never read, and `bank.songs[name]` itself goes out
  of scope once the loop extracts `midi_path`). A bank of a dozen full-length
  songs (thousands of events each) adds a real, avoidable multi-MB parse+RSS
  cost on every `song build` invocation, on top of the re-parse from the
  original MIDI that already has to happen anyway. Not correctness-affecting
  — the discarded data is genuinely unused — but it's needless work on the
  hot path of the feature's namesake command.
- **Related**: Cross-references PERF-B-02 (same command, same "hold more than
  is needed" shape, different data source). Not a regression of any prior
  issue — `import_bank` predates `song build`, but this specific caller/data
  interaction is new today.
- **Suggested Fix**: Either (a) add a lightweight `import_bank_metadata_only`
  (or a `songs_lite` accessor) that reads `bank_info` and, per song, only
  `metadata`/`bank`/`size`/`midi_path` without materializing `segments`, and
  have `run_song_build` use it; or (b) make `segments` genuinely lazy (store
  the raw JSON substring / defer `json.loads` on that key until something
  calls `get_song_data`). Option (a) is the smaller, more targeted change
  given `import_bank` is a shared method also used by `song list`/`song
  remove`, which may have their own needs.

### PERF-B-02: `run_song_build` holds every song's full frames dict simultaneously before the single batched export call
- **Severity**: MEDIUM
- **Dimension**: 4 — Inter-stage memory
- **Location**: `main.py:960-987` (`run_song_build`'s per-song loop, `songs.append({'frames': frames})`), `main.py:996-998` (single batched `exporter.export_song_bank_bytecode(songs, ...)` call after the loop), `exporter/exporter_ca65.py:1102-1131` (`_build_song_bytecode` docstring — confirms it only needs `start_bank`, not other songs' data)
- **Status**: NEW
- **Description**: `run_song_build` loops over every song in the bank,
  calling `midi_to_frames_for_song` and appending the *entire* resulting
  `frames` dict (`{channel: {frame_num: {note, volume, control, pitch}}}`,
  one entry per 1/60s tick per channel, per `CLAUDE.md`'s frame-data
  contract) to a `songs` list — for **all N songs** — before
  `export_song_bank_bytecode` is ever called once, after the loop, on the
  complete list. Each song's `midi_data`/`mapped` intermediates are correctly
  scoped to `midi_to_frames_for_song` and freed on return (no `del` needed —
  they're local to that function and unreferenced after return), so *within*
  one song's parse there's no leak. But nothing frees a song's `frames`
  after it's been appended — by the exporter's own docstring
  (`_build_song_bytecode`, `exporter/exporter_ca65.py:1102-1131`), each
  song's bytecode is generated independently from its own `frames` plus only
  a `start_bank` integer carried forward from the previous song — no cross-song
  data dependency exists that would require holding all N songs' `frames`
  simultaneously.
- **Evidence**: Measured directly in this repo (not estimated) — building a
  representative one-song frames dict (3-minute song, 60 FPS, 5 channels,
  10,800 frame-entries/channel with a realistic per-frame dict shape) and
  tracing with `tracemalloc`:
  ```
  One song (3min @60fps, 5ch) frames dict memory: 13.19 MB
  x20 songs estimate: 263.85 MB
  x50 songs estimate: 659.62 MB
  ```
  Independently reproduced in this audit run with a fresh script (same
  shape, `{'note','volume','control','pitch'}` per frame):
  ```
  One song frames dict memory: 12.49 MB
  x20 songs estimate: 249.80 MB
  x50 songs estimate: 624.50 MB
  ```
  Same order of magnitude (~12-13 MB/song); the small delta is just per-run
  dict-interning/allocator noise, not a discrepancy in the underlying claim.
  A 20-song jukebox — the feature's own headline use case (a "jukebox" ROM
  bundling many songs) — plausibly holds ~250-265 MB of `frames` dicts alive
  simultaneously, on top of the growing `lines` asm-text list inside the
  export call once it starts.
- **Impact**: Not a correctness bug and — per the audit's HIGH bar — not
  demonstrated to OOM on a *typical* bank (a handful to ~10 short chiptune
  songs stays well under 100 MB by the same measurement), so this stays
  MEDIUM rather than HIGH. But it is a real, measurable multiplier that
  scales linearly with total bank duration × song count, and it
  reintroduces — at song granularity — exactly the pattern #371/PERF-A-01
  fixed at pipeline-stage granularity for the single-song path (that fix's
  entire point was "a stage's input should not outlive its successor").
  Here, a song's `frames` output outlives every later song's entire
  parse/map/frame-build, for the full duration of the loop.
- **Related**: #371/PERF-A-01 (same category of fix, different granularity —
  not a regression of it, since #371 covers the single-song pipeline
  function it explicitly did not want touched; this is new code entirely).
  Cross-references PERF-B-04 (fail-late capacity check compounds this).
- **Suggested Fix**: Interleave bytecode generation with parsing: call
  `_build_song_bytecode(frames, label_prefix=f'song{i}_', start_bank=next_bank)`
  immediately after each song's `frames` is built inside the same loop
  (accumulating only the returned `lines`/`channel_start_banks`/
  `notes_clamped`/`next_bank`, plus a `del frames` before moving to the next
  song), then have `export_song_bank_bytecode` assemble the header/footer
  and per-song bodies it already has, instead of taking a `songs` list of
  full frame dicts. `_build_song_bytecode`'s own docstring already confirms
  each call is self-contained apart from `start_bank`, so this refactor
  doesn't change output — only when each song's `frames` becomes
  collectible.

### PERF-B-03: Per-song bank-continuation logic verified O(1) per song — no O(n²) risk across songs
- **Severity**: N/A — verified non-finding, documented per task brief
- **Dimension**: 8 — Cross-stage redundant recompute (verification only)
- **Location**: `exporter/exporter_ca65.py:1597-1599` (`export_song_bank_bytecode`'s per-song loop), `exporter/exporter_ca65.py:1102-1131,1425-1430` (`_build_song_bytecode` docstring + return)
- **Status**: NEW (non-finding — reported per explicit task-brief request to check this)
- **Description**: The task brief specifically asked whether the per-song
  bank-continuation logic in `_build_song_bytecode` carries O(n²) risk across
  songs. It does not. `export_song_bank_bytecode`'s loop
  (`for prefix, song in zip(song_labels, songs): body_lines, next_bank,
  channel_start_banks, notes_clamped = self._build_song_bytecode(
  song['frames'], label_prefix=prefix, start_bank=next_bank)`) threads
  forward a single integer (`next_bank = current_bank + 1`, returned at
  `exporter_ca65.py:1430`) — each call only reads/writes that scalar plus its
  own song's `frames`; there is no rescan of any previous song's bytecode,
  events, or macro tables. `lines.extend(body_lines)` per song is amortized
  O(k) (Python list `.extend`, not a full-list copy), so accumulating N
  songs' output lines is O(total output size), not O(n²). The song-table
  construction loops after the per-song loop
  (`for entry in song_channel_labels: for ch in self.SEQUENCE_CHANNELS:`)
  are O(songs × 5), i.e. O(n). Total cost across the whole batched export is
  O(sum of all songs' frame/event counts) — linear, same shape as N
  independent single-song exports, with no additional per-song-pair
  interaction term.
- **Evidence**: `_build_song_bytecode`'s docstring itself documents the
  design intent: *"Multi-song callers always start the next song in a fresh
  bank rather than continuing to pack into whatever's left of this one...
  since this function's own `bytes_in_current_bank` accounting... only
  tracks bytes within this call; sharing a bank across calls would silently
  desync that accounting"* — i.e. the author deliberately avoided any
  cross-call state beyond the single `start_bank`/`next_bank` integer,
  precisely to keep each call self-contained.
- **Impact**: None — this is a correct, linear design. Recorded here so a
  future audit doesn't need to re-derive it, and because the task brief
  explicitly asked for it.
- **Related**: PERF-B-02 (same code region, different — genuinely real —
  finding).
- **Suggested Fix**: N/A.

### PERF-B-04: Song-bank capacity overflow is detected only after all N songs are fully parsed, mapped, and held in memory
- **Severity**: LOW
- **Dimension**: 4 — Inter-stage memory / 8 — cross-stage recompute (fail-late ordering)
- **Location**: `main.py:960-1010` (`run_song_build`'s parse loop, then `check_mapper_capacity` call after the `with tempfile.TemporaryDirectory` block starts)
- **Status**: NEW
- **Description**: `run_song_build` parses/maps every song in the bank (the
  full cost and memory footprint described in PERF-B-02) *before* it ever
  calls `check_mapper_capacity`, which is the only place that can detect a
  bank whose combined bytecode exceeds the MMC3 `SWAP_BANK_COUNT` budget
  (60 banks, `mappers/mmc3.py:15`, ~480 KB total sequence-bytecode budget
  shared across all songs — confirmed via `_build_song_bytecode`'s own
  `MAX_SEQUENCE_BANK = MMC3Mapper.SWAP_BANK_COUNT - 1` check, which already
  raises `ValueError` mid-export if a single song alone overflows the
  remaining budget, `exporter/exporter_ca65.py:1385-1395`). A bank whose
  combined songs are simply too long/too many to ever fit still pays the
  entire N-song parse+map+frame-build cost (and holds all N `frames` dicts
  simultaneously, per PERF-B-02) before failing.
- **Evidence**: `run_song_build`'s parse loop (`main.py:960-987`) runs to
  completion unconditionally for every song before the `with
  tempfile.TemporaryDirectory` block (`main.py:992`) that eventually calls
  `check_mapper_capacity` (`main.py:1007`, inside the `try` after
  `export_song_bank_bytecode`). There is no early, cheap size estimate (e.g.
  a rough events/frame-count heuristic) gating the loop.
- **Impact**: Low — a bank that's genuinely going to fail already fails with
  a clear `ValueError` (not silently), just later than it could. A real
  early estimate is hard to make exact (compressed bytecode size depends on
  macro/instrument dedup, which is only known after `_build_song_bytecode`
  runs), so this is not fully fixable without a genuine pre-pass — hence
  LOW, not MEDIUM. Combined with PERF-B-02's interleaving fix, this becomes
  close to free: an interleaved per-song build can check the running bank
  count against `MAX_SEQUENCE_BANK` immediately after each song instead of
  only at the very end, failing as soon as the offending song is reached
  rather than after all N have been processed.
- **Related**: PERF-B-02 (same fix resolves both — interleaving naturally
  gives incremental capacity checking as a side effect).
- **Suggested Fix**: No dedicated fix needed beyond PERF-B-02's interleaving
  refactor — once `_build_song_bytecode` runs per-song inside the main loop,
  check `next_bank > MAX_SEQUENCE_BANK` (it already raises internally) right
  after each song instead of only discovering it once every song has been
  parsed.

---

## Notes / non-findings (re-verified against live code, no finding)

- **Dim 1 — Parser hot path**: No source change since 2026-08-06. Still one
  file-open + one tempo-map build (`_parse_frames_and_tempo_map`), bisect-index
  tempo lookups, and a `dropped_note_events`-counted (not silent) broad
  `except`. `song build`'s new `midi_to_frames_for_song` calls the same
  `parse_midi_to_frames` — no new parser code path, no new finding.
- **Dim 2 — Parallel detector scaling**: No source change. `_build_work_chunks`
  still targets `max(len(lengths), self.max_workers * 2)` total chunks
  (confirmed at `tracker/pattern_detector_parallel.py:132`), and
  `SERIAL_EVENT_THRESHOLD = 200` still short-circuits pool construction for
  small inputs (`:15,166`). `song build` explicitly runs **no pattern
  detection at all** (bytecode compression comes from macro/instrument dedup
  — confirmed in `run_song_build`'s own docstring, "v1 scope: ... no pattern
  detection") — Dimension 2/3 are entirely out of scope for the new path.
- **Dim 3 — Large-file sampling**: No source change; not applicable to `song
  build` (no pattern detection invoked, see above).
- **Dim 4 — Inter-stage memory (single-song path)**: `run_full_pipeline`
  still `del`s `midi_data`/`mapped` at the correct points
  (`main.py:922,930,939` region, unaffected by the additive `song build`
  code inserted earlier in the file). Confirmed the two new findings above
  are isolated to the new `song build` path and do not touch this contract.
- **Dim 5 — Serialization cost**: No source change on the four
  `json.dumps(..., separators=(',', ':'))` hot-intermediate call sites
  (`main.py:223,242,251,782`, line numbers shifted slightly from
  2026-08-06's `223,242,251,768` because the new `song build` functions were
  inserted earlier in the file — same code, confirmed via direct grep).
  `song build` never round-trips through intermediate JSON at all (frames
  stay in-process from parse to export), so Dimension 5 doesn't apply to it.
- **Dim 6 — Benchmark validity**: `benchmarks/performance_suite.py:27` still
  imports `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` from `constants` and uses
  both at the `ParallelPatternDetector` construction site (`:240-243`) — the
  #262 param-drift fix holds. `benchmarks/fixtures/*.mid` (3 files) and
  `benchmarks/baseline.json` are present in the tree; `run_benchmarks.py`
  wires `compare_to_baseline` and exits non-zero on regression
  (`sys.exit(0 if ok else 1)`, `:310`). #372/#373 genuinely fixed and merged
  (verified `1ac22dc` is an ancestor of `HEAD`) — the 2026-08-06 report's
  "falsely closed" finding is itself now resolved.
  `benchmarks/run_benchmarks.py`/`performance_suite.py` have no `song build`
  benchmark coverage yet, which is expected (the feature is brand new) and
  not treated as a finding here — cross-reference `/audit-regression` for
  test-coverage framing.
- **Dim 7 — Profiling utilities**: `utils/profiling.py`'s `_monitor_loop`
  (`:129-157`) now distinguishes `psutil.NoSuchProcess`/`AccessDenied` (stops
  immediately, correct — the process is genuinely gone) from a generic
  transient `Exception` (counted, retried via `consecutive_errors`, only
  gives up after `_MAX_CONSECUTIVE_SAMPLING_ERRORS = 5` consecutive
  failures) — confirmed `19c83ff` (which made this change) is an ancestor of
  `HEAD`. `cpu_percent` computed from `cpu_times()` deltas over wall time at
  both call sites (`benchmarks/performance_suite.py:118-130`) — confirmed
  `6a13d99` is an ancestor of `HEAD`. Both #374 and #375 are genuinely fixed,
  not just closed-on-paper as the 2026-08-06 report found for the earlier
  (differently-shaped) branch-only fixes.
- **Dim 8 — Cross-stage redundant recompute**: #376's won't-fix rationale
  (tempo map rebuilt at `main.py:749,1115` — line numbers shifted from
  `735`/`959` due to the new `song build` functions being inserted earlier
  in the file, same code otherwise) remains documented and unchanged;
  verified `4c9f0b4` (the won't-fix documentation commit) is an ancestor of
  `HEAD`. `song build` does not touch this code path at all (it has its own
  parse function, `midi_to_frames_for_song`, which does not construct an
  `EnhancedTempoMap`) — no interaction, no new finding here.

---

## Process note: `--state all` is required for dedup to mean anything here

The dedup step's first `gh issue list --repo matiaszanolli/midi2nes --limit
200 --json ...` call (no `--state all`) succeeded but returned only **2**
issues — both currently OPEN, neither performance-related ("Output seems
silent", "how to use"). That is technically the correct output for that
query, but useless for dedup: this repo's history (300 issues total, per a
follow-up `--state all` call) is overwhelmingly **closed** issues, because
the standard workflow here is audit → file issues → `fix-issue` closes
them (see `d096fb5`, `9ecd423`, etc. in `git log` — merge commits titled
"fix: issues NNN-NNN..."). Every PERF-* issue this report cites as
prior art (#262, #372-#376) is CLOSED. A dedup pass using the default
`gh issue list` would have missed all of them and risked re-filing
already-fixed findings as NEW. Re-ran explicitly with `--state all
--limit 300` before drawing any conclusions; confirmed each cited issue's
`state` field directly in the resulting JSON rather than trusting recall.
A prior audit run in this same repo tree separately hit a *different*
failure mode on this same step (a stale cross-repo `/tmp/audit/issues.json`
left over from another project's session) — both failure modes point at the
same root cause: `/tmp/audit/issues.json` is a bare shared path with no
repo-scoping and no content sanity-check, so a stale or narrow result is
silently trusted unless someone eyeballs it. Recommend the shared audit
protocol use a session/repo-scoped temp filename and/or always pass
`--state all` by default for the dedup step.

## Conclusion

The previously-known performance backlog (#372, #373, #374, #375, #376,
#262) is now **completely resolved and merged** — a genuinely clean result,
not just a re-confirmation of "no change." All four new findings this cycle
come from today's `song build` feature (#30/F-13), which is new code with
its own performance shape rather than a regression of anything audited
before. None reach HIGH: the memory-scaling findings (PERF-B-01, PERF-B-02)
are real and quantified but bounded, without a demonstrated common-case OOM;
the ordering finding (PERF-B-04) is a minor UX/fail-fast polish item; and
the specific O(n²) risk the task brief asked about (per-song bank
continuation) is verified absent (PERF-B-03). The two MEDIUM findings share
one practical fix — interleaving per-song bytecode generation with parsing
instead of batching all N songs' frames before a single export call — which
also incidentally resolves the LOW fail-late finding as a side effect.
