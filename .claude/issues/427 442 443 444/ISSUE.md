# Issues 427, 442, 443, 444

## #427 — PIPE-2026-08-21-5: `import_bank` doesn't validate per-song entries

**Severity:** MEDIUM · **Domain:** pipeline

**Location:** `nes/song_bank.py:200-227` (`SongBank.import_bank`, bank-level guard only);
consumers: `main.py:953-954` (`run_song_build`'s sort key), `main.py:844-853`
(`run_song_list`'s print loop), `main.py:962-963` (`song_data.get('midi_path')`, already
defensive)

#220/SAFE-09 added a bank-level guard so a corrupt/hand-edited bank fails cleanly, but the
guard stops one level up: `data['songs']` values are stored as-is with no per-song-entry
validation. A song entry missing `'metadata'` (or non-dict, or missing `'bank'`) raises an
uncaught `KeyError`/`TypeError` inside `run_song_build`'s sort key (outside the `try` that
wraps only `import_bank`) or `run_song_list`'s print loop — a raw traceback, the exact
presentation #220 was closing off.

Banks written by `export_bank` always carry the keys — this needs a hand-edited/truncated/
version-drifted bank file. Defense-in-depth, not a mainline break.

**Suggested fix:** in `import_bank`, validate each song entry is a dict with a dict
`'metadata'` (raising the same `ValueError` style already used), or make the three consumer
sites use `.get()` with defaults.

---

## #442 — EXP-2026-08-21-7: Volume macro bytes bypass reserved-byte encoding

**Severity:** LOW · **Domain:** exporters

**Location:** `exporter/exporter_ca65.py:1171` (`vol = frame_data.get('volume', 0)` — raw),
`:1270`/`:1286` (`vol_seq` appended unencoded, unlike `pitch`/`arp` which route through
`_encode_macro_offset`), `:1343` (`.byte` emission with no mask/clamp)

Every in-pipeline producer clamps volume to 0-15, but the step-by-step CLI accepts a
user-editable frames JSON with no mask applied. A frame with `volume: 255` exports
`macro_vol_1: .byte $FF, $FF` — the first data byte IS the end-of-macro control byte, so
`EVAL_MACRO` reads end-at-step-0 and plays the null default (15) instead of the intended
value; 16-253 emit and are silently masked `& $0F` by the engine at write time. No crash,
but macro semantics silently change for malformed input the exporter elsewhere rejects
loudly.

**Suggested fix:** clamp/mask `vol` to 0-15 at collection time (matching spec's stated
domain), or raise like the DPCM range guard does.

---

## #443 — EXP-2026-08-21-8: `fetch_sequence_byte` comment claims wrong bank window

**Severity:** LOW · **Domain:** exporters (documentation)

**Location:** `nes/project_builder.py:171` ("Swaps the sequence bank into $8000-$9FFF, reads
1 byte") vs `:176-187` (`lda #$47` selects R7; pointer high byte `and #$1F / ora #$A0` — the
`$A000` window)

The routine's header comment describes the wrong 8KB window. Code is correct (R7 maps
`$A000-$BFFF` per `docs/MAPPER_MMC3_REFERENCE.md`), but the comment invites the kind of
misread that produced past bank-window bugs (#388-class), and contradicts the correct
"fixed `$8000` bank" comments 40 lines away in the same generated file.

**Suggested fix:** `s/$8000-$9FFF/$A000-$BFFF (R7)/` in the template comment.

---

## #444 — EXP-2026-08-21-9: `export_direct_frames` summary overstates byte count

**Severity:** LOW · **Domain:** exporters

**Location:** `exporter/exporter_ca65.py:1002` (`total_bytes = (max_frame + 1) * 4 *
len(all_channels)`)

The end-of-export summary multiplies frames × 4 × channel-count, overstating emitted RODATA
whenever noise (3 tables) or dpcm (1 table) is active — for a 5-channel song it reports 20
bytes/frame where 16 are emitted (+25%). `estimate_direct_export_size` already has the
correct per-channel accounting (pulse/triangle 4, noise 3, dpcm 1); only the human-facing
print still uses the old math. Nothing downstream consumes the printed number.

**Suggested fix:** reuse `estimate_direct_export_size(frames)` (or its `bytes_per_frame`
map) for the summary.
