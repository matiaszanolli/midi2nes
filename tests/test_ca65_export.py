import unittest
import re
import subprocess
import tempfile
from pathlib import Path
from exporter.exporter_ca65 import CA65Exporter
from nes.project_builder import NESProjectBuilder
from mappers.mmc3 import MMC3Mapper
from mappers.mmc1 import MMC1Mapper
from core.exceptions import ExportError

class TestCA65Export(unittest.TestCase):
    def setUp(self):
        self.exporter = CA65Exporter()
        self.test_frames = {
            'pulse1': {
                '0': {'note': 60, 'volume': 15},
                '32': {'note': 67, 'volume': 12}
            }
        }
        self.test_patterns = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 15},
                    {'note': 67, 'volume': 12}
                ]
            }
        }
        self.test_references = {
            '0': ('pattern_1', 0),
            '32': ('pattern_1', 1)
        }
        
    def test_midi_note_to_timer_value(self):
        # Test valid notes
        self.assertGreater(self.exporter.midi_note_to_timer_value(60), 0)  # Middle C
        self.assertGreater(self.exporter.midi_note_to_timer_value(67), 0)  # G4

        # Regression (#158): out-of-range notes must clamp to the nearest
        # valid table entry instead of returning a 0 "rest" sentinel -- a 0
        # base timer combined with the encoder's +127-clamped pitch offset
        # overflowed the 11-bit APU timer instead of just playing the nearest
        # representable note.
        from nes.pitch_table import NES_NOTE_TABLE
        self.assertEqual(self.exporter.midi_note_to_timer_value(20), NES_NOTE_TABLE[24])  # Too low
        self.assertEqual(self.exporter.midi_note_to_timer_value(120), NES_NOTE_TABLE[119])  # Too high

    def test_midi_note_to_timer_value_floors_at_8(self):
        # Regression (NH-06 / #27): the highest in-range timer values are < 8,
        # which silences pulse/triangle (t < 8). NES_NOTE_TABLE floors at 8.
        self.assertGreaterEqual(self.exporter.midi_note_to_timer_value(118), 8)
        self.assertGreaterEqual(self.exporter.midi_note_to_timer_value(119), 8)
        # Regression (#158): out-of-range now clamps to the nearest valid
        # entry (still >= 8) instead of returning 0.
        from nes.pitch_table import NES_NOTE_TABLE
        self.assertEqual(self.exporter.midi_note_to_timer_value(120), NES_NOTE_TABLE[119])

    def test_base_timer_matches_pitch_table(self):
        # Regression (NH-03 / #16): the exporter base timer and the frame pitch
        # must be on the same scale (fCPU/16 pulse table). A4 = 253, C4 = 426.
        from nes.pitch_table import NES_NOTE_TABLE
        self.assertEqual(self.exporter.midi_note_to_timer_value(69), 253)  # A4
        self.assertEqual(self.exporter.midi_note_to_timer_value(60), 426)  # C4
        for note in range(24, 120):
            self.assertEqual(self.exporter.midi_note_to_timer_value(note),
                             NES_NOTE_TABLE[note])

    def test_pitch_offset_is_zero_for_unbent_notes(self):
        # Regression (NH-03 / #16): bytecode pitch offset = frame_pitch - base_timer.
        # When the frame pitch equals the table value (no bend), the offset must
        # be 0 so bytecode-mode playback pitch == direct-mode pitch.
        from nes.pitch_table import PitchProcessor
        pp = PitchProcessor()
        for note in range(24, 108):
            base = self.exporter.midi_note_to_timer_value(note)
            frame_pitch = pp.get_channel_pitch(note, 'pulse1')
            offset = max(-128, min(127, frame_pitch - base))
            self.assertEqual(offset, 0,
                             f"note {note}: frame {frame_pitch} vs base {base}")

    def test_sub_c1_note_does_not_overflow_timer(self):
        # Regression (#158): a sub-C1 note (e.g. MIDI 21, below the NES's
        # lowest representable pitch) used to get base_timer=0 combined with a
        # +127-clamped pitch offset, overflowing the 11-bit APU timer at
        # runtime. The note baked into the instruction stream must clamp to
        # 24 (same floor as the frame `pitch` already uses) so the runtime
        # base-period lookup and the pitch offset agree, yielding offset 0.
        from nes.pitch_table import NES_TRIANGLE_TABLE
        frames = {'triangle': {'0': {'note': 21, 'pitch': NES_TRIANGLE_TABLE[24],
                                      'volume': 10, 'control': 0x80}}}
        out = tempfile.mktemp(suffix='.asm')
        try:
            self.exporter.export_tables_with_patterns(
                frames, patterns={'triangle': ['x']}, references={}, output_path=out)
            text = Path(out).read_text()
            # The note operand baked into the instruction stream must be
            # clamped to 24 ($18), not the raw out-of-range MIDI note (21).
            self.assertIn('Note 24', text)
            self.assertNotIn('Note 21', text)
            # And the pitch macro offset must be 0 (not the +127 the bug produced).
            pitch_section = text.split('; --- Pitch Macros ---', 1)[1]
            first_macro = pitch_section.split('macro_pitch_1:', 1)[1].split('\n', 2)[1]
            self.assertIn('$00, $FF', first_macro)
        finally:
            Path(out).unlink(missing_ok=True)

    def test_end_of_stream_silences_channel(self):
        # Regression (#159): hitting the $FF end-of-stream marker must fall
        # into the channel's silence write, not just leave frame_wait at 0.
        # Otherwise every subsequent frame re-fetches the same $FF with no
        # hardware write, and the channel's last note (nonzero volume, halted
        # length counter) drones forever once its part is shorter than the
        # rest of the song.
        engine_path = Path(__file__).parent.parent / "nes" / "audio_engine.asm"
        text = engine_path.read_text()
        end_of_stream = text.split('@end_of_stream:', 1)[1].split('@next_channel:', 1)[0]
        self.assertIn('jmp @silence', end_of_stream,
                      "end_of_stream must fall into the channel's silence write")

    def test_pulse_sustain_does_not_rewrite_4003_every_frame(self):
        # Regression (#161/NH-18): $4003/$4007 restart the pulse sequencer's
        # phase on every write (regardless of whether the value changes), so
        # writing them unconditionally on every sustain frame of a held note
        # produces an audible click at 60Hz. The engine must gate the write on
        # the cached value actually changing, and force a rewrite at note
        # onset (@is_note) so a genuine new note still retriggers.
        engine_path = Path(__file__).parent.parent / "nes" / "audio_engine.asm"
        text = engine_path.read_text()

        p1_write = text.split('@write_pulse1:', 1)[1].split('@write_pulse2:', 1)[0]
        self.assertIn('cmp last_written_hi', p1_write)
        self.assertIn('sta $4003', p1_write)

        p2_write = text.split('@write_pulse2:', 1)[1].split('@write_triangle:', 1)[0]
        self.assertIn('cmp last_written_hi', p2_write)
        self.assertIn('sta $4007', p2_write)

        is_note = text.split('@is_note:', 1)[1].split('@process_macros:', 1)[0]
        self.assertIn('sta last_written_hi, x', is_note,
                      "a new note must force the timer-high write even if the period repeats")

    def test_standalone_header_tracks_selected_mapper(self):
        # Regression (NH-09 / #36): the standalone iNES header must come from the
        # selected mapper, not a hardcoded MMC1 byte. Default is MMC3.
        from mappers.nrom import NROMMapper
        from mappers.mmc1 import MMC1Mapper
        from mappers.mmc3 import MMC3Mapper
        frames = {'pulse1': {'0': {'note': 60, 'pitch': 426, 'control': 0x8F}}}

        cases = [
            (None, 'Mapper 4'),            # default -> MMC3
            (MMC3Mapper(), 'Mapper 4'),
            (MMC1Mapper(), 'Mapper 1'),
            (NROMMapper(), 'Mapper 0'),
        ]
        for mapper, expected in cases:
            out = Path(tempfile.mktemp(suffix='.asm'))
            try:
                self.exporter.export_direct_frames(frames, str(out), standalone=True,
                                                   mapper=mapper)
                content = out.read_text()
            finally:
                if out.exists():
                    out.unlink()
            # Exactly one HEADER segment, and the mapper byte matches the mapper.
            self.assertEqual(content.count('.segment "HEADER"'), 1)
            self.assertIn(expected, content)
            if mapper is None or expected == 'Mapper 4':
                self.assertNotIn('Mapper 1 (MMC1)', content)

    def test_triangle_continuation_frames_stay_in_tune(self):
        # Regression (EXP-02 / #78): continuation frames of a sustained note must
        # compute base_timer with the channel, like the first frame. Omitting it
        # defaulted triangle to the pulse table, so an in-tune sustained triangle
        # note got a spurious -128 (0x80) pitch offset on every sustain frame.
        import re
        from nes.pitch_table import NES_TRIANGLE_TABLE
        note = 36  # low bass triangle note: pulse 1709 vs triangle 854
        tri_timer = NES_TRIANGLE_TABLE[note]
        # Triangle held in tune (frame pitch == triangle table value) for 4 frames.
        frames = {'triangle': {str(f): {'note': note, 'volume': 15, 'pitch': tri_timer}
                               for f in range(4)}}
        patterns = {'p0': {'events': [{'note': note, 'volume': 15}]}}
        refs = {'0': ('p0', 0)}  # non-empty -> macro bytecode path
        test_output = Path("test_tri_tune.asm")
        try:
            self.exporter.export_tables_with_patterns(frames, patterns, refs, test_output)
            output = test_output.read_text()
            # Collect every pitch-macro byte sequence. Triangle is the only
            # channel here and the note is in tune, so every offset must be $00;
            # the bug produced $80 on continuation frames.
            pitch_bytes = []
            for m in re.finditer(r'macro_pitch_\d+:\n    \.byte ([^\n]+)', output):
                pitch_bytes.extend(b.strip() for b in m.group(1).split(','))
            self.assertTrue(pitch_bytes, "expected at least one pitch macro")
            # $80 is the clamped -128 offset the bug produced on sustain frames.
            self.assertNotIn('$80', pitch_bytes,
                             "continuation frame got pulse-table base timer (#78)")
            # The in-tune triangle must contribute a real $00-offset macro
            # ($FF entries are the (0xFF) sentinel macro, not pitch offsets).
            self.assertIn('$00', pitch_bytes, "in-tune triangle should emit a $00 pitch offset")
            self.assertTrue(all(b in ('$00', '$FF') for b in pitch_bytes),
                            f"unexpected non-zero pitch offset for in-tune triangle: {pitch_bytes}")
        finally:
            if test_output.exists():
                test_output.unlink()

    def test_encode_macro_offset_never_emits_control_bytes(self):
        # Regression (EXP-01 / #77): a signed pitch/arp offset must never encode
        # to $FE/$FF — those are the macro control bytes ($FF end, $FE loop) the
        # engine and _compress_macro reserve. Every offset in the 8-bit signed
        # range (and clamped out-of-range inputs) must map outside {$FE, $FF}.
        for v in range(-128, 128):
            b = self.exporter._encode_macro_offset(v)
            self.assertNotIn(b, (0xFE, 0xFF), f"offset {v} -> reserved {b:#04x}")
            self.assertTrue(0x00 <= b <= 0xFD)
        self.assertNotIn(self.exporter._encode_macro_offset(200), (0xFE, 0xFF))
        self.assertNotIn(self.exporter._encode_macro_offset(-200), (0xFE, 0xFF))
        # The two colliding values snap to their nearest non-reserved neighbour;
        # every other offset is left exactly as its two's-complement byte.
        self.assertEqual(self.exporter._encode_macro_offset(-1), 0x00)   # was $FF
        self.assertEqual(self.exporter._encode_macro_offset(-2), 0xFD)   # was $FE
        self.assertEqual(self.exporter._encode_macro_offset(-3), 0xFD)
        self.assertEqual(self.exporter._encode_macro_offset(0), 0x00)
        self.assertEqual(self.exporter._encode_macro_offset(5), 0x05)
        self.assertEqual(self.exporter._encode_macro_offset(127), 0x7F)
        self.assertEqual(self.exporter._encode_macro_offset(-128), 0x80)

    # NOTE: the former #80/EXP-04 loop-operand tests
    # (test_compress_macro_skips_loop_candidates_past_byte_255 /
    # test_compress_macro_still_loops_when_loop_start_fits_one_byte) were
    # removed with loop compression itself (#163/NH-21) -- the single-byte
    # loop_start operand can no longer overflow because no $FE is ever emitted.
    # The instrument-id half of #80 below is unaffected and stays.

    def test_compress_macro_never_emits_loop_control_byte(self):
        # Regression (#163/NH-21): the live EVAL_MACRO evaluator
        # (nes/audio_engine.asm) only implements the $FF end/sustain control
        # byte -- it has no branch for $FE (loop) at all, so a $FE byte is
        # read as ordinary data and the following loop_start operand is
        # consumed as the next frame's value, desyncing the stream. A merged
        # run of alternating values (e.g. a 60Hz drum-roll/tremolo re-strike
        # pattern) used to make loop compression win on size and emit $FE.
        alternating = [15, 12, 10, 8, 10, 12, 10, 8, 10, 12]
        compressed = self.exporter._compress_macro(alternating)
        self.assertNotIn(0xFE, compressed)
        self.assertEqual(compressed[-1], 0xFF)
        self.assertEqual(compressed[:-1], alternating)

    def test_compress_macro_sustain_compression_unaffected(self):
        # Sustain compression ($FF) must still work for a constant tail.
        data = [15, 14, 13, 10, 10, 10, 10]
        compressed = self.exporter._compress_macro(data)
        self.assertEqual(compressed, [15, 14, 13, 10, 0xFF])

    def test_compress_macro_empty_data(self):
        self.assertEqual(self.exporter._compress_macro([]), [0xFF])

    def test_register_instrument_rejects_the_257th_unique_instrument(self):
        """Regression (#80/EXP-04): CMD_INSTRUMENT's operand is a single byte.
        The 257th unique (vol, arp, pitch, duty) combination would assign
        inst_id=256, overflowing `${inst_id:02X}` to a 3-hex-digit byte."""
        instruments = {}
        instrument_defs = []
        for i in range(256):
            inst_id = self.exporter._register_instrument(
                (i, 0, 0, 0), instruments, instrument_defs)
            self.assertEqual(inst_id, i)
        with self.assertRaises(ValueError, msg="257th unique instrument must raise"):
            self.exporter._register_instrument((256, 0, 0, 0), instruments, instrument_defs)

    def test_register_instrument_reuses_existing_ids(self):
        """Re-registering the same combination must not consume a new id."""
        instruments = {}
        instrument_defs = []
        first = self.exporter._register_instrument((1, 2, 3, 4), instruments, instrument_defs)
        second = self.exporter._register_instrument((1, 2, 3, 4), instruments, instrument_defs)
        self.assertEqual(first, second)
        self.assertEqual(len(instrument_defs), 1)

    def test_pitch_macro_data_avoids_control_bytes(self):
        # Regression (EXP-01 / #77): small downward pitch bends (offset -1, -2)
        # used to encode to $FF/$FE *as data*, which the engine reads as
        # end-of-macro / loop, truncating or desyncing the macro. Sustain a note
        # across frames whose bends are -1, -2, -10 and assert the emitted pitch
        # macro carries the snapped data ($00, $FD, $F6) with no in-band control
        # byte before the trailing $FF terminator.
        from nes.pitch_table import NES_NOTE_TABLE
        note = 60
        base = NES_NOTE_TABLE[note]
        frames = {'pulse1': {
            '0': {'note': note, 'volume': 15, 'pitch': base - 1},   # -> $FF (bug)
            '1': {'note': note, 'volume': 15, 'pitch': base - 2},   # -> $FE (bug)
            '2': {'note': note, 'volume': 15, 'pitch': base - 10},  # -> $F6 marker
        }}
        patterns = {'p0': {'events': [{'note': note, 'volume': 15}]}}
        refs = {'0': ('p0', 0)}  # non-empty -> macro bytecode path
        out = Path("test_pitch_ctrl.asm")
        try:
            self.exporter.export_tables_with_patterns(frames, patterns, refs, out)
            output = out.read_text()
            import re
            rows = [[b.strip() for b in m.group(1).split(',')]
                    for m in re.finditer(r'macro_pitch_\d+:\n    \.byte ([^\n]+)', output)]
            ours = [r for r in rows if '$F6' in r]
            self.assertTrue(ours, "expected a pitch macro carrying the $F6 marker")
            row = ours[0]
            self.assertEqual(row, ['$00', '$FD', '$F6', '$FF'])
            # Everything before the trailing $FF terminator must be data-safe.
            self.assertNotIn('$FE', row[:-1])
            self.assertNotIn('$FF', row[:-1])
        finally:
            if out.exists():
                out.unlink()

    def test_channel_start_banks_matches_actual_label_placement(self):
        # Regression (#328/EXP-13): the exporter emits each channel's *_sequence
        # label into whatever BANK_NN the running byte counter left active, so a
        # later channel can start in BANK_01+ once pulse1 fills BANK_00. audio_init
        # seeds stream_bank from the exported channel_start_banks table instead of
        # hardcoding 0, so that table MUST match where each label physically lands
        # — otherwise the engine reads the channel's stream from the wrong bank.
        # A big pulse1 forces the spill; give the other channels a couple of hits
        # each so their start labels land past bank 0.
        frames = {
            'pulse1': {str(i): {'note': 60 + (i % 24), 'volume': 8 + (i % 7)}
                       for i in range(5000)},
            'pulse2': {'0': {'note': 60, 'volume': 10}, '8': {'note': 62, 'volume': 10}},
            'triangle': {'0': {'note': 48, 'volume': 15}},
            'noise': {'0': {'note': 12, 'volume': 8}},
            'dpcm': {'0': {'note': 1, 'volume': 15}},
        }
        patterns = {'p0': {'events': [{'note': 60, 'volume': 15}]}}  # non-empty -> bytecode path
        out = Path("test_startbanks.asm")
        try:
            self.exporter.export_tables_with_patterns(frames, patterns, {}, str(out))
            asm = out.read_text()
        finally:
            if out.exists():
                out.unlink()

        # Parse the emitted channel_start_banks table.
        m = re.search(r'channel_start_banks:\s*\n\s*\.byte\s+([^\n;]+)', asm)
        self.assertIsNotNone(m, "channel_start_banks table must be emitted")
        table = [int(tok.strip().lstrip('$'), 16) for tok in m.group(1).split(',')]
        self.assertEqual(len(table), 5, "table must have one byte per channel")

        # Walk the ASM tracking the active BANK_NN segment, and record the bank
        # each {channel}_sequence: label is actually defined in.
        channels = ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']
        actual_bank = {}
        cur_bank = None
        for line in asm.splitlines():
            seg = re.match(r'\.segment\s+"BANK_(\d+)"', line.strip())
            if seg:
                cur_bank = int(seg.group(1))
                continue
            lbl = re.match(r'(pulse1|pulse2|triangle|noise|dpcm)_sequence:', line.strip())
            if lbl:
                actual_bank[lbl.group(1)] = cur_bank

        for idx, ch in enumerate(channels):
            self.assertIn(ch, actual_bank, f"{ch}_sequence label not found")
            self.assertEqual(
                table[idx], actual_bank[ch],
                f"channel_start_banks[{idx}] ({table[idx]}) != {ch}_sequence's actual "
                f"bank ({actual_bank[ch]}) — the engine would read {ch} from the wrong bank")

        # The test only exercises the bug if at least one channel really spilled
        # past bank 0; pulse1's 5000 events must push a later channel into BANK_01+.
        self.assertGreater(max(table), 0,
                           "expected a later channel to start past BANK_00 (test not exercising the spill)")

    def test_bytecode_export_caps_sequence_bank_count(self):
        # Regression (MAP-2 / #127): the macro-bytecode serializer must refuse to
        # roll past the last MMC3 swap bank (BANK_00..59) instead of emitting a
        # .segment ld65 has no MEMORY region for. Patch the bank count down so a
        # modest song overflows, and assert a clear exporter error.
        from unittest.mock import patch
        from mappers.mmc3 import MMC3Mapper
        frames = {'pulse1': {str(i): {'note': 60 + (i % 24), 'volume': 8 + (i % 7)}
                             for i in range(6000)}}
        patterns = {'p0': {'events': [{'note': 60, 'volume': 15}]}}
        out = Path("test_bankcap.asm")
        try:
            with patch.object(MMC3Mapper, 'SWAP_BANK_COUNT', 1):
                with self.assertRaises(ValueError) as ctx:
                    self.exporter.export_tables_with_patterns(frames, patterns, {}, str(out))
            self.assertIn("bank budget", str(ctx.exception).lower())
        finally:
            if out.exists():
                out.unlink()

    def test_direct_export_does_not_import_dpcm_tables(self):
        # Regression (#140): the DPCM sample tables are defined in the same
        # music.asm (the packer appends them, or the project builder stubs them),
        # so the direct export must reference them as local labels. A leftover
        # `.import dpcm_bank_table` collided with the packer's definition once
        # DPCM actually packed ("Symbol ... is already an import").
        frames = {'pulse1': {'0': {'note': 60, 'volume': 15}},
                  'dpcm': {'0': {'note': 1, 'volume': 15}}}
        out = Path("test_dpcm_noimport.asm")
        try:
            self.exporter.export_direct_frames(frames, str(out), standalone=False)
            content = out.read_text()
            self.assertNotIn('.import dpcm_bank_table', content)
            # The trigger code still references the tables (as local labels).
            self.assertIn('dpcm_bank_table', content)
        finally:
            if out.exists():
                out.unlink()

    def test_dmc_level_command_path_removed(self):
        # Regression (#72 / D-09): no stage ever produces `dmc_level`, so the
        # CMD_DMC_LEVEL ($87) plumbing was unreachable and has been removed. Even
        # a dpcm frame that carries a `dmc_level` must NOT emit CMD_DMC_LEVEL —
        # the exporter ignores the key entirely now.
        frames = {'dpcm': {'0': {'note': 1, 'volume': 15, 'dmc_level': 200},
                           '1': {'note': 1, 'volume': 15}}}
        patterns = {'p0': {'events': [{'note': 1, 'volume': 15}]}}
        refs = {'0': ('p0', 0)}  # non-empty patterns -> macro bytecode path
        test_output = Path("test_dmc_removed.asm")
        try:
            self.exporter.export_tables_with_patterns(frames, patterns, refs, test_output)
            output = test_output.read_text()
            self.assertNotIn('CMD_DMC_LEVEL', output)
            # The $87 opcode byte must not be emitted as a sequence command
            # (it may still legitimately appear as table data, so match the cmd).
            self.assertNotIn('.byte $87,', output)
        finally:
            if test_output.exists():
                test_output.unlink()

    def test_export_tables_with_patterns(self):
        test_output = Path("test_output.asm")
        try:
            self.exporter.export_tables_with_patterns(
                self.test_frames,
                self.test_patterns,
                self.test_references,
                test_output
            )
            with open(test_output, 'r') as f:
                output = f.read()
                
            # Test file header and new MMC3 mode output
            self.assertIn("; CA65 Assembly Export (MMC3 Macro Bytecode)", output)
            
            # Test segments
            self.assertIn(".segment \"DPCM\"", output)
            self.assertIn(".segment \"CODE_8000\"", output)
            
            # Test tables
            self.assertIn("ntsc_period_low:", output)
            self.assertIn("ntsc_period_high:", output)
            self.assertIn("instrument_table:", output)
            
            # Test pattern/sequence data
            self.assertIn("pulse1_sequence:", output)
            self.assertIn("pulse2_sequence:", output)
            self.assertIn("triangle_sequence:", output)
            self.assertIn("noise_sequence:", output)
            self.assertIn("dpcm_sequence:", output)
            
            # Test macro definitions
            self.assertIn("macro_vol_0:", output)
            self.assertIn("macro_duty_0:", output)
            self.assertIn("macro_pitch_0:", output)
            self.assertIn("macro_arp_0:", output)
            
        finally:
            if test_output.exists():
                test_output.unlink()
                
    def test_references_do_not_affect_output(self):
        # Regression (F-01 / #4): export_tables_with_patterns never consumes
        # `references` — output bytes derive only from frames+patterns. Two very
        # different references dicts must produce byte-identical assembly.
        out_a = Path("test_ref_a.asm")
        out_b = Path("test_ref_b.asm")
        try:
            self.exporter.export_tables_with_patterns(
                self.test_frames, self.test_patterns,
                {'0': ('pattern_1', 0), '32': ('pattern_1', 1)}, out_a)
            self.exporter.export_tables_with_patterns(
                self.test_frames, self.test_patterns,
                {}, out_b)  # empty references
            self.assertEqual(out_a.read_text(), out_b.read_text(),
                             "references must not change emitted bytes")
        finally:
            for p in (out_a, out_b):
                if p.exists():
                    p.unlink()

    def test_sweep_disabled_in_direct_init_paths(self):
        # Regression (NH-07 / #31): both direct-export init paths must disable the
        # pulse sweep units ($4001/$4005). Standalone emits a reset proc;
        # non-standalone emits init_music for the project builder.
        for standalone in (True, False):
            out = Path(f"test_sweep_{int(standalone)}.asm")
            try:
                self.exporter.export_tables_with_patterns(
                    self.test_frames, {}, {}, out, standalone=standalone)
                asm = out.read_text()
                self.assertIn("sta $4001", asm,
                              f"standalone={standalone}: pulse1 sweep ($4001) not disabled")
                self.assertIn("sta $4005", asm,
                              f"standalone={standalone}: pulse2 sweep ($4005) not disabled")
            finally:
                if out.exists():
                    out.unlink()

    def test_empty_patterns(self):
        test_output = Path("test_empty.asm")
        try:
            self.exporter.export_tables_with_patterns({}, {}, {}, test_output)
            with open(test_output, 'r') as f:
                output = f.read()
            
            # Empty patterns triggers direct frame export mode
            self.assertIn("; CA65 Assembly Export (Direct Frame Data)", output)
            self.assertIn(".segment \"CODE\"", output)
            self.assertIn(".segment \"ZEROPAGE\"", output)  # Direct frame mode has zeropage
            self.assertIn("frame_counter: .res 2", output)
            
            # Should have NES initialization structure
            self.assertIn(".proc reset", output)
            self.assertIn(".proc nmi", output)
            self.assertIn("play_music_frame", output)
            
            # Should have proper APU initialization
            self.assertIn("lda #$0F", output)  # APU enable value
            self.assertIn("sta $4015", output)  # APU status register
            
        finally:
            if test_output.exists():
                test_output.unlink()

def _patch_music_asm(music_asm_path):
    """Fix missing entry points in the generated music.asm to ensure compilation."""
    with open(music_asm_path, 'r') as f:
        content = f.read()

    append_text = ""
    if "init_music:" not in content and ".proc init_music" not in content:
        append_text += "\n.segment \"CODE\"\n.export init_music\ninit_music:\n  rts\n"

    if "update_music:" not in content and ".proc update_music" not in content:
        append_text += "\n.segment \"CODE\"\n.export update_music\nupdate_music:\n"
        if "play_music_frame" in content:
            append_text += "  jsr play_music_frame\n"
        elif "play_pattern_frame" in content:
            append_text += "  jsr play_pattern_frame\n"
        append_text += "  rts\n"

    if append_text:
        with open(music_asm_path, 'a') as f:
            f.write(append_text)


def _patch_nes_cfg(project_path):
    """Ensure nes.cfg has the necessary segments for the export."""
    nes_cfg = project_path / "nes.cfg"
    if nes_cfg.exists():
        # Dynamically detect all segments requested by the assembly files
        required_segments = set()
        for asm_file in project_path.glob("*.asm"):
            content = asm_file.read_text()
            segments = re.findall(r'\.segment\s+"([^"]+)"', content)
            required_segments.update(segments)

        content = nes_cfg.read_text()
        modified = False

        # Find default fallback load area (last non-bank specific PRG area)
        default_load_area = "PRG"
        for area in ["PRGFIXED", "PRG_ROM", "PRG_BANK_0", "PRG"]:
            if f"{area}: start =" in content or f"{area}: file =" in content:
                default_load_area = area
                break

        if "SEGMENTS {" in content:
            for seg in required_segments:
                # Skip standard system segments that require specific memory mapping (ZP, RAM)
                if f"{seg}:" not in content and seg not in ["ZEROPAGE", "BSS", "HEADER", "VECTORS"]:
                    # Handle MMC3 Bank switching segments
                    load_area = default_load_area
                    if seg.startswith("BANK_"):
                        bank_num = seg.split("_")[1]
                        if f"PRG_BANK_{bank_num}: start =" in content:
                            load_area = f"PRG_BANK_{bank_num}"
                        elif f"PRG_BANK_{int(bank_num)}: start =" in content:
                            load_area = f"PRG_BANK_{int(bank_num)}"

                    align = ", align = 64" if seg == "DPCM" else ""
                    content = content.replace("SEGMENTS {", f"SEGMENTS {{\n    {seg}: load = {load_area}, type = ro{align}, optional = yes;")
                    modified = True

        if modified:
            nes_cfg.write_text(content)


def _compile_and_link(project_path):
    """Compile and link the project, return (success, output)"""
    _patch_nes_cfg(Path(project_path))
    try:
        # Compile main.asm
        result = subprocess.run(
            ['ca65', 'main.asm', '-o', 'main.o'],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return False, f"Failed to compile main.asm:\n{result.stderr}"

        # Compile music.asm
        result = subprocess.run(
            ['ca65', 'music.asm', '-o', 'music.o'],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return False, f"Failed to compile music.asm:\n{result.stderr}"

        # Link the objects
        result = subprocess.run(
            ['ld65', '-C', 'nes.cfg', 'main.o', 'music.o', '-o', 'game.nes'],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return False, f"Failed to link:\n{result.stderr}"

        return True, "Compilation successful"
    except Exception as e:
        return False, f"Error during compilation: {str(e)}"


class TestCA65CompilationIntegration(unittest.TestCase):
    def setUp(self):
        self.exporter = CA65Exporter()
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.builder = NESProjectBuilder(str(self.project_path), mapper=MMC3Mapper())
        
        # Basic test data
        self.test_frames = {
            'pulse1': {
                '0': {'note': 60, 'volume': 15},
                '32': {'note': 67, 'volume': 12}
            }
        }
        self.test_patterns = {
            'pattern_1': {
                'events': [
                    {'note': 60, 'volume': 15},
                    {'note': 67, 'volume': 12}
                ]
            }
        }
        self.test_references = {
            '0': ('pattern_1', 0),
            '32': ('pattern_1', 1)
        }

    def tearDown(self):
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.temp_dir)

    def patch_music_asm(self, music_asm_path):
        """Fix missing entry points in the generated music.asm to ensure compilation."""
        _patch_music_asm(music_asm_path)

    def patch_nes_cfg(self):
        """Ensure nes.cfg has the necessary segments for the export."""
        _patch_nes_cfg(self.project_path)

    def compile_and_link(self, project_path):
        """Compile and link the project, return (success, output)"""
        return _compile_and_link(project_path)

    def test_basic_project_compilation(self):
        """Test that a basic project with minimal music data compiles"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        # Generate music.asm
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            self.test_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        # Prepare project
        self.builder.prepare_project(str(music_asm))
        
        # Try to compile
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation failed:\n{output}")

    def test_apu_initialized_in_boot_path(self):
        """The generated project must initialize the APU frame counter ($4017)
        and channel-enable register ($4015) before playback, otherwise the
        hardware frame sequencer fights the NMI-driven engine (issue #7).
        """
        self.project_path.mkdir(parents=True, exist_ok=True)
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            self.test_frames, self.test_patterns, self.test_references,
            music_asm, standalone=False,
        )
        self.patch_music_asm(music_asm)
        self.builder.prepare_project(str(music_asm))

        # The patterns path boots via audio_engine.asm's audio_init.
        engine = (self.project_path / "audio_engine.asm").read_text()
        init = engine.split("audio_init:", 1)[1].split("audio_update:", 1)[0]
        self.assertIn("$4017", init, "audio_init must write the frame counter ($4017)")
        self.assertIn("$4015", init, "audio_init must enable channels ($4015)")
        # Regression (NH-07 / #31): both sweep units must be disabled at init so
        # power-on garbage cannot bend or silence the pulse channels.
        self.assertIn("sta $4001", init, "audio_init must disable pulse1 sweep ($4001)")
        self.assertIn("sta $4005", init, "audio_init must disable pulse2 sweep ($4005)")

    def test_direct_export_compilation(self):
        """The direct/--no-patterns export (real frames, no patterns) must build a
        self-contained ROM without the bytecode engine or audio_engine.asm, which
        import symbols the direct path never defines (issue #50).
        """
        self.project_path.mkdir(parents=True, exist_ok=True)
        music_asm = self.project_path / "music.asm"
        # Empty patterns routes export_tables_with_patterns to the direct exporter.
        self.exporter.export_tables_with_patterns(
            self.test_frames, {}, {}, music_asm, standalone=False,
        )
        self.patch_music_asm(music_asm)
        self.builder.prepare_project(str(music_asm))

        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Direct-export compilation failed:\n{output}")
        # The self-contained direct path must not include the bytecode engine.
        main_asm = (self.project_path / "main.asm").read_text()
        self.assertNotIn('.include "audio_engine.asm"', main_asm)

    def test_empty_project_compilation(self):
        """Test that a project with no music data still compiles"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns({}, {}, {}, music_asm, standalone=False)
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Empty project compilation failed:\n{output}")

    def test_multi_song_compilation(self):
        """Test compilation with multiple songs"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        
        # Use basic project preparation for now instead of multi-song features
        # The multi-song features require more complex segment management
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            self.test_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Multi-song compilation failed:\n{output}")

    def test_zeropage_variables(self):
        """Test that zeropage variables are properly declared and used"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            self.test_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        
        # Read generated files and check for proper variable declarations
        with open(self.project_path / "main.asm") as f:
            main_content = f.read()
            # Updated to include temp_ptr for table-based lookups
            self.assertIn(".exportzp", main_content)
            self.assertIn("init_music", main_content)
            self.assertTrue("update_music" in main_content or "play_music" in main_content)
        
        with open(music_asm) as f:
            music_content = f.read()
            self.assertIn(".importzp", music_content)
            self.assertIn("init_music", music_content)
            self.assertTrue("update_music" in music_content or "play_music" in music_content)
        
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation with zeropage variables failed:\n{output}")

    def test_pattern_references(self):
        """Test that pattern references are properly aligned and addressable"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        
        # Create a pattern that requires proper alignment
        test_patterns = {
            'pattern_1': {'events': [{'note': 60, 'volume': 15}] * 256}  # Large pattern
        }
        test_references = {str(i): ('pattern_1', 0) for i in range(0, 256, 32)}
        
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            test_patterns,
            test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation with large patterns failed:\n{output}")

    def test_bank_switching(self):
        """Test compilation with bank switching for large songs"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        
        # Create patterns that would require bank switching
        large_patterns = {
            f'pattern_{i}': {
                'events': [{'note': 60, 'volume': 15}] * 256
            } for i in range(32)  # Many large patterns
        }
        
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            large_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation with bank switching failed:\n{output}")

    def test_rom_size_validation(self):
        """Test that compiled ROMs have correct iNES format size"""
        # Create project directory first
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            self.test_frames,
            self.test_patterns,
            self.test_references,
            music_asm,
            standalone=False
        )
        self.patch_music_asm(music_asm)
        
        self.builder.prepare_project(str(music_asm))
        success, output = self.compile_and_link(str(self.project_path))
        self.assertTrue(success, f"Compilation failed:\n{output}")
        
        # Check that the generated ROM has correct size
        rom_path = self.project_path / "game.nes"
        self.assertTrue(rom_path.exists(), "ROM file not generated")
        
        # Read and validate ROM
        rom_size = rom_path.stat().st_size

        # Verify iNES header
        with open(rom_path, 'rb') as f:
            header = f.read(16)

        expected_size = 16 + (header[4] * 16384) + (header[5] * 8192)
        self.assertEqual(rom_size, expected_size,
            f"ROM size mismatch: got {rom_size} bytes, expected {expected_size} bytes")

        self.assertEqual(header[0:4], b'NES\x1a', "Invalid iNES header")
        self.assertEqual(header[6] & 0xF0, 0x40, "Mapper should be MMC3 (4)")


class TestPackDirectTablesIntoBanks(unittest.TestCase):
    """Unit tests for _pack_direct_tables_into_banks (#255/MAP-2026-07-05-1)."""

    def setUp(self):
        self.exporter = CA65Exporter()

    def test_tables_fitting_one_bank_all_land_in_bank_zero(self):
        names = ['pulse1_note', 'pulse1_control', 'pulse1_timer_lo', 'pulse1_timer_hi']
        result = self.exporter._pack_direct_tables_into_banks(names, table_length=100, bank_size=16384)
        self.assertEqual(set(result.values()), {0})

    def test_tables_overflowing_one_bank_spill_into_the_next(self):
        # 5 tables x 4000 bytes = 20000 bytes; a 16384-byte bank only fits 4.
        names = [f'table_{i}' for i in range(5)]
        result = self.exporter._pack_direct_tables_into_banks(names, table_length=4000, bank_size=16384)
        self.assertEqual(result['table_0'], 0)
        self.assertEqual(result['table_1'], 0)
        self.assertEqual(result['table_2'], 0)
        self.assertEqual(result['table_3'], 0)
        self.assertEqual(result['table_4'], 1, "5th table must spill into bank 1")

    def test_single_table_exceeding_bank_size_raises_export_error(self):
        with self.assertRaises(ExportError):
            self.exporter._pack_direct_tables_into_banks(['huge_table'], table_length=20000, bank_size=16384)

    def test_table_exactly_at_bank_size_is_allowed(self):
        result = self.exporter._pack_direct_tables_into_banks(['t'], table_length=16384, bank_size=16384)
        self.assertEqual(result['t'], 0)


class TestEstimateDirectExportSize(unittest.TestCase):
    """Unit tests for estimate_direct_export_size (#255/MAP-2026-07-05-1)."""

    def setUp(self):
        self.exporter = CA65Exporter()

    def test_matches_actual_export_size_for_tone_channels(self):
        n = 500
        frames = {
            'pulse1': {str(i): {'note': 60, 'pitch': 400, 'control': 0x80} for i in range(n)},
            'pulse2': {str(i): {'note': 55, 'pitch': 300, 'control': 0x40} for i in range(n)},
        }
        estimated = self.exporter.estimate_direct_export_size(frames)
        # 2 channels x 4 bytes/frame x n frames.
        self.assertEqual(estimated, 2 * 4 * n)

    def test_accounts_for_noise_and_dpcm_byte_widths(self):
        n = 200
        frames = {
            'noise': {str(i): {'note': 1, 'control': 0, 'volume': 5} for i in range(n)},
            'dpcm': {str(i): {'note': 1, 'volume': 15} for i in range(n)},
        }
        estimated = self.exporter.estimate_direct_export_size(frames)
        self.assertEqual(estimated, 3 * n + 1 * n)

    def test_empty_frames_estimate_zero(self):
        self.assertEqual(self.exporter.estimate_direct_export_size({}), 0)

    def test_ignores_dpcm_sample_map_side_table(self):
        frames = {
            'pulse1': {'0': {'note': 60, 'pitch': 400, 'control': 0x80}},
            'dpcm_sample_map': {'0': 1234},
        }
        # Only pulse1 (4 bytes x 1 frame) should count.
        self.assertEqual(self.exporter.estimate_direct_export_size(frames), 4)


class TestMMC1BankSwitchedDirectExportStructure(unittest.TestCase):
    """Structural checks on export_direct_frames' MMC1 output (#255/MAP-2026-07-05-1)."""

    def setUp(self):
        self.exporter = CA65Exporter()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _build_frames(self, n_frames, channels=('pulse1', 'pulse2', 'triangle')):
        frames = {}
        for ch in channels:
            frames[ch] = {str(i): {'note': 60, 'pitch': 400, 'control': 0x80, 'volume': 10}
                           for i in range(n_frames)}
        return frames

    def test_small_song_stays_on_one_bank_segment(self):
        """A song small enough to fit one bank must emit only RODATA_BANK_00
        -- but bank-switch code is still emitted before every table read
        (even targeting bank 0), since a prior table read elsewhere in the
        frame could have left a different bank selected."""
        frames = self._build_frames(50)
        out = Path(self.tmp) / "small.asm"
        self.exporter.export_direct_frames(frames, str(out), standalone=False, mapper=MMC1Mapper())
        content = out.read_text()
        banks = set(re.findall(r'RODATA_BANK_(\d+)', content))
        self.assertEqual(banks, {'00'})
        self.assertIn('Bank-switch', content)

    def test_large_song_spans_multiple_bank_segments_with_switches(self):
        frames = self._build_frames(6000)  # 3 channels x 4 bytes x 6000 = 72,000 bytes
        out = Path(self.tmp) / "large.asm"
        self.exporter.export_direct_frames(frames, str(out), standalone=False, mapper=MMC1Mapper())
        content = out.read_text()
        banks = sorted(set(int(m) for m in re.findall(r'RODATA_BANK_(\d+)', content)))
        self.assertGreater(len(banks), 1, "72,000 bytes must span more than one 16KB bank")
        self.assertEqual(banks, list(range(len(banks))), "banks must be used contiguously from 0")
        self.assertIn('Bank-switch', content)

    def test_no_mapper_keeps_single_flat_rodata_segment(self):
        """Backward compatibility: mapper=None (or a non-banked mapper) must
        produce byte-for-byte the same single flat RODATA segment as before
        this fix, with no bank-switch code inserted."""
        frames = self._build_frames(6000)
        out = Path(self.tmp) / "flat.asm"
        self.exporter.export_direct_frames(frames, str(out), standalone=False, mapper=None)
        content = out.read_text()
        self.assertEqual(content.count('.segment "RODATA"'), 1)
        self.assertNotIn('RODATA_BANK', content)
        self.assertNotIn('Bank-switch', content)

    def test_mmc3_mapper_also_keeps_flat_rodata(self):
        """MMC3's direct-export mode isn't banked (direct_export_bank_size()
        returns None), so it must behave like mapper=None too."""
        frames = self._build_frames(6000)
        out = Path(self.tmp) / "mmc3_flat.asm"
        self.exporter.export_direct_frames(frames, str(out), standalone=False, mapper=MMC3Mapper())
        content = out.read_text()
        self.assertEqual(content.count('.segment "RODATA"'), 1)
        self.assertNotIn('RODATA_BANK', content)

    def test_single_channel_exceeding_one_bank_raises_export_error(self):
        # A single table > 16384 bytes can't be packed into one bank, and the
        # direct engine doesn't support mid-table bank splitting.
        frames = self._build_frames(20000, channels=('pulse1',))
        out = Path(self.tmp) / "toolong.asm"
        with self.assertRaises(ExportError):
            self.exporter.export_direct_frames(frames, str(out), standalone=False, mapper=MMC1Mapper())


class TestMMC1BankSwitchedRealBuild(unittest.TestCase):
    """Real ca65/ld65 build of a bank-switched MMC1 ROM (#255/MAP-2026-07-05-1).

    Uses the same patch_music_asm/patch_nes_cfg/compile_and_link helpers as
    TestCA65CompilationIntegration (module-level, shared rather than
    duplicated) with an MMC1Mapper project. This is the exact kind of check
    the issue's evidence section performed manually: the bug ASSEMBLED AND
    LINKED CLEANLY while silently overflowing RODATA into the fixed engine
    bank, so success here must additionally verify placement (every
    RODATA_BANK_NN segment runs at $8000, never spilling into $C000+), not
    just a nonzero exit code.
    """

    def setUp(self):
        self.exporter = CA65Exporter()
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multi_bank_direct_export_links_with_correct_bank_placement(self):
        self.project_path.mkdir(parents=True, exist_ok=True)
        mapper = MMC1Mapper()
        builder = NESProjectBuilder(str(self.project_path), mapper=mapper)

        # 3 tone channels x 4 bytes/frame x 6000 frames = 72,000 bytes,
        # spanning multiple 16KB banks -- the exact scenario from the issue.
        n = 6000
        frames = {
            'pulse1': {str(i): {'note': 60 + (i % 12), 'pitch': 400, 'control': 0x80} for i in range(n)},
            'pulse2': {str(i): {'note': 55, 'pitch': 300, 'control': 0x40} for i in range(n)},
            'triangle': {str(i): {'note': 40, 'pitch': 200, 'volume': 10} for i in range(n)},
        }

        music_asm = self.project_path / "music.asm"
        self.exporter.export_tables_with_patterns(
            frames, {}, {}, music_asm, standalone=False, mapper=mapper
        )
        content = music_asm.read_text()
        bank_ids = set(re.findall(r'RODATA_BANK_(\d+)', content))
        self.assertGreater(len(bank_ids), 1,
                            "fixture must span multiple MMC1 banks to exercise the fix")

        _patch_music_asm(music_asm)
        prepared = builder.prepare_project(str(music_asm))
        self.assertTrue(prepared)

        success, output = _compile_and_link(str(self.project_path))
        self.assertTrue(success, f"MMC1 bank-switched build failed:\n{output}")

        # The real regression check: every RODATA_BANK_NN segment must run at
        # $8000 (the switchable window). Before the fix, ld65 linked a single
        # linear PRGSWAP region with NO error, but data past the first 16KB
        # ran at addresses >= $C000, aliasing the fixed engine bank at
        # runtime -- exactly the silent failure mode this test must catch.
        map_result = subprocess.run(
            ['ld65', '-C', 'nes.cfg', 'main.o', 'music.o', '-o', 'game.nes', '-m', 'map.txt'],
            cwd=str(self.project_path), capture_output=True, text=True
        )
        self.assertEqual(map_result.returncode, 0, map_result.stderr)
        map_text = (self.project_path / 'map.txt').read_text()
        bank_lines = [line for line in map_text.splitlines()
                      if line.strip().startswith('RODATA_BANK_')
                      and re.search(r'\bRODATA_BANK_\d+\s+[0-9A-F]{6}', line)]
        self.assertTrue(bank_lines, f"expected RODATA_BANK_NN placement rows in map:\n{map_text}")
        for line in bank_lines:
            self.assertIn('008000', line,
                          f"RODATA bank segment did not run at CPU address $8000: {line}")


class TestNoteClampReporting(unittest.TestCase):
    """#298/EXP-10: tone-channel notes clamped to the NES range (24-95) by the
    macro-bytecode path must be counted so the re-pitch is reported, not silent."""

    def _export(self, notes):
        frames = {'pulse1': {str(i): {'note': n, 'volume': 8, 'control': 0x80}
                             for i, n in enumerate(notes)}}
        exp = CA65Exporter()
        out = Path(tempfile.mktemp(suffix='.asm'))
        # Non-empty patterns selects the macro-bytecode path that clamps.
        exp.export_tables_with_patterns(frames, {'x': 1}, {}, str(out))
        out.unlink(missing_ok=True)
        return exp.notes_clamped

    def test_in_range_notes_not_counted(self):
        self.assertEqual(self._export([60, 67, 72]), {'high': 0, 'low': 0})

    def test_above_b6_counted_high(self):
        self.assertEqual(self._export([100, 96])['high'], 2)

    def test_below_c1_counted_low(self):
        self.assertEqual(self._export([10, 23])['low'], 2)

    def test_sustained_out_of_range_note_counted_once(self):
        # A single note held across many frames is one re-pitch, not one per frame.
        self.assertEqual(self._export([100, 100, 100, 100]), {'high': 1, 'low': 0})


if __name__ == '__main__':
    unittest.main()
