from exporter.base_exporter import BaseExporter, atomic_write_text
from nes.pitch_table import NES_NOTE_TABLE, NES_TRIANGLE_TABLE
from core.exceptions import ExportError

# NES APU register addresses
APU_PULSE1_CTRL = 0x4000
APU_PULSE1_SWEEP = 0x4001
APU_PULSE1_TIMER_LO = 0x4002
APU_PULSE1_TIMER_HI = 0x4003

APU_PULSE2_CTRL = 0x4004
APU_PULSE2_SWEEP = 0x4005
APU_PULSE2_TIMER_LO = 0x4006
APU_PULSE2_TIMER_HI = 0x4007

APU_TRIANGLE_CTRL = 0x4008
APU_TRIANGLE_TIMER_LO = 0x400A
APU_TRIANGLE_TIMER_HI = 0x400B

APU_NOISE_CTRL = 0x400C
APU_NOISE_PERIOD = 0x400E
APU_NOISE_LENGTH = 0x400F

APU_DMC_CTRL = 0x4010
APU_DMC_LOAD = 0x4011
APU_DMC_ADDR = 0x4012
APU_DMC_LEN = 0x4013

APU_STATUS = 0x4015

# Triangle control byte ($4008 = CRRR RRRR): bit 7 is the linear-counter
# control/halt flag, bits 6-0 the linear-counter reload value
# (docs/APU_TRIANGLE_REFERENCE.md §4). With the control flag set, the reload
# flag is re-armed every frame, so the counter never gates the note — any
# non-zero reload plays continuously and the exact reload value is inert. Use a
# fixed max reload (0xFF = control flag + 0x7F), matching the bytecode engine's
# $FF write (nes/audio_engine.asm), rather than scaling it by loudness: the
# triangle has no volume control (§1), so a loudness-derived reload was a
# meaningless, latent-trap constant (#364/NH-HW-04).
TRIANGLE_LINEAR_COUNTER_CONTROL = 0x80  # bit 7 (control/halt flag)
TRIANGLE_LINEAR_COUNTER_MAX = 0x7F      # bits 6-0 max reload
TRIANGLE_CONTROL_ON = TRIANGLE_LINEAR_COUNTER_CONTROL | TRIANGLE_LINEAR_COUNTER_MAX  # 0xFF

# Pitch timer values come from the single authoritative NES_NOTE_TABLE in
# nes/pitch_table.py (fCPU/16 formula). The exporter must NOT keep its own
# divergent table: the bytecode pitch offset is `frame_pitch - base_timer`, and
# the frame pitch is produced from NES_NOTE_TABLE too, so any scale mismatch
# corrupts the played note (#16).


def song_has_dpcm_events(frames):
    """True if `frames['dpcm']` contains a real (non-silent) drum hit.

    Multi-song `song build` (#30/F-13) doesn't support DPCM in v1 (see
    docs/ROADMAP.md): no `DpcmPacker` runs for a jukebox build, so a DPCM
    trigger byte would index the project builder's 1-byte stub
    `dpcm_*_table`s past their end, feeding garbage into a live DMC DMA
    trigger. `export_song_bank_bytecode` uses this to raise a clear error
    itself (#509/EXP-2026-08-23-2) rather than depending solely on a
    caller-side check -- this used to be a private copy in `main.py`
    (`_song_has_dpcm_events`), which only protected `run_song_build`'s own
    CLI path and left every other caller of this module unguarded.
    """
    dpcm_frames = frames.get('dpcm') or {}
    return any(
        (frame_data or {}).get('note', 0) and (frame_data or {}).get('volume', 0)
        for frame_data in dpcm_frames.values()
    )


class CA65Exporter(BaseExporter):
    def __init__(self):
        super().__init__()
        # First PRG bank not already claimed by this song's own BANK_NN
        # sequence bytecode; defaults to 0 (no bytecode banks used yet) so
        # it's always a real int a caller can read straight off a fresh
        # instance -- export_tables_with_patterns overwrites it once the
        # bytecode branch actually runs (#522/DPCM-2026-08-23-1). A caller
        # packing DPCM samples afterward (main.py's pack_dpcm_into_asm)
        # reads this to start DPCM_NN numbering after the song's own banks,
        # since DPCM_NN and BANK_NN share the same physical PRG_BANK_NN
        # pool (mappers/mmc3.py).
        self.next_bank = 0

    def midi_note_to_timer_value(self, midi_note, channel=None):
        # Clamp instead of returning 0: a 0 base combined with the encoder's
        # +127-clamped pitch offset overflows the 11-bit timer at runtime
        # instead of just playing the nearest representable note (#158).
        midi_note = max(24, min(midi_note, 119))
        # Use the shared per-channel table so this base timer is on the same
        # scale as the frame `pitch` it is differenced against (#16, #12).
        # Triangle uses the /32 table (an octave lower for the same timer), so
        # mixing it with the pulse base would clamp the offset and corrupt the
        # bass. Both tables already floor at 8 and clamp to 11-bit.
        if channel == 'triangle':
            return NES_TRIANGLE_TABLE[midi_note]
        return NES_NOTE_TABLE[midi_note]

    # $FF is the only macro *control* byte the live engine understands:
    # _compress_macro appends it as end/sustain, and EVAL_MACRO
    # (nes/audio_engine.asm) reads the first $FF as end-of-macro -- it has no
    # branch for $FE at all, so _compress_macro intentionally never emits
    # $FE either (loop compression was removed, #163/NH-21). $FE is still
    # kept out of the *data* domain here as a forward-compatible reservation
    # in case loop support is ever added to both sides together; a signed
    # pitch/arp offset spans the whole byte, so the offsets -1 (0xFF) and
    # -2 (0xFE) would otherwise be misread as control codes mid-stream,
    # truncating or desyncing the macro (#77). There is no spare byte in a
    # full signed domain, so the encoder keeps both values out of the data:
    # snap each to its nearest non-reserved encoding.
    MACRO_CTRL_END = 0xFF
    MACRO_CTRL_LOOP = 0xFE

    def _encode_macro_offset(self, value):
        """Encode a signed pitch/arp offset to a macro data byte that can never
        collide with the $FE/$FF control bytes (#77).

        ``value`` is clamped to the 8-bit signed range, then the two colliding
        encodings are snapped to the nearest representable, non-reserved byte:
        -1 (0xFF) -> 0 and -2 (0xFE) -> -3 (0xFD). For pitch these are period-unit
        deltas, so the <=1-unit nudge is sub-cent and inaudible; arp offsets are
        semitone steps (and no current producer emits a negative arp).
        """
        byte = max(-128, min(127, int(value))) & 0xFF
        if byte == self.MACRO_CTRL_END:      # -1 -> 0 (nearest non-reserved)
            byte = 0x00
        elif byte == self.MACRO_CTRL_LOOP:   # -2 -> -3 (nearest non-reserved)
            byte = 0xFD
        return byte

    def estimate_direct_export_size(self, frames):
        """Predict export_direct_frames' total RODATA byte count from
        ``frames`` alone, without actually exporting (#255/MAP-2026-07-05-1).

        A bank-switching-aware export needs to know the target mapper before
        it writes anything, but main.py's `--mapper auto` selection has
        historically measured the *already-exported* music.asm. This lets
        callers resolve the mapper first and pass it into
        export_tables_with_patterns/export_direct_frames from the start.

        Mirrors export_direct_frames' own accounting exactly: 4 bytes/frame
        for each active tone channel (note+control+timer_lo+timer_hi), 3 for
        noise (note+ctrl+reg), 1 for dpcm (note) -- so a drift between the
        two would only under/over-estimate, never silently diverge in shape.
        """
        active = [name for name, data in frames.items()
                  if name != 'dpcm_sample_map' and data]
        if not active:
            return 0
        max_frame = max(int(f) for name in active for f in frames[name].keys())
        bytes_per_frame = {'pulse1': 4, 'pulse2': 4, 'triangle': 4, 'noise': 3, 'dpcm': 1}
        per_frame_total = sum(bytes_per_frame.get(name, 0) for name in active)
        return per_frame_total * (max_frame + 1)

    def _pack_direct_tables_into_banks(self, table_names, table_length, bank_size):
        """Assign each direct-export frame table to a bank index (#255/MAP-2026-07-05-1).

        Every table `export_direct_frames` emits (note/control/timer_lo/
        timer_hi per tone channel, note/ctrl/reg for noise, note for dpcm) is
        exactly ``table_length`` (== max_frame + 1) bytes long, so bin-packing
        reduces to a simple division: ``bank_size // table_length`` whole
        tables fit per bank. Tables are packed whole -- never split across a
        bank boundary -- because the runtime bank-switch happens once per
        table access (see _emit_table_read_lines), not per byte.

        Raises ExportError if a single table alone exceeds bank_size (would
        need mid-table bank switching, which the direct engine does not do).
        """
        if table_length > bank_size:
            raise ExportError(
                f"Direct-export frame table is {table_length:,} bytes, exceeding "
                f"the {bank_size:,}-byte switchable bank window -- shorten the "
                f"song, drop a channel, or use a mapper with flat PRG addressing "
                f"(NROM) or pattern compression (MMC3)."
            )
        tables_per_bank = max(1, bank_size // table_length)
        return {name: i // tables_per_bank for i, name in enumerate(table_names)}

    def _emit_table_read_lines(self, table_name, mapper, table_bank):
        """CA65 lines that load A = table_name[frame_counter], Y left at 0.

        If ``table_name`` has a bank assignment in ``table_bank``, a
        bank-switch is emitted first so the table's actual bank is mapped
        into the mapper's switchable window before the read (#255/MAP-2026-07-05-1).
        Replaces the ~9-line pointer computation that used to be duplicated
        inline at every one of the ~16 table-read call sites in this method.
        """
        lines = []
        bank = table_bank.get(table_name) if table_bank else None
        if bank is not None:
            lines.append(f'    ; Bank-switch for {table_name} (#255/MAP-2026-07-05-1)')
            lines.append(mapper.generate_bank_switch_code(bank))
        lines.extend([
            f'    lda #<{table_name}',
            '    clc',
            '    adc frame_counter',
            '    sta temp_ptr',
            f'    lda #>{table_name}',
            '    adc frame_counter+1',
            '    sta temp_ptr+1',
            '    ldy #0',
            '    lda (temp_ptr),y',
        ])
        return lines

    def _emit_safe_beq(self, target, unique_suffix, bank_size, comment=''):
        """Emit ``beq target`` (#255/MAP-2026-07-05-1), safe against the
        6502's +-127-byte relative-branch range.

        Discovered via a real ca65 assemble: bank-switch code inserted
        between a channel's note-changed check and its `@sustain`/`@silence`
        label (both defined near the end of the enclosing .proc) can push
        the plain relative `beq` out of range ("Range error (N not in
        [-128..127])"). When bank-switching is active (bank_size is not
        None), falls back to an inverted `bne` over an absolute `jmp` (no
        distance limit) instead. When bank_size is None, emits the original
        single-instruction relative branch, byte-for-byte unchanged, since
        no extra bytes were inserted for mappers that don't need this.
        """
        suffix = f'{"":<11}{comment}' if comment else ''
        if bank_size is None:
            return [f'    beq {target}{suffix}']
        skip_label = f'@skip_{unique_suffix}'
        return [
            f'    bne {skip_label}',
            f'    jmp {target}{suffix}',
            f'{skip_label}:',
        ]

    # ------------------------------------------------------------------
    # Direct-export per-channel emitters (#136/TD-11). Extracted verbatim
    # from export_direct_frames -- same lines, same order, same asymmetric
    # comments where pulse1/pulse2 historically diverged -- so the emitted
    # music.asm is byte-for-byte unchanged (verified via golden-file diff
    # across standalone/non-standalone, all three mappers, and with/without
    # noise/dpcm). Splitting these into independently callable/testable
    # methods was the issue's explicit ask (cf. REG-05/#45's testability
    # gap). ensure_segment/emit_byte_table are the closures export_direct_
    # frames defines over its local `lines`/`current_segment`/`table_bank`
    # -- passed in rather than duplicated so bank-packed segment interleaving
    # across channels still works exactly as before.

    def _emit_pulse_or_triangle_table(self, lines, channel_name, channel_data,
                                        max_frame, ensure_segment):
        """Emit the note/control/timer_lo/timer_hi frame tables for a pulse1,
        pulse2, or triangle channel. Triangle's control byte has no volume/
        duty (docs/APU_TRIANGLE_REFERENCE.md §1) -- see #364/NH-HW-04."""
        ensure_segment(f'{channel_name}_note')
        lines.append(f'; {channel_name.upper()} Frame Data Tables')

        # Create arrays that are indexed by frame number
        # We use $00 for empty frames (silent)
        note_table = []
        control_table = []
        timer_lo_table = []
        timer_hi_table = []

        for frame_num in range(max_frame + 1):
            # Check if this frame has data (keys can be int or str)
            if frame_num in channel_data:
                frame_data = channel_data[frame_num]
            elif str(frame_num) in channel_data:
                frame_data = channel_data[str(frame_num)]
            else:
                # Empty frame - silence
                note_table.append("$00")
                control_table.append("$00")
                timer_lo_table.append("$00")
                timer_hi_table.append("$00")
                continue

            # Frame has data - process it
            pitch = frame_data.get('pitch', 0)
            note = frame_data.get('note', 0)

            # Triangle channel uses different control format
            if channel_name == 'triangle':
                # Triangle $4008: bit 7 = linear-counter control flag, bits
                # 6-0 = reload value (docs/APU_TRIANGLE_REFERENCE.md §4). The
                # triangle has no volume control (§1), so `volume` here is
                # only a gate: 0 -> silent (clear the flag, reload 0), else
                # play at a fixed max reload with the flag set (0xFF, like the
                # bytecode engine). The old `0x80 | volume*7` scaled a halted
                # counter's reload by loudness — inert but a latent trap
                # (clearing bit 7 would turn it into a wrong note-length
                # knob) (#364/NH-HW-04).
                volume = frame_data.get('volume', 0)
                if volume == 0:
                    control = 0x00
                else:
                    control = TRIANGLE_CONTROL_ON
            else:
                # Pulse channels: use provided control byte
                control = frame_data.get('control', 0)

            # Re-assert the audible 11-bit timer range before the byte split.
            # t < 8 silences pulse/triangle (APU_PULSE_REFERENCE §3/§7), so a
            # nonzero pitch is floored at 8; a true rest (pitch 0) stays 0.
            if pitch:
                pitch = max(8, min(pitch, 0x07FF))

            note_table.append(f"${note:02X}")
            control_table.append(f"${control:02X}")
            timer_lo_table.append(f"${pitch & 0xFF:02X}")
            timer_hi_table.append(f"${((pitch >> 8) & 0x07):02X}")

        # Write tables in chunks of 16 bytes per line
        ensure_segment(f'{channel_name}_note')
        lines.append(f'{channel_name}_note:')
        for i in range(0, len(note_table), 16):
            chunk = note_table[i:i+16]
            lines.append(f'    .byte {", ".join(chunk)}')

        ensure_segment(f'{channel_name}_control')
        lines.append(f'{channel_name}_control:')
        for i in range(0, len(control_table), 16):
            chunk = control_table[i:i+16]
            lines.append(f'    .byte {", ".join(chunk)}')

        ensure_segment(f'{channel_name}_timer_lo')
        lines.append(f'{channel_name}_timer_lo:')
        for i in range(0, len(timer_lo_table), 16):
            chunk = timer_lo_table[i:i+16]
            lines.append(f'    .byte {", ".join(chunk)}')

        ensure_segment(f'{channel_name}_timer_hi')
        lines.append(f'{channel_name}_timer_hi:')
        for i in range(0, len(timer_hi_table), 16):
            chunk = timer_hi_table[i:i+16]
            lines.append(f'    .byte {", ".join(chunk)}')
        lines.append('')

    def _emit_noise_table(self, lines, channel_data, max_frame, emit_byte_table):
        """Emit noise frame tables (#9). note = 4-bit period index (0 =
        rest/change sentinel); ctrl = $400C byte ($30 | volume); reg =
        $400E byte (mode bit 7 | period). Drum hits are sparse, so empty
        frames are rests."""
        n_note, n_ctrl, n_reg = [], [], []
        for frame_num in range(max_frame + 1):
            fd = channel_data.get(frame_num, channel_data.get(str(frame_num)))
            if not fd or fd.get('volume', 0) == 0:
                n_note.append('$00'); n_ctrl.append('$00'); n_reg.append('$00')
                continue
            period = fd.get('note', 0) & 0x0F
            mode = (fd.get('control', 0) >> 6) & 0x01
            vol = fd.get('volume', 0) & 0x0F
            n_note.append(f'${period:02X}')
            n_ctrl.append(f'${0x30 | vol:02X}')
            n_reg.append(f'${(mode << 7) | period:02X}')
        lines.append('; NOISE Frame Data Tables')
        emit_byte_table('noise_note', n_note)
        emit_byte_table('noise_ctrl', n_ctrl)
        emit_byte_table('noise_reg', n_reg)
        lines.append('')

    def _emit_dpcm_table(self, lines, channel_data, max_frame, emit_byte_table):
        """Emit DPCM frame tables (#9). note = sample_id + 1 (0 = rest/change
        sentinel). The trigger reuses the packer/engine sample tables
        (dpcm_*_table)."""
        d_note = []
        for frame_num in range(max_frame + 1):
            fd = channel_data.get(frame_num, channel_data.get(str(frame_num)))
            if not fd or fd.get('volume', 0) == 0:
                d_note.append('$00')
                continue
            d_note.append(f'${fd.get("note", 0) & 0xFF:02X}')
        lines.append('; DPCM Frame Data Tables')
        emit_byte_table('dpcm_note', d_note)
        lines.append('')

    def _emit_vis_store(self, chan_index):
        """--visualizer (nes/visualizer.py): mask the control byte's volume
        nibble -- still in A, unaffected by the `sta` just before this is
        spliced in -- into channel_vis_vol[chan_index]. `$30 & $0F == 0`, so
        the same snippet spliced after a silence write correctly zeroes the
        bar too."""
        return [
            '    and #$0F               ; --visualizer: isolate volume nibble',
            f'    sta channel_vis_vol+{chan_index}',
        ]

    def _emit_pulse1_proc(self, lines, mapper, table_bank, bank_size, visualizer=False):
        """Emit the play_pulse1 playback subroutine."""
        lines.extend([
            '.proc play_pulse1',
            '    ; Get note number for this frame',
        ])
        lines.extend(self._emit_table_read_lines('pulse1_note', mapper, table_bank))
        lines.extend([
            '    ',
            '    ; Check if note changed',
            '    cmp last_pulse1_note',
        ])
        lines.extend(self._emit_safe_beq('@sustain', 'p1_sustain', bank_size,
                                          "; Same note - sustain, don't retrigger"))
        lines.extend([
            '    sta last_pulse1_note   ; NB: STA does not affect Z',
            '    cmp #0                 ; re-test the note (A still holds it); STA left the stale CMP flags (#66/#107)',
            '    ',
            '    ; Note changed - check if new note is silence',
        ])
        lines.extend(self._emit_safe_beq('@silence', 'p1_silence', bank_size,
                                          '; If note is 0, silence the channel'))
        lines.extend([
            '    ',
            '    ; New note - write full channel state',
            '    ; Get and write control byte',
        ])
        lines.extend(self._emit_table_read_lines('pulse1_control', mapper, table_bank))
        lines.extend([
            '    sta $4000',
        ])
        if visualizer:
            lines.extend(self._emit_vis_store(0))
        lines.extend([
            '    ',
            '    ; Get and write timer low',
        ])
        lines.extend(self._emit_table_read_lines('pulse1_timer_lo', mapper, table_bank))
        lines.extend([
            '    sta $4002',
            '    ',
            '    ; Get and write timer high with length counter reload',
        ])
        lines.extend(self._emit_table_read_lines('pulse1_timer_hi', mapper, table_bank))
        lines.extend([
            '    ora #$08               ; Set length reload for new notes',
            '    sta $4003',
            '    rts',
            '    ',
            '@silence:',
            '    ; Silence the channel',
            '    lda #$30               ; Zero volume, duty 0',
            '    sta $4000',
        ])
        if visualizer:
            lines.extend(self._emit_vis_store(0))
        lines.extend([
            '    rts',
            '    ',
            '@sustain:',
            '    ; Note is sustaining - do nothing to avoid phase reset',
            '    rts',
            '.endproc',
            ''
        ])

    def _emit_pulse2_proc(self, lines, mapper, table_bank, bank_size, visualizer=False):
        """Emit the play_pulse2 playback subroutine."""
        lines.extend([
            '.proc play_pulse2',
            '    ; Get note number for this frame',
        ])
        lines.extend(self._emit_table_read_lines('pulse2_note', mapper, table_bank))
        lines.extend([
            '    ',
            '    ; Check if note changed',
            '    cmp last_pulse2_note',
        ])
        lines.extend(self._emit_safe_beq('@sustain', 'p2_sustain', bank_size))
        lines.extend([
            '    sta last_pulse2_note   ; NB: STA does not affect Z',
            '    cmp #0                 ; re-test the note (A still holds it); STA left the stale CMP flags (#66/#107)',
            '    ',
            '    ; Note changed - check if silence',
        ])
        lines.extend(self._emit_safe_beq('@silence', 'p2_silence', bank_size))
        lines.extend([
            '    ',
            '    ; New note - write full channel state',
            '    ; Get and write control byte',
        ])
        lines.extend(self._emit_table_read_lines('pulse2_control', mapper, table_bank))
        lines.extend([
            '    sta $4004',
        ])
        if visualizer:
            lines.extend(self._emit_vis_store(1))
        lines.extend([
            '    ',
            '    ; Get and write timer low',
        ])
        lines.extend(self._emit_table_read_lines('pulse2_timer_lo', mapper, table_bank))
        lines.extend([
            '    sta $4006',
            '    ',
            '    ; Get and write timer high',
        ])
        lines.extend(self._emit_table_read_lines('pulse2_timer_hi', mapper, table_bank))
        lines.extend([
            '    ora #$08',
            '    sta $4007',
            '    rts',
            '    ',
            '@silence:',
            '    lda #$30',
            '    sta $4004',
        ])
        if visualizer:
            lines.extend(self._emit_vis_store(1))
        lines.extend([
            '    rts',
            '    ',
            '@sustain:',
            '    rts',
            '.endproc',
            ''
        ])

    def _emit_triangle_proc(self, lines, mapper, table_bank, bank_size, visualizer=False):
        """Emit the play_triangle playback subroutine."""
        lines.extend([
            '.proc play_triangle',
            '    ; Get note number for this frame',
        ])
        lines.extend(self._emit_table_read_lines('triangle_note', mapper, table_bank))
        lines.extend([
            '    ',
            '    ; Check if note changed',
            '    cmp last_triangle_note',
        ])
        lines.extend(self._emit_safe_beq('@sustain', 'tri_sustain', bank_size))
        lines.extend([
            '    sta last_triangle_note ; NB: STA does not affect Z',
            '    cmp #0                 ; re-test the note (A still holds it); STA left the stale CMP flags (#66/#107)',
            '    ',
            '    ; Note changed - check if silence',
        ])
        lines.extend(self._emit_safe_beq('@silence', 'tri_silence', bank_size))
        lines.extend([
            '    ',
            '    ; New note - write full channel state',
            '    ; Get and write control byte',
        ])
        lines.extend(self._emit_table_read_lines('triangle_control', mapper, table_bank))
        lines.extend([
            '    sta $4008',
        ])
        if visualizer:
            # Triangle has no hardware volume register (on/off only) and
            # this direct-export path has no per-frame envelope value
            # available here (only the on/off control byte) -- unlike the
            # bytecode engine's temp_vol, so the bar is binary: full when
            # active, zero when silenced.
            lines.extend([
                '    lda #$0F               ; --visualizer: on (no per-frame envelope here)',
                '    sta channel_vis_vol+2',
            ])
        lines.extend([
            '    ',
            '    ; Get and write timer low',
        ])
        lines.extend(self._emit_table_read_lines('triangle_timer_lo', mapper, table_bank))
        lines.extend([
            '    sta $400A',
            '    ',
            '    ; Get and write timer high',
        ])
        lines.extend(self._emit_table_read_lines('triangle_timer_hi', mapper, table_bank))
        lines.extend([
            '    ora #$08',
            '    sta $400B',
            '    rts',
            '    ',
            '@silence:',
            '    lda #$00',
            '    sta $4008',
        ])
        if visualizer:
            lines.extend([
                '    lda #$00               ; --visualizer: off',
                '    sta channel_vis_vol+2',
            ])
        lines.extend([
            '    rts',
            '    ',
            '@sustain:',
            '    rts',
            '.endproc',
            ''
        ])

    def _emit_noise_proc(self, lines, mapper, table_bank, bank_size, visualizer=False):
        """Emit the play_noise playback subroutine."""
        lines.extend([
            '.proc play_noise',
            '    ; Index noise_note[frame_counter]',
        ])
        lines.extend(self._emit_table_read_lines('noise_note', mapper, table_bank))
        lines.extend(self._emit_safe_beq('@silence', 'noise_silence', bank_size,
                                          '; note 0 -> silence'))
        lines.extend([
            '    ; Active hit -- rewrite $400C/$400E/$400F every frame from',
            '    ; the tables, even while the period is unchanged from the',
            '    ; last frame. The length counter is always halted and constant',
            '    ; volume always set (#162/NH-19), so there is no hardware',
            '    ; decay to lean on -- emulator_core.py bakes a software volume',
            '    ; ramp into noise_ctrl per frame, and $400E/$400F writes never',
            '    ; reset the noise phase (docs/APU_NOISE_REFERENCE.md section 6),',
            '    ; so writing unconditionally is both safe and required.',
        ])
        lines.extend(self._emit_table_read_lines('noise_ctrl', mapper, table_bank))
        lines.extend([
            '    sta $400C',
        ])
        if visualizer:
            lines.extend(self._emit_vis_store(3))
        lines.extend([
            '    ; $400E from noise_reg (mode bit 7 | period)',
        ])
        lines.extend(self._emit_table_read_lines('noise_reg', mapper, table_bank))
        lines.extend([
            '    sta $400E',
            '    lda #$08             ; length counter load (harmless: halted)',
            '    sta $400F',
            '    rts',
            '@silence:',
            '    lda #$30             ; constant volume 0 - silence noise',
            '    sta $400C',
        ])
        if visualizer:
            lines.extend(self._emit_vis_store(3))
        lines.extend([
            '    rts',
            '.endproc',
            ''
        ])

    def _emit_dpcm_proc(self, lines, mapper, table_bank, bank_size):
        """Emit the play_dpcm playback subroutine. Mirrors audio_engine.asm
        @write_dpcm: trigger a one-shot sample on a new note
        (sample_id = note-1), reusing the packer sample tables."""
        lines.extend([
            '.proc play_dpcm',
            '    ; Index dpcm_note[frame_counter]',
        ])
        lines.extend(self._emit_table_read_lines('dpcm_note', mapper, table_bank))
        lines.extend([
            '    cmp last_dpcm_note',
        ])
        lines.extend(self._emit_safe_beq('@done', 'dpcm_unchanged', bank_size,
                                          '; unchanged - sample already triggered'))
        lines.extend([
            '    sta last_dpcm_note   ; NB: STA does not affect Z',
            '    cmp #0               ; re-test the note (A still holds it); STA left the stale CMP flags (#66)',
        ])
        lines.extend(self._emit_safe_beq('@done', 'dpcm_rest', bank_size,
                                          '; note 0 (rest) -> nothing to trigger, no dpcm_*_table[$FF] over-read'))
        lines.extend([
            '    ; New sample: sample_id = note - 1',
            '    sec',
            '    sbc #1',
            '    tay',
            '    ; A $00 length_reg means this dense id was never packed',
            '    ; (its .dmc file was missing at pack time, #367/DP-DPCM-05)',
            '    ; -- skip the trigger so we don\'t read a stray 1-byte',
            '    ; fragment of bank 0 / $C000 in place of the intended drum.',
            '    lda dpcm_len_table,y',
        ])
        lines.extend(self._emit_safe_beq('@done', 'dpcm_unpacked', bank_size,
                                          '; sample was never packed (missing .dmc)'))
        lines.extend([
            '    ; Stop DPCM to reset the byte counter',
            '    lda #$0F',
            '    sta $4015',
            '    ; MMC3: swap DPCM sample bank into $C000 (R6)',
            '    lda #$46',
            '    sta $8000',
            '    lda dpcm_bank_table,y',
            '    sta $8001',
            '    ; Load sample parameters',
            '    lda dpcm_pitch_table,y',
            '    sta $4010',
            '    lda dpcm_addr_table,y',
            '    sta $4012',
            '    lda dpcm_len_table,y',
            '    sta $4013',
            '    ; Trigger playback (enable DMC, bit 4)',
            '    lda #$1F',
            '    sta $4015',
            '@done:',
            '    rts',
            '.endproc',
            ''
        ])

    def export_direct_frames(self, frames, output_path, standalone=True, mapper=None,
                              visualizer=False):
        """Export frames data directly using efficient lookup tables.

        ``mapper`` selects the iNES header emitted for a standalone ROM; it
        defaults to the pipeline default (MMC3) so the header matches the
        project's linker config instead of hardcoding MMC1 (#36).

        ``visualizer`` (--visualizer, see nes/visualizer.py): when True, each
        channel proc below also snapshots the volume nibble it just wrote
        into `channel_vis_vol` for the on-screen bar UI to read -- the APU is
        write-only, so this is the only way that UI can know a channel's
        current volume. No-op / no added bytes when False (default).
        """
        print("🔧 CA65 Exporter: Direct frame export mode (table-based)")

        lines = []
        lines.append("; CA65 Assembly Export (Direct Frame Data)")
        lines.append("; Generated by MIDI2NES - Optimized Table-Based Exporter")
        # Marker so a later prepare/compile step (via main.resolve_mapper) can
        # detect that these frame tables were bin-packed into RODATA_BANK_NN
        # segments only this mapper's linker config defines, and force/reject a
        # mismatched --mapper up front instead of deferring to a raw ld65
        # "Missing memory area assignment" error — mirrors the "MMC3 Macro
        # Bytecode" marker guarding the bytecode path (#283/MAP-2026-07-05B-3,
        # #285/PL-09). Only banked mappers (MMC1) bin-pack; MMC3/NROM don't.
        if mapper is not None and mapper.direct_export_bank_size() is not None:
            lines.append(f"; Direct export bank-packed for {mapper.name}")
        # A direct-export song with DPCM samples is MMC3-only: play_dpcm writes
        # MMC3's $8000/$8001 bank-select ports and DpcmPacker (appended to this
        # music.asm downstream) emits DPCM_NN segments only MMC3's linker config
        # defines. The in-memory export/full-pipeline paths enforce this via
        # main.enforce_direct_export_dpcm_mapper, but the split prepare/compile
        # flow only sees the finished music.asm — stamp a marker so
        # main.resolve_mapper can re-force MMC3 / reject a non-MMC3 --mapper up
        # front instead of deferring to a raw ld65 "Missing memory area
        # assignment for DPCM_00" at link time (#362/MAP-2026-07-19-2). Mirrors
        # the bank-pack marker above and the "MMC3 Macro Bytecode" bytecode marker.
        if frames.get('dpcm'):
            lines.append("; Direct export DPCM (MMC3-only)")
        lines.append("")

        # Add header segment if standalone, derived from the selected mapper so
        # the declared mapper/PRG size tracks the actual build (#36).
        if standalone:
            if mapper is None:
                from mappers.mmc3 import MMC3Mapper
                mapper = MMC3Mapper()
            header_asm = mapper.generate_header_asm()
            # All mappers (NROM/MMC1/MMC3) return bare `.byte` header rows;
            # this exporter is the sole owner of `.segment "HEADER"` (#22,
            # #216/MAP-5 -- a stale comment here used to claim MMC3 embedded
            # its own segment, which is no longer true for any mapper).
            lines.append('.segment "HEADER"')
            lines.append(header_asm)
            lines.append('')

        # Zero page variables
        if not standalone:
            # Import zeropage from main.asm
            lines.append('.importzp frame_counter, temp_ptr')
            lines.append('')
        else:
            # Define our own zeropage
            lines.append('.segment "ZEROPAGE"')
            lines.append('frame_counter: .res 2')
            lines.append('temp_ptr: .res 2')
            lines.append('')

        # --visualizer's channel_vis_vol (see nes/visualizer.py): a plain
        # (non-zeropage) BSS array, one byte per non-DPCM channel. Owned by
        # main.asm and imported here in the normal (project-builder-managed)
        # case; a standalone export has no main.asm partner, so it reserves
        # its own copy instead.
        if visualizer:
            if not standalone:
                lines.append('.import channel_vis_vol')
                lines.append('')
            else:
                lines.append('.segment "BSS"')
                lines.append('channel_vis_vol: .res 4')
                lines.append('')

        # BSS segment for last note tracking (prevents buzzing)
        lines.append('.segment "BSS"')
        lines.append('last_pulse1_note: .res 1')
        lines.append('last_pulse2_note: .res 1')
        lines.append('last_triangle_note: .res 1')
        lines.append('last_dpcm_note: .res 1')
        lines.append('')

        # Get all channels and find maximum frame
        all_channels = {}
        max_frame = 0

        for channel_name, channel_data in frames.items():
            # `dpcm_sample_map` (#200/D-14) is a dense_id -> catalog_id side
            # table, not a per-frame channel.
            if channel_name == 'dpcm_sample_map':
                continue
            if channel_data:  # Skip empty channels
                all_channels[channel_name] = channel_data
                channel_max = max(int(f) for f in channel_data.keys())
                max_frame = max(max_frame, channel_max)

        print(f"  Channels: {list(all_channels.keys())}")
        print(f"  Max frame: {max_frame}")
        print(f"  Total frames to export: {max_frame + 1}")

        # The frame tables hold `frame_count` entries (indices 0..max_frame).
        # The runtime range check and loop-reset guards below must compare
        # frame_counter against this EXCLUSIVE upper bound, not max_frame
        # itself -- comparing against max_frame treated frame_counter ==
        # max_frame as already out of range, so the last frame (and, for a
        # single-frame song where max_frame == 0, the ONLY frame) never
        # played (#430/NH-HW-2026-08-21-2).
        frame_count = max_frame + 1

        # Bank-pack frame tables if the mapper's switchable window is smaller
        # than the aggregate PRG pool (MMC1, #255/MAP-2026-07-05-1). All tables
        # are exactly max_frame + 1 bytes, so the table names alone (in emission
        # order) are enough to compute bank assignment before any are written.
        bank_size = mapper.direct_export_bank_size() if mapper is not None else None
        table_names = []
        for channel_name in ['pulse1', 'pulse2', 'triangle']:
            if channel_name in all_channels:
                table_names.extend([f'{channel_name}_note', f'{channel_name}_control',
                                     f'{channel_name}_timer_lo', f'{channel_name}_timer_hi'])
        has_noise = 'noise' in all_channels
        if has_noise:
            table_names.extend(['noise_note', 'noise_ctrl', 'noise_reg'])
        has_dpcm = 'dpcm' in all_channels
        if has_dpcm:
            table_names.append('dpcm_note')

        table_bank = {}
        if bank_size is not None:
            table_bank = self._pack_direct_tables_into_banks(table_names, max_frame + 1, bank_size)

        # Generate ROM data segment(s) with frame tables. When bank-packed,
        # segment switches are interleaved with table emission below instead
        # of one segment up front, since different tables can land in
        # different banks.
        current_segment = ['']  # mutable cell for the nested closure below

        def _ensure_segment(table_name):
            target = f'RODATA_BANK_{table_bank[table_name]:02d}' if table_name in table_bank else 'RODATA'
            if target != current_segment[0]:
                lines.append(f'.segment "{target}"')
                lines.append('')
                current_segment[0] = target

        if bank_size is None:
            lines.append('.segment "RODATA"')
            lines.append('')
            current_segment[0] = 'RODATA'

        def _emit_byte_table(label, values):
            _ensure_segment(label)
            lines.append(f'{label}:')
            for i in range(0, len(values), 16):
                lines.append(f'    .byte {", ".join(values[i:i+16])}')

        # Create sparse frame lookup tables for each channel (#136/TD-11:
        # extracted to _emit_pulse_or_triangle_table/_emit_noise_table/
        # _emit_dpcm_table -- see the comment above those methods).
        # Format: For each active frame, store (note, control_byte, timer_lo, timer_hi)
        for channel_name in ['pulse1', 'pulse2', 'triangle']:
            if channel_name not in all_channels:
                continue
            self._emit_pulse_or_triangle_table(
                lines, channel_name, all_channels[channel_name], max_frame, _ensure_segment)

        if has_noise:
            self._emit_noise_table(lines, all_channels['noise'], max_frame, _emit_byte_table)

        if has_dpcm:
            self._emit_dpcm_table(lines, all_channels['dpcm'], max_frame, _emit_byte_table)

        # Code segment with efficient playback routine
        lines.append('.segment "CODE"')
        lines.append('')
        # NOTE: the DPCM sample tables (dpcm_bank_table/pitch/addr/len) are NOT
        # imported here. They are appended to THIS music.asm by the DPCM packer
        # (or stubbed by the project builder, which guarantees they exist), so the
        # trigger code below references them as local labels. Importing a symbol
        # the same module also defines is a ca65 "already an import" error — the
        # collision that surfaced once DPCM actually packs (#140). The project
        # builder adds the `.export` that makes them visible to other modules.

        # Add reset routine ONLY if standalone
        if standalone:
            lines.extend([
            '.proc reset',
            '    ; Standard NES initialization',
            '    sei',
            '    cld',
            '    ldx #$FF',
            '    txs',
            '    ',
            '    ; PPU warmup',
            '    bit $2002',
            '@wait_vbl1:',
            '    bit $2002',
            '    bpl @wait_vbl1',
            '@wait_vbl2:',
            '    bit $2002',
            '    bpl @wait_vbl2',
            '    ',
            '    ; APU initialization',
            '    lda #$00',
            '    sta $4015',
            '    ; Zero the DMC output level so a soft reset cannot leave it at a',
            '    ; stale nonzero value, which would muffle Triangle/Noise via the',
            '    ; non-linear mixer (docs/APU_DMC_REFERENCE.md §5).',
            '    sta $4011',
            '    lda #$40',
            '    sta $4017',
            '    lda #$0F',
            '    sta $4015',
            '    ; Disable both sweep units so power-on garbage cannot bend or',
            '    ; silence the pulse channels (docs/APU_PULSE_REFERENCE.md §1, §5).',
            '    lda #$08',
            '    sta $4001',
            '    sta $4005',
            '    ',
            '    ; Initialize frame counter',
            '    lda #$00',
            '    sta frame_counter',
            '    sta frame_counter+1',
            '    ',
            '    ; Seed last_*_note with an impossible value ($FF -- MIDI notes are',
            "    ; 0-127) so the 'note changed' check in play_pulse1/play_pulse2/",
            "    ; play_triangle below always fires on each channel's first frame.",
            '    ; Without this, these BSS bytes hold power-on garbage on real',
            "    ; hardware; if garbage happens to equal a channel's first note, that",
            '    ; note is silently skipped until the next note change',
            "    ; (#432/NH-HW-2026-08-21-5). Mirrors audio_engine.asm's",
            '    ; last_written_hi init.',
            '    lda #$FF',
            '    sta last_pulse1_note',
            '    sta last_pulse2_note',
            '    sta last_triangle_note',
            '    ; last_dpcm_note is NOT a MIDI note -- it is min(255, dense_id + 1)',
            "    ; (nes/emulator_core.py), and direct-export's 255-distinct-sample",
            '    ; ceiling (docs/APU_DMC_REFERENCE.md §6) means $FF (255) is a real,',
            '    ; reachable first-trigger value, unlike the tone channels above. $00',
            '    ; is the correct "impossible" seed here instead: note 0 is the',
            '    ; reserved rest/no-trigger sentinel on this channel (never a real',
            '    ; sample), and play_dpcm already re-tests for it explicitly',
            '    ; (#107/NH-14), so seeding last_dpcm_note=$00 reads as "nothing',
            '    ; playing yet", which is true at power-on and cannot alias a genuine',
            '    ; sample trigger (#482/NH-HW-2026-08-22-2).',
            '    lda #$00',
            '    sta last_dpcm_note',
            '    ',
            '    ; Enable NMI',
            '    lda #$80',
            '    sta $2000',
            '    ',
            '@main_loop:',
            '    jmp @main_loop',
            '.endproc',
            '',
            '.proc nmi',
            '    ; Save registers',
            '    pha',
            '    txa',
            '    pha',
            '    tya',
            '    pha',
            '    ',
            '    ; Play current frame',
            '    jsr play_music_frame',
            '    ',
            '    ; Increment frame counter',
            '    inc frame_counter',
            '    bne @no_carry',
            '    inc frame_counter+1',
            '@no_carry:',
            '    ',
            '    ; Check for song end and loop (reset once frame_counter reaches',
            '    ; frame_count, NOT max_frame -- frame_counter == max_frame is still',
            '    ; the last valid frame and must play before looping, #430)',
            f'    lda frame_counter+1',
            f'    cmp #>{frame_count}',
            f'    bcc @no_loop',
            f'    bne @loop_song',
            f'    lda frame_counter',
            f'    cmp #<{frame_count}',
            f'    bcc @no_loop',
            '@loop_song:',
            '    lda #$00',
            '    sta frame_counter',
            '    sta frame_counter+1',
            '@no_loop:',
            '    ; Restore registers',
            '    pla',
            '    tay',
            '    pla',
            '    tax',
            '    pla',
            '    rti',
            '.endproc',
            ''
            ])

        # Efficient table-based playback routine with 16-bit addressing
        lines.append('.proc play_music_frame')
        lines.append('    ; Check if frame is within range (frame_counter < frame_count,')
        lines.append('    ; i.e. frame_counter <= max_frame -- the last table entry at')
        lines.append('    ; index max_frame must still play, #430/NH-HW-2026-08-21-2)')
        lines.append(f'    lda frame_counter+1')
        lines.append(f'    cmp #>{frame_count}')
        lines.append('    bcc @in_range')
        lines.append('    bne @done')
        lines.append(f'    lda frame_counter')
        lines.append(f'    cmp #<{frame_count}')
        lines.append('    bcs @done')
        lines.append('@in_range:')
        lines.append('')

        # Generate playback code for each channel with 16-bit indexing
        if 'pulse1' in all_channels:
            lines.extend([
                '    ; === PULSE1 CHANNEL ===',
                '    jsr play_pulse1',
                ''
            ])

        if 'pulse2' in all_channels:
            lines.extend([
                '    ; === PULSE2 CHANNEL ===',
                '    jsr play_pulse2',
                ''
            ])

        if 'triangle' in all_channels:
            lines.extend([
                '    ; === TRIANGLE CHANNEL ===',
                '    jsr play_triangle',
                ''
            ])

        if has_noise:
            lines.extend([
                '    ; === NOISE CHANNEL ===',
                '    jsr play_noise',
                ''
            ])

        if has_dpcm:
            lines.extend([
                '    ; === DPCM CHANNEL ===',
                '    jsr play_dpcm',
                ''
            ])

        lines.extend([
            '@done:',
            '    rts',
            '.endproc',
            ''
        ])

        # Add channel-specific playback subroutines (#136/TD-11: extracted
        # to _emit_pulse1_proc/_emit_pulse2_proc/_emit_triangle_proc/
        # _emit_noise_proc/_emit_dpcm_proc -- see the comment above those
        # methods; pulse1/pulse2 keep their historical comment asymmetry
        # verbatim so the emitted bytes are unchanged).
        if 'pulse1' in all_channels:
            self._emit_pulse1_proc(lines, mapper, table_bank, bank_size, visualizer)

        if 'pulse2' in all_channels:
            self._emit_pulse2_proc(lines, mapper, table_bank, bank_size, visualizer)

        if 'triangle' in all_channels:
            self._emit_triangle_proc(lines, mapper, table_bank, bank_size, visualizer)

        if has_noise:
            self._emit_noise_proc(lines, mapper, table_bank, bank_size, visualizer)

        if has_dpcm:
            self._emit_dpcm_proc(lines, mapper, table_bank, bank_size)

        lines.extend([
            '.proc irq',
            '    rti',
            '.endproc'
        ])
        
        # Add project builder compatible functions if not standalone
        if not standalone:
            lines.extend([
                '',
                '; Project builder compatible functions',
                '.global init_music',
                '.global update_music',
                '',
                'init_music:',
                '    ; Initialize APU for music playback',
                '    lda #$00',
                '    sta $4011  ; Zero the DMC output level so a soft reset cannot leave it',
                '               ; at a stale nonzero value, which would muffle Triangle/Noise',
                '               ; via the non-linear mixer (docs/APU_DMC_REFERENCE.md §5)',
                '    lda #$40',
                '    sta $4017  ; Frame counter 4-step mode (mode 0), disable frame IRQ (NES_APU_REFERENCE 3.2)',
                '    lda #$0F',
                '    sta $4015  ; Enable all channels',
                '    lda #$08    ; Disable sweep units (APU_PULSE_REFERENCE §1, §5)',
                '    sta $4001   ; Pulse1 sweep off',
                '    sta $4005   ; Pulse2 sweep off',
                '    lda #$00',
                '    sta frame_counter',
                '    sta frame_counter+1',
                '    ; Seed last_*_note with an impossible value ($FF -- MIDI notes',
                "    ; are 0-127) so each channel's first-frame note change is never",
                '    ; mistaken for a sustain against power-on RAM garbage',
                '    ; (#432/NH-HW-2026-08-21-5). Mirrors the standalone reset proc',
                "    ; above and audio_engine.asm's last_written_hi init.",
                '    lda #$FF',
                '    sta last_pulse1_note',
                '    sta last_pulse2_note',
                '    sta last_triangle_note',
                '    ; last_dpcm_note seeds $00, not $FF -- $FF (255) is a real,',
                '    ; reachable DPCM note (min(255, dense_id+1)), unlike a MIDI',
                '    ; pitch; $00 is DPCM\'s actual rest/no-trigger sentinel, matching',
                '    ; power-on "nothing playing yet" (#482/NH-HW-2026-08-22-2).',
                '    lda #$00',
                '    sta last_dpcm_note',
                '    rts',
                '',
                'update_music:',
                '    ; Update music frame (called from NMI)',
                '    jsr play_music_frame',
                '    ',
                '    ; Increment frame counter',
                '    inc frame_counter',
                '    bne @no_carry',
                '    inc frame_counter+1',
                '@no_carry:',
                '    ',
                '    ; Check for song end and loop (reset once frame_counter reaches',
                '    ; frame_count, NOT max_frame -- frame_counter == max_frame is still',
                '    ; the last valid frame and must play before looping, #430)',
                f'    lda frame_counter+1',
                f'    cmp #>{frame_count}',
                f'    bcc @no_loop',
                f'    bne @loop_song',
                f'    lda frame_counter',
                f'    cmp #<{frame_count}',
                f'    bcc @no_loop',
                '@loop_song:',
                '    lda #$00',
                '    sta frame_counter',
                '    sta frame_counter+1',
                '@no_loop:',
                '    rts'
            ])
        
        # Add vectors if standalone
        if standalone:
            lines.append('')
            lines.append('.segment "VECTORS"')
            lines.append('    .word nmi')
            lines.append('    .word reset')
            lines.append('    .word irq')

        # Write assembly file atomically (#385/SAFE-2026-07-19-3): a failed
        # write (disk full, killed process) must never leave a truncated
        # .asm at output_path or overwrite a prior good one with a partial
        # write.
        atomic_write_text(output_path, '\n'.join(lines))

        # Reuse the same per-channel accounting estimate_direct_export_size
        # uses (4 bytes/frame for pulse/triangle, 3 for noise, 1 for dpcm) --
        # a flat `* 4 * len(all_channels)` overstated the total whenever
        # noise or dpcm was active (e.g. +25% on a 5-channel song, #444/
        # EXP-2026-08-21-9). Nothing downstream consumes this printed
        # number; it's purely cosmetic, but must not contradict the
        # estimator that capacity decisions actually rely on.
        total_bytes = self.estimate_direct_export_size(frames)
        print(f"✅ Table-based export complete: {output_path}")
        print(f"   Data size: {total_bytes:,} bytes ({total_bytes/1024:.1f} KB)")
        print(f"   Channels exported: {', '.join(all_channels.keys())}")

        return output_path

    @staticmethod
    def _register_instrument(inst, instruments, instrument_defs):
        """Look up or assign an instrument id, guarding the engine's actual
        addressable range (#425/NH-HW-2026-08-21-1 supersedes the >256
        single-byte-operand guard this replaced -- #80/EXP-04): each
        instrument occupies 8 bytes of `instrument_table` and the bytecode
        engine (nes/audio_engine.asm's EVAL_MACRO) computes the row offset
        as `current_inst * 8` with an 8-bit accumulator/Y-register, so only
        32 instruments (ids 0-31) are actually reachable -- id 32 silently
        aliases to id 0's macro pointers, id 33 to id 1's, etc., with no
        error on either side of the contract. Raises rather than emitting
        an id the engine will misread.
        """
        if inst not in instruments:
            new_id = len(instrument_defs)
            if new_id > 0x1F:
                raise ValueError(
                    "Too many unique instruments (>32 distinct volume/arp/"
                    "pitch/duty combinations) -- the bytecode engine's "
                    "8-bit instrument-table indexing (nes/audio_engine.asm) "
                    "can only address instrument ids 0-31. Reduce timbre "
                    "variety, split the song, or use --no-patterns for "
                    "full-fidelity direct export."
                )
            instruments[inst] = new_id
            instrument_defs.append(inst)
        return instruments[inst]

    def _compress_macro(self, data):
        """
        Compresses a macro list (volume, pitch, duty) using $FF (sustain).

        $FE (loop) is part of the documented bytecode contract
        (docs/AUDIO_BYTECODE_SPEC.md §2.3) but the live EVAL_MACRO evaluator
        in nes/audio_engine.asm only implements $FF -- it has no branch for
        $FE at all, so a $FE byte is read as ordinary data and the following
        loop_start operand is consumed as the next frame's value, desyncing
        the stream. Sustain compression alone is a strict subset of what the
        engine can decode, so loop compression is intentionally not
        attempted here (#163/NH-21) rather than emitting a format the
        engine cannot honor.
        """
        if not data:
            return [0xFF]

        n = len(data)

        # Baseline: No compression, just end with $FF (sustain)
        best_compression = data + [0xFF]
        best_len = len(best_compression)

        # Try Sustain Compression ($FF)
        # E.g., [15, 14, 13, 10, 10, 10, 10] -> [15, 14, 13, 10, 0xFF]
        sustain_idx = n - 1
        while sustain_idx > 0 and data[sustain_idx - 1] == data[-1]:
            sustain_idx -= 1

        sustain_comp = data[:sustain_idx + 1] + [0xFF]
        if len(sustain_comp) < best_len:
            best_compression = sustain_comp
            best_len = len(sustain_comp)

        return best_compression

    # Channel order used throughout the bytecode engine -- sequence labels,
    # channel_start_banks/song_table entries, and the engine's stream_*, x
    # arrays (nes/audio_engine.asm) all index 0..4 in this order.
    SEQUENCE_CHANNELS = ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']

    def _emit_period_tables(self, lines):
        """Append the shared pulse/triangle pitch lookup tables.

        Generated from the single authoritative per-channel tables so the
        runtime base period matches the base_timer the pitch offset was
        computed against (#16) — keeping them as separate hardcoded copies
        is exactly how they drifted an octave apart. The triangle channel
        needs its own /32 table or it plays an octave low (#12).

        These are pure hardware constant tables, not derived from any song's
        `frames` -- identical for every song, so a multi-song build emits
        them exactly once (see `export_song_bank_bytecode`) rather than once
        per song.
        """
        def _emit_period_table(label, table, byte_of):
            lines.append(f'{label}:')
            for row_start in range(0, 128, 8):
                row = ', '.join(
                    f'${byte_of(table[n]):02x}'
                    for n in range(row_start, row_start + 8)
                )
                lines.append(f'  .byte {row}')
            lines.append('')

        lines.append('; The 128-byte Pitch Lookup Tables (pulse: /16)')
        _emit_period_table('ntsc_period_low', NES_NOTE_TABLE, lambda p: p & 0xFF)
        _emit_period_table('ntsc_period_high', NES_NOTE_TABLE, lambda p: (p >> 8) & 0xFF)
        lines.append('; Triangle Pitch Lookup Tables (/32 — an octave below pulse for the same timer)')
        _emit_period_table('triangle_period_low', NES_TRIANGLE_TABLE, lambda p: p & 0xFF)
        _emit_period_table('triangle_period_high', NES_TRIANGLE_TABLE, lambda p: (p >> 8) & 0xFF)

    def _build_song_bytecode(self, frames, label_prefix='', start_bank=0):
        """Serialize one song's per-channel frames into MMC3 macro-bytecode.

        Walks `frames` into per-channel note/duration events, de-duplicates
        them into volume/arp/pitch/duty macros and instruments, and emits
        the instrument table, macro byte streams, and banked sequence
        bytecode for all 5 channels (`SEQUENCE_CHANNELS`).

        `label_prefix` is prepended to every symbol this song defines
        (`instrument_table`, `macro_*`, and each channel's `*_sequence` /
        bank-jump labels) so a multi-song build's N songs can coexist in one
        music.asm without colliding ca65 symbol names (#30/F-13). The
        single-song caller (`export_tables_with_patterns`) passes `''` --
        byte-identical output to before this was extracted.

        `start_bank` is the first `BANK_NN` this song's sequence data may
        use. Returns `next_bank = <song's last used bank> + 1` -- a
        multi-song caller always starts the following song in a fresh bank
        rather than packing two songs' sequence bytes into the same
        `BANK_NN` segment, since this function's own `bytes_in_current_bank`
        accounting (and its overflow check against `MAX_SEQUENCE_BANK`) only
        tracks bytes *within this call*; sharing a bank across calls would
        silently desync that accounting from ca65's real per-segment size.

        Returns `(lines, next_bank, channel_start_banks, notes_clamped)`.
        `channel_start_banks` maps channel name -> the `BANK_NN` index its
        `{label_prefix}{channel}_sequence` label physically landed in (a
        later channel's label can spill past the bank the song started in).
        `notes_clamped` is `{'high': N, 'low': N}`, the tone-range clamp
        tally for this song (#298/EXP-10).
        """
        lines = []

        def optimize_macro(seq):
            return tuple(self._compress_macro(seq))

        vol_macros = {(0xFF,): 0}
        vol_macro_defs = [(0xFF,)]
        duty_macros = {(0xFF,): 0}
        duty_macro_defs = [(0xFF,)]
        arp_macros = {(0xFF,): 0}
        arp_macro_defs = [(0xFF,)]
        pitch_macros = {(0xFF,): 0}
        pitch_macro_defs = [(0xFF,)]

        instruments = {(0, 0, 0, 0): 0}
        instrument_defs = [(0, 0, 0, 0)]

        channel_events = {ch: [] for ch in self.SEQUENCE_CHANNELS}

        # Count tone-channel notes re-pitched by the range clamp below so the
        # loss is reported instead of silently altering pitch (#298/EXP-10).
        notes_clamped_high = 0  # note > 95 (above B6)
        notes_clamped_low = 0   # 0 < note < 24 (below C1, tone channels)

        for channel in self.SEQUENCE_CHANNELS:
            if channel not in frames or not frames[channel]:
                continue

            channel_frames = frames[channel]
            max_frame = max(int(f) for f in channel_frames.keys()) if channel_frames else -1

            current_note = 0
            current_event = None
            prev_orig_note = None  # last frame's pre-clamp source note (#298)

            for frame_idx in range(max_frame + 1):
                frame_data = channel_frames.get(str(frame_idx), channel_frames.get(frame_idx))
                note = frame_data.get('note', 0) if frame_data else 0
                # Every in-pipeline producer already clamps volume to 0-15,
                # but this JSON is user-editable (the step-by-step `export`
                # CLI), and vol_seq bytes -- unlike pitch/arp, which route
                # through _encode_macro_offset (#77) -- were emitted raw. A
                # volume >= $FE collides with the reserved end-of-macro/loop
                # control bytes: $FF as the first macro byte reads as
                # end-at-step-0, silently playing the null default (15)
                # instead of the value asked for (#442/EXP-2026-08-21-7).
                # Clamp to the spec's stated 0-15 domain (docs/
                # AUDIO_BYTECODE_SPEC.md §2.3), matching the pitch/arp guard.
                vol = max(0, min(15, frame_data.get('volume', 0))) if frame_data else 0
                control = frame_data.get('control', 0x80) if frame_data else 0x80
                duty = (control >> 6) & 0x03

                if frame_data and vol == 0:
                    note = 0
                    
                # The DPCM channel's `note` is sample_id + 1, not a MIDI note, so
                # it is NOT bounded by the 0-95 tone-note range -- clamping it to
                # 95 collapsed high-id drums to one wrong sample (#67). But it
                # cannot simply grow up to the single-byte ceiling (255) either:
                # DPCM events are emitted through the *same* length+note
                # serializer as tone channels (`.byte $6X, note`, see the
                # sequence-bytecode loop below), and the engine's @read_next
                # dispatcher (nes/audio_engine.asm) re-reads every stream byte by
                # range -- only `< $60` is a note; `$60-$7F` is Length and `>=
                # $80` is a Command. A DPCM note >= $60 (sample_id >= 95) would
                # be misdispatched as a Length or Command byte, desyncing the
                # entire DPCM stream from that point on, not just misplaying one
                # hit (#369/EXP-2026-07-19-1). Fail loudly instead -- mirroring
                # the bank-budget ValueError above -- rather than silently
                # emitting a stream that decodes to garbage; the direct-export
                # path has no such ceiling (its DPCM notes live in a dedicated
                # byte table read by index, never re-dispatched), so only the
                # bytecode path is limited: note must stay <= $5F (95), i.e.
                # sample_id <= 94, so at most 95 distinct DPCM samples per song
                # (ids 0-94).
                orig_note = note
                if channel == 'dpcm':
                    if note >= 0x60:
                        raise ValueError(
                            f"DPCM sample id {note - 1} (note ${note:02X}) exceeds the "
                            f"macro-bytecode engine's $00-$5F note range -- the "
                            f"sequence-bytecode dispatcher would misread it as a Length "
                            f"or Command byte, desyncing the DPCM stream. The bytecode "
                            f"path supports at most 95 distinct DPCM samples per song "
                            f"(sample ids 0-94); use --no-patterns (direct export) or "
                            f"reduce the sample count."
                        )
                elif note > 95:
                    note = 95
                elif channel != 'noise' and 0 < note < 24:
                    # Tone channels only: clamp the note baked into the
                    # instruction stream (and later fed to
                    # midi_note_to_timer_value) to the same floor the frame
                    # `pitch` was already clamped to, so the runtime base-period
                    # lookup and the pitch offset agree on the same note (#158).
                    # `noise`'s "note" is a 4-bit period index, not a MIDI note —
                    # clamping it here would corrupt the drum pitch.
                    note = 24

                # Report a tone-channel re-pitch once per distinct source note
                # (keyed on the pre-clamp value, not the collapsed played note)
                # so a sustained note counts once but two adjacent out-of-range
                # notes that clamp to the same boundary each count (#298/EXP-10).
                # dpcm's "note" is a sample id, not a pitch, so it is excluded.
                if (channel != 'dpcm' and note != orig_note
                        and orig_note != prev_orig_note):
                    if orig_note > 95:
                        notes_clamped_high += 1
                    else:
                        notes_clamped_low += 1
                prev_orig_note = orig_note

                if note != current_note:
                    if current_event is not None:
                        if current_event['note'] > 0:
                            v_seq = optimize_macro(current_event['vol_seq'])
                            d_seq = optimize_macro(current_event['duty_seq'])
                            p_seq = optimize_macro(current_event['pitch_seq'])
                            a_seq = optimize_macro(current_event['arp_seq'])
                            
                            if v_seq not in vol_macros:
                                vol_macros[v_seq] = len(vol_macro_defs)
                                vol_macro_defs.append(v_seq)
                            if d_seq not in duty_macros:
                                duty_macros[d_seq] = len(duty_macro_defs)
                                duty_macro_defs.append(d_seq)
                            if p_seq not in pitch_macros:
                                pitch_macros[p_seq] = len(pitch_macro_defs)
                                pitch_macro_defs.append(p_seq)
                            if a_seq not in arp_macros:
                                arp_macros[a_seq] = len(arp_macro_defs)
                                arp_macro_defs.append(a_seq)
                                
                            inst = (vol_macros[v_seq], arp_macros[a_seq], pitch_macros[p_seq], duty_macros[d_seq])
                            current_event['inst_id'] = self._register_instrument(
                                inst, instruments, instrument_defs)
                        channel_events[channel].append(current_event)

                    current_note = note
                    if note > 0:
                        base_timer = self.midi_note_to_timer_value(note, channel)
                        pitch_val = frame_data.get('pitch', base_timer) if frame_data else base_timer
                        pitch_offset = self._encode_macro_offset(pitch_val - base_timer)
                        # No pipeline stage emits an 'arp' key, so the arp macro is
                        # always the neutral offset — still emitted so each instrument
                        # keeps its 4 macro pointers (vol/arp/pitch/duty) (#166).
                        arp_val = self._encode_macro_offset(0)
                        current_event = {'note': note, 'dur': 1, 'vol_seq': [vol], 'duty_seq': [duty], 'pitch_seq': [pitch_offset], 'arp_seq': [arp_val]}
                    else:
                        current_event = {'note': 0, 'dur': 1}

                else:
                    if current_event is not None:
                        current_event['dur'] += 1
                        if note > 0:
                            # Continuation frames must use the same per-channel
                            # table as the first frame (:990) — omitting channel
                            # here defaults triangle to the pulse table and bends
                            # every sustained triangle note (#78).
                            base_timer = self.midi_note_to_timer_value(note, channel)
                            pitch_val = frame_data.get('pitch', base_timer) if frame_data else base_timer
                            pitch_offset = self._encode_macro_offset(pitch_val - base_timer)
                            arp_val = self._encode_macro_offset(0)  # no 'arp' producer (#166)
                            current_event['vol_seq'].append(vol)
                            current_event['duty_seq'].append(duty)
                            current_event['pitch_seq'].append(pitch_offset)
                            current_event['arp_seq'].append(arp_val)

            if current_event is not None:
                if current_event['note'] > 0:
                    v_seq = optimize_macro(current_event['vol_seq'])
                    d_seq = optimize_macro(current_event['duty_seq'])
                    p_seq = optimize_macro(current_event['pitch_seq'])
                    a_seq = optimize_macro(current_event['arp_seq'])
                    
                    if v_seq not in vol_macros:
                        vol_macros[v_seq] = len(vol_macro_defs)
                        vol_macro_defs.append(v_seq)
                    if d_seq not in duty_macros:
                        duty_macros[d_seq] = len(duty_macro_defs)
                        duty_macro_defs.append(d_seq)
                    if p_seq not in pitch_macros:
                        pitch_macros[p_seq] = len(pitch_macro_defs)
                        pitch_macro_defs.append(p_seq)
                    if a_seq not in arp_macros:
                        arp_macros[a_seq] = len(arp_macro_defs)
                        arp_macro_defs.append(a_seq)
                        
                    inst = (vol_macros[v_seq], arp_macros[a_seq], pitch_macros[p_seq], duty_macros[d_seq])
                    current_event['inst_id'] = self._register_instrument(
                        inst, instruments, instrument_defs)
                channel_events[channel].append(current_event)

        # Explicit re-declaration (#30/F-13, MAP-2026-08-07-1): this method
        # is called once per song by a multi-song build, and each call's
        # sequence-bytecode loop below leaves the assembler in whatever
        # `.segment "BANK_NN"` its last channel used. Without this, the
        # *next* song's instrument_table/macro tables silently land inside
        # that leftover dynamically-banked segment instead of the fixed,
        # always-mapped CODE_8000 region -- the ROM still links and boots
        # (BANK_NN is a valid segment), but at runtime, with R7 pointed
        # anywhere other than that exact bank, every macro read for that
        # song pulls garbage bytes. The single-song caller
        # (export_tables_with_patterns) already has CODE_8000 active at
        # this point (from its own header emission), so this is a no-op
        # there -- redeclaring an already-active ca65 segment costs nothing
        # and changes no emitted bytes.
        lines.append('.segment "CODE_8000"')
        lines.append('; The Instrument Macro Pointers')
        lines.append(f'{label_prefix}instrument_table:')
        for inst in instrument_defs:
            v_id, a_id, p_id, d_id = inst
            lines.append(f'    .word {label_prefix}macro_vol_{v_id}, {label_prefix}macro_arp_{a_id}, '
                          f'{label_prefix}macro_pitch_{p_id}, {label_prefix}macro_duty_{d_id}')
        lines.append('')

        for name, defs in [('vol', vol_macro_defs), ('arp', arp_macro_defs), ('pitch', pitch_macro_defs), ('duty', duty_macro_defs)]:
            lines.append(f'; --- {name.capitalize()} Macros ---')
            for i, seq in enumerate(defs):
                lines.append(f'{label_prefix}macro_{name}_{i}:')
                lines.append('    .byte ' + ', '.join(f'${val:02X}' for val in seq))
            lines.append('')

        # Bytecode generation for channels
        from mappers.mmc3 import MMC3Mapper
        # Highest swap-bank index the MMC3 linker config defines (BANK_00..N-1).
        # Rolling past it would emit a .segment ld65 has no MEMORY region for (#127).
        MAX_SEQUENCE_BANK = MMC3Mapper.SWAP_BANK_COUNT - 1
        current_bank = start_bank
        bytes_in_current_bank = 0
        BANK_SIZE_LIMIT = 8192 - 256  # 8KB minus a safety margin

        lines.append('; ---------------------------------------------------------------------------')
        lines.append('; Sequence Data (Dynamically Banked)')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append(f'.segment "BANK_{current_bank:02d}"')
        lines.append('')

        # The bank each channel's sequence label physically lands in. Only
        # the first channel is guaranteed to start in `start_bank`; once
        # earlier channels fill a bank, a later channel's label spills into
        # the next one. audio_init/load_song_streams_indexed must seed each
        # channel's stream_bank from this instead of assuming a fixed value
        # (#328/EXP-13).
        channel_start_banks = {}

        for channel in self.SEQUENCE_CHANNELS:
            channel_start_banks[channel] = current_bank
            lines.append(f'{label_prefix}{channel}_sequence:')
            events = channel_events[channel]
            if not events:
                lines.append('    .byte $FF')
                lines.append('')
                bytes_in_current_bank += 1
                continue
                
            current_inst = -1
            
            for event in events:
                # Pre-calculate bytes needed for this event
                event_bytes = 0
                note = event['note']
                dur = event['dur']

                if note > 0:
                    inst_id = event['inst_id']
                    if inst_id != current_inst:
                        event_bytes += 2
                
                if dur > 0:
                    rem_dur = dur
                    while rem_dur > 0:
                        write_dur = min(rem_dur, 32)
                        event_bytes += 2
                        rem_dur -= write_dur
                
                # Check if we need to switch banks
                if bytes_in_current_bank + event_bytes + 4 > BANK_SIZE_LIMIT:
                    next_bank = current_bank + 1
                    if next_bank > MAX_SEQUENCE_BANK:
                        raise ValueError(
                            f"Sequence bytecode exceeds the MMC3 "
                            f"{MAX_SEQUENCE_BANK + 1}-bank budget "
                            f"(~{(MAX_SEQUENCE_BANK + 1) * 8} KB): channel '{channel}' "
                            f"needs bank {next_bank}, but the linker config defines only "
                            f"BANK_00..BANK_{MAX_SEQUENCE_BANK:02d}. Shorten the song or "
                            f"split it across songs."
                        )
                    jump_label = f'{label_prefix}{channel}_seq_bank_{next_bank:02d}'
                    lines.append(f'    .byte $FE, ${next_bank:02X}, <{jump_label}, >{jump_label} ; CMD_BANK_JUMP')

                    current_bank = next_bank
                    bytes_in_current_bank = 0
                    lines.append('')
                    lines.append(f'.segment "BANK_{current_bank:02d}"')
                    lines.append(f'{jump_label}:')

                # Emit bytes and update size counter
                if note > 0:
                    inst_id = event['inst_id']
                    if inst_id != current_inst:
                        lines.append(f'    .byte $80, ${inst_id:02X} ; CMD_INSTRUMENT')
                        current_inst = inst_id
                        bytes_in_current_bank += 2

                if dur > 0:
                    rem_dur = dur
                    while rem_dur > 0:
                        write_dur = min(rem_dur, 32)
                        lines.append(f'    .byte ${(write_dur - 1) + 0x60:02X}, ${note:02X} ; Length {write_dur}, Note {note}')
                        rem_dur -= write_dur
                        bytes_in_current_bank += 2

            lines.append('    .byte $FF')
            lines.append('')
            bytes_in_current_bank += 1

        notes_clamped = {'high': notes_clamped_high, 'low': notes_clamped_low}
        # Multi-song callers always start the next song in a fresh bank
        # rather than continuing to pack into whatever's left of this one --
        # see the docstring above for why sharing a bank across calls isn't
        # safe with this function's per-call byte accounting.
        return lines, current_bank + 1, channel_start_banks, notes_clamped

    def _emit_bytecode_preamble(self, lines):
        """Shared header block for both bytecode exporters
        (export_tables_with_patterns and export_song_bank_bytecode,
        #466/TD-31): the `.importzp`, DPCM segment banner, and CODE_8000
        segment banner are byte-identical between a single-song and a
        jukebox build -- extracted so a future change to this preamble
        (e.g. a new `.importzp` symbol) can't apply to one path and silently
        skew the other."""
        lines.append('.importzp ptr1, temp1, temp2, frame_counter')
        lines.append('')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('; DPCM Sample Bank (Mapped to $C000)')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('.segment "DPCM"')
        lines.append('.align 64')
        # Deliberately left empty (#137/TD-08). DPCM sample data and lookup
        # tables are packed and appended to this music.asm by DpcmPacker
        # (dpcm_sampler/dpcm_packer.py) into the swappable DPCM_NN bank
        # segments -- not this fixed "DPCM" segment (mapped to the $C000/R6
        # window's default bank, `optional = yes` in the mapper's linker
        # config, mappers/mmc3.py) -- so there is nothing to .incbin here.
        lines.append('')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('; Macro & Sequence Data (Mapped to fixed $8000 bank)')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('.segment "CODE_8000"')
        lines.append('')

    def export_tables_with_patterns(self, frames, patterns, references, output_path, standalone=True,
                                     mapper=None, visualizer=False):
        """Export NES audio assembly from per-frame channel data.

        All emitted bytes derive from ``frames``. ``patterns`` is used only as a
        boolean switch: when empty, export the direct frame tables; when non-empty,
        emit the MMC3 macro-bytecode serializer (whose compression comes from
        macro/instrument de-duplication, not from the pattern detector). The
        ``references`` argument is **not consumed** — the detector's pattern
        references are analysis/metrics only and have no effect on output bytes
        (#4). It is retained for call-site compatibility.

        ``visualizer`` (--visualizer) only matters on the direct-export branch
        below -- it's passed through to ``export_direct_frames`` so its
        per-channel procs snapshot volume into ``channel_vis_vol``. The
        macro-bytecode branch needs no exporter change: nes/audio_engine.asm
        (included by NESProjectBuilder, gated on its own ``VISUALIZER_BUILD``
        symbol) does the equivalent snapshot itself.
        """
        if not patterns:
            return self.export_direct_frames(frames, output_path, standalone, mapper, visualizer)

        print("🔧 CA65 Exporter: MMC3 Macro Bytecode mode")

        lines = []
        lines.append('; CA65 Assembly Export (MMC3 Macro Bytecode)')
        lines.append('')
        self._emit_bytecode_preamble(lines)
        # The DPCM lookup tables (dpcm_bank_table/pitch/addr/len) are owned by the
        # DPCM packer when real samples exist, and stubbed by the project builder
        # otherwise. Defining them here too would be a duplicate-symbol error once
        # the packer appends the real tables to music.asm.

        # Export symbols needed by the audio engine
        lines.append('.export pulse1_sequence, pulse2_sequence, triangle_sequence, noise_sequence, dpcm_sequence')
        lines.append('.export ntsc_period_low, ntsc_period_high')
        lines.append('.export triangle_period_low, triangle_period_high')
        lines.append('.export instrument_table')
        lines.append('.export channel_start_banks')
        lines.append('')

        self._emit_period_tables(lines)

        body_lines, next_bank, channel_start_banks, notes_clamped = self._build_song_bytecode(
            frames, label_prefix='', start_bank=0)
        lines.extend(body_lines)
        # Exposed so a caller packing DPCM samples afterward (main.py's
        # pack_dpcm_into_asm) can start DPCM_NN numbering at the first bank
        # this song's own BANK_NN sequence bytecode didn't use, instead of
        # both independently starting at bank 0 and colliding in the same
        # physical PRG_BANK_00 region (#522/DPCM-2026-08-23-1).
        self.next_bank = next_bank

        # Per-channel starting-bank table (#328/EXP-13). Emitted into the fixed
        # CODE_8000 bank (always mapped) so audio_init can read it via absolute
        # addressing at startup, exactly like instrument_table / the period
        # tables above. Order matches the engine's channel indices 0..4.
        lines.append('.segment "CODE_8000"')
        bank_bytes = ', '.join(
            f'${channel_start_banks[ch]:02X}' for ch in self.SEQUENCE_CHANNELS)
        lines.append('channel_start_banks:')
        lines.append(f'    .byte {bank_bytes} ; pulse1, pulse2, triangle, noise, dpcm')
        lines.append('')

        if not standalone:
            lines.extend([
                '',
                '; Project builder compatible functions',
                '.export init_music, update_music',
                '.import audio_init, audio_update',
                '',
                '.segment "CODE"',
                'init_music:',
                '    jmp audio_init',
                '',
                'update_music:',
                '    jmp audio_update',
                ''
            ])

        # Atomic write (#385/SAFE-2026-07-19-3) -- see export_direct_frames above.
        atomic_write_text(output_path, '\n'.join(lines))

        # Expose the clamp tally for callers/tests; report it so an out-of-range
        # song does not get silently re-pitched (#298/EXP-10).
        self.notes_clamped = notes_clamped
        total_clamped = notes_clamped['high'] + notes_clamped['low']
        if total_clamped:
            print(
                f"⚠ {total_clamped} note(s) clamped to the NES tone range (24-95): "
                f"{notes_clamped['high']} above B6, {notes_clamped['low']} below C1. "
                "Pitch may differ from the MIDI file."
            )

        print(f"✅ Macro Bytecode export complete: {output_path}")
        return output_path

    def export_song_bank_bytecode(self, songs, output_path, song_count=None):
        """Export a multi-song 'jukebox' ROM's music.asm (#30/F-13).

        `songs` is an ordered iterable of mappings with a `'frames'` key (one
        entry per song, in playback order -- callers should already have
        sorted by the song bank's `metadata['order']`). Each song's frames
        are serialized exactly like a single-song bytecode export (see
        `_build_song_bytecode`), but with its symbols prefixed `song{i}_`
        and its sequence bytecode continuing the shared MMC3 60-bank pool
        from a fresh bank after the previous song's tail. Distinct songs
        keep separate instrument/macro tables (no cross-song dedup) but
        share one copy of the pulse/triangle period tables (they're pure
        hardware constants, identical for every song).

        `songs` is consumed lazily, one song at a time -- a caller building N
        songs from source MIDI can pass a generator so only one song's frames
        dict is resident in memory at a time instead of collecting a full
        list upfront (#505/PERF-B-02; also resolves #506/PERF-B-04 for free,
        since `_build_song_bytecode`'s own bank-budget `ValueError` below now
        fires as soon as the offending song is built, not after every song in
        the bank has already been parsed). `song_count` must be passed
        explicitly when `songs` has no `len()` (a generator); for a
        `list`/`tuple` it's inferred automatically, matching the previous
        signature.

        A `song_table` (three parallel byte arrays -- low/high address byte
        and bank, indexed `song_index*5 + channel`) plus a `song_count` byte
        replace the single-song `channel_start_banks` table, giving the
        jukebox-only engine routines in nes/audio_engine.asm (gated behind
        `.ifdef JUKEBOX_BUILD`) a way to look up any song's channel entry
        points at runtime. `init_music` jumps to `audio_init_song` instead
        of `audio_init` (single-song builds are unaffected -- they never
        call this method).
        """
        if song_count is None:
            song_count = len(songs)
        if song_count == 0:
            raise ValueError("export_song_bank_bytecode requires at least one song")

        # song_table (below) is indexed song_index*5 + channel by the
        # jukebox engine's 8-bit accumulator/Y-register math
        # (load_song_streams_indexed in nes/audio_engine.asm) -- the
        # highest valid index is 255, so the highest valid song_index is
        # (255 - 4) // 5 = 50, i.e. at most 51 songs. Past that the index
        # (or the current_song*5 multiply itself) wraps in 8 bits and every
        # gate downstream (bank pool, CC65, ROM validation) still passes,
        # so songs at index >= 51 would silently play the wrong streams on
        # the wrong channels with no build-time signal (#426). Checked
        # against the declared `song_count` before `songs` is ever iterated,
        # so an oversized bank fails before a single song is parsed/built.
        max_songs = (255 - (len(self.SEQUENCE_CHANNELS) - 1)) // len(self.SEQUENCE_CHANNELS) + 1
        if song_count > max_songs:
            raise ValueError(
                f"export_song_bank_bytecode: {song_count} songs exceeds the "
                f"jukebox engine's {max_songs}-song limit (song_table index "
                f"song_index*{len(self.SEQUENCE_CHANNELS)}+channel must stay "
                f"<= 255 for the engine's 8-bit indexing). Split this bank "
                f"into multiple ROMs."
            )

        print(f"🔧 CA65 Exporter: MMC3 Macro Bytecode mode ({song_count}-song jukebox build)")

        lines = []
        lines.append('; CA65 Assembly Export (MMC3 Macro Bytecode -- multi-song jukebox build)')
        lines.append('')
        self._emit_bytecode_preamble(lines)

        song_labels = [f'song{i}_' for i in range(song_count)]
        for prefix in song_labels:
            lines.append(
                f'.export {prefix}pulse1_sequence, {prefix}pulse2_sequence, '
                f'{prefix}triangle_sequence, {prefix}noise_sequence, {prefix}dpcm_sequence'
            )
            lines.append(f'.export {prefix}instrument_table')
        lines.append('.export ntsc_period_low, ntsc_period_high')
        lines.append('.export triangle_period_low, triangle_period_high')
        lines.append('.export song_table_ptr_lo, song_table_ptr_hi, song_table_bank, song_count')
        lines.append('.export song_instrument_ptr_lo, song_instrument_ptr_hi')
        lines.append('')

        self._emit_period_tables(lines)

        all_notes_clamped = {'high': 0, 'low': 0}
        next_bank = 0
        song_channel_labels = []  # per song: {channel: (label, bank)}

        # `songs` is consumed one item at a time (it may be a generator) --
        # `song` is rebound each iteration, so the previous iteration's
        # frames dict has no remaining reference once this loop moves on and
        # is freed by CPython's refcounting rather than surviving until the
        # whole bank is built (#505/PERF-B-02).
        #
        # Iterated manually via `iter(songs)` rather than `zip(song_labels,
        # songs)` (#512/EXP-2026-08-23-5): `zip` silently stops at the
        # shorter of the two, which caught `songs` yielding FEWER items than
        # `song_count` declares (the mismatch check below) but not MORE --
        # a `songs` iterable with leftover items past `song_count` would
        # have zip'd cleanly and silently dropped them. Pulling one extra
        # item after the loop (further below) surfaces that case too.
        songs_iter = iter(songs)
        songs_consumed = 0
        for prefix in song_labels:
            try:
                song = next(songs_iter)
            except StopIteration:
                break
            frames = song['frames']
            # Every other hard invariant this method enforces (instrument
            # count, DPCM note range, bank budget, song_count) raises from
            # inside the exporter itself; DPCM-channel presence used to be
            # the one exception -- enforced only by main.py's
            # `_song_has_dpcm_events`, so a caller that skipped `main.py`
            # entirely (a library consumer, a future CLI path) could feed a
            # DPCM-bearing song straight through. No `DpcmPacker` ever runs
            # for a jukebox build, so the emitted `song{i}_dpcm_sequence`'s
            # trigger bytes would index the project builder's 1-byte stub
            # `dpcm_*_table`s past their end, feeding garbage bank/addr/len
            # into a live DMC DMA trigger (#509/EXP-2026-08-23-2).
            if song_has_dpcm_events(frames):
                raise ValueError(
                    f"export_song_bank_bytecode: song index {songs_consumed} "
                    f"('{prefix.rstrip('_')}') contains DPCM drum samples -- "
                    f"multi-song jukebox builds don't support DPCM yet (see "
                    f"docs/ROADMAP.md). Remove drums or build this song "
                    f"individually with the normal pipeline."
                )
            try:
                body_lines, next_bank, channel_start_banks, notes_clamped = self._build_song_bytecode(
                    frames, label_prefix=prefix, start_bank=next_bank)
            except ValueError as e:
                # Re-raise with the song identified (#511/EXP-2026-08-23-4):
                # _build_song_bytecode's own errors (bank-budget overflow,
                # DPCM note range) name the channel/bank but not which song
                # in a multi-song bank tipped it over, forcing the caller to
                # bisect the bank to find it.
                raise ValueError(
                    f"export_song_bank_bytecode: song index {songs_consumed} "
                    f"('{prefix.rstrip('_')}'): {e}"
                ) from e
            lines.extend(body_lines)
            all_notes_clamped['high'] += notes_clamped['high']
            all_notes_clamped['low'] += notes_clamped['low']
            song_channel_labels.append({
                ch: (f'{prefix}{ch}_sequence', channel_start_banks[ch])
                for ch in self.SEQUENCE_CHANNELS
            })
            songs_consumed += 1

        # If a lazy `songs` iterable yields fewer items than the `song_count`
        # it was declared with, every table built above (song_labels length,
        # the .export lines) would already assume the declared count. Fail
        # loudly instead of emitting a `song_table` shorter than `song_count`
        # claims, which the engine would read past the end of.
        if songs_consumed != song_count:
            raise ValueError(
                f"export_song_bank_bytecode: declared song_count={song_count} but "
                f"`songs` yielded only {songs_consumed} song(s)."
            )

        # The reverse mismatch (#512/EXP-2026-08-23-5): `songs` yielding MORE
        # than `song_count` declares. The loop above only ever pulls exactly
        # `song_count` items (one per `song_labels` entry), so a leftover
        # item here means the caller under-declared `song_count` -- the
        # extra song(s) would otherwise vanish from the ROM with no signal.
        _NO_MORE_SONGS = object()
        if next(songs_iter, _NO_MORE_SONGS) is not _NO_MORE_SONGS:
            raise ValueError(
                f"export_song_bank_bytecode: declared song_count={song_count} but "
                f"`songs` has at least one more song beyond that."
            )

        # song_table: 3 parallel arrays (addr-lo/addr-hi/bank), indexed
        # song_index*5 + channel, channel order = SEQUENCE_CHANNELS. Emitted
        # into CODE_8000 (fixed, always-mapped) like channel_start_banks was
        # for a single song, so load_song_streams_indexed can read any
        # song's entry via absolute,Y addressing without a bank swap.
        lines.append('.segment "CODE_8000"')
        lo_bytes, hi_bytes, bank_bytes = [], [], []
        for entry in song_channel_labels:
            for ch in self.SEQUENCE_CHANNELS:
                label, bank = entry[ch]
                lo_bytes.append(f'<{label}')
                hi_bytes.append(f'>{label}')
                bank_bytes.append(f'${bank:02X}')
        lines.append('song_table_ptr_lo:')
        lines.append('    .byte ' + ', '.join(lo_bytes))
        lines.append('song_table_ptr_hi:')
        lines.append('    .byte ' + ', '.join(hi_bytes))
        lines.append('song_table_bank:')
        lines.append('    .byte ' + ', '.join(bank_bytes))
        lines.append('song_count:')
        lines.append(f'    .byte ${song_count:02X}')
        lines.append('')

        # song_instrument_ptr: one entry per song (not per channel) --
        # EVAL_MACRO (nes/audio_engine.asm) indirects through this via
        # instrument_table_ptr since there's no single fixed `instrument_table`
        # label when each song has its own.
        lines.append('song_instrument_ptr_lo:')
        lines.append('    .byte ' + ', '.join(f'<{prefix}instrument_table' for prefix in song_labels))
        lines.append('song_instrument_ptr_hi:')
        lines.append('    .byte ' + ', '.join(f'>{prefix}instrument_table' for prefix in song_labels))
        lines.append('')

        lines.extend([
            '',
            '; Project builder compatible functions',
            '.export init_music, update_music',
            '.import audio_init_song, audio_update',
            '',
            '.segment "CODE"',
            'init_music:',
            '    jmp audio_init_song',
            '',
            'update_music:',
            '    jmp audio_update',
            ''
        ])

        # Atomic write (#385/SAFE-2026-07-19-3) -- see export_direct_frames above.
        atomic_write_text(output_path, '\n'.join(lines))

        self.notes_clamped = all_notes_clamped
        total_clamped = all_notes_clamped['high'] + all_notes_clamped['low']
        if total_clamped:
            print(
                f"⚠ {total_clamped} note(s) clamped to the NES tone range (24-95) across "
                f"{song_count} song(s): {all_notes_clamped['high']} above B6, "
                f"{all_notes_clamped['low']} below C1. Pitch may differ from the MIDI file(s)."
            )

        print(f"✅ Macro Bytecode jukebox export complete: {output_path} "
              f"({song_count} songs, {next_bank} bank(s) used)")
        return output_path
