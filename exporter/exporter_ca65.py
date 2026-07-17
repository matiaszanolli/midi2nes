from exporter.base_exporter import BaseExporter
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

# Pitch timer values come from the single authoritative NES_NOTE_TABLE in
# nes/pitch_table.py (fCPU/16 formula). The exporter must NOT keep its own
# divergent table: the bytecode pitch offset is `frame_pitch - base_timer`, and
# the frame pitch is produced from NES_NOTE_TABLE too, so any scale mismatch
# corrupts the played note (#16).


class CA65Exporter(BaseExporter):
    def __init__(self):
        super().__init__()
        
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

    def export_direct_frames(self, frames, output_path, standalone=True, mapper=None):
        """Export frames data directly using efficient lookup tables.

        ``mapper`` selects the iNES header emitted for a standalone ROM; it
        defaults to the pipeline default (MMC3) so the header matches the
        project's linker config instead of hardcoding MMC1 (#36).
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

        # Create sparse frame lookup tables for each channel
        # Format: For each active frame, store (note, control_byte, timer_lo, timer_hi)
        for channel_name in ['pulse1', 'pulse2', 'triangle']:
            if channel_name not in all_channels:
                continue

            channel_data = all_channels[channel_name]
            _ensure_segment(f'{channel_name}_note')
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
                    # Triangle: bit 7 = control flag, bits 6-0 = linear counter
                    # Use volume (if available) to set linear counter
                    volume = frame_data.get('volume', 0)
                    # FIXED: If volume is 0, control must be 0 (silent), not 0x80!
                    if volume == 0:
                        control = 0x00
                    else:
                        control = 0x80 | (volume * 7)  # Control flag + linear counter
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
            _ensure_segment(f'{channel_name}_note')
            lines.append(f'{channel_name}_note:')
            for i in range(0, len(note_table), 16):
                chunk = note_table[i:i+16]
                lines.append(f'    .byte {", ".join(chunk)}')

            _ensure_segment(f'{channel_name}_control')
            lines.append(f'{channel_name}_control:')
            for i in range(0, len(control_table), 16):
                chunk = control_table[i:i+16]
                lines.append(f'    .byte {", ".join(chunk)}')

            _ensure_segment(f'{channel_name}_timer_lo')
            lines.append(f'{channel_name}_timer_lo:')
            for i in range(0, len(timer_lo_table), 16):
                chunk = timer_lo_table[i:i+16]
                lines.append(f'    .byte {", ".join(chunk)}')

            _ensure_segment(f'{channel_name}_timer_hi')
            lines.append(f'{channel_name}_timer_hi:')
            for i in range(0, len(timer_hi_table), 16):
                chunk = timer_hi_table[i:i+16]
                lines.append(f'    .byte {", ".join(chunk)}')
            lines.append('')

        def _emit_byte_table(label, values):
            _ensure_segment(label)
            lines.append(f'{label}:')
            for i in range(0, len(values), 16):
                lines.append(f'    .byte {", ".join(values[i:i+16])}')

        # Noise frame tables (#9). note = 4-bit period index (0 = rest/change
        # sentinel); ctrl = $400C byte ($30 | volume); reg = $400E byte
        # (mode bit 7 | period). Drum hits are sparse, so empty frames are rests.
        if has_noise:
            channel_data = all_channels['noise']
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
            _emit_byte_table('noise_note', n_note)
            _emit_byte_table('noise_ctrl', n_ctrl)
            _emit_byte_table('noise_reg', n_reg)
            lines.append('')

        # DPCM frame tables (#9). note = sample_id + 1 (0 = rest/change sentinel).
        # The trigger reuses the packer/engine sample tables (dpcm_*_table).
        if has_dpcm:
            channel_data = all_channels['dpcm']
            d_note = []
            for frame_num in range(max_frame + 1):
                fd = channel_data.get(frame_num, channel_data.get(str(frame_num)))
                if not fd or fd.get('volume', 0) == 0:
                    d_note.append('$00')
                    continue
                d_note.append(f'${fd.get("note", 0) & 0xFF:02X}')
            lines.append('; DPCM Frame Data Tables')
            _emit_byte_table('dpcm_note', d_note)
            lines.append('')

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
            '    ; Check for song end and loop',
            f'    lda frame_counter+1',
            f'    cmp #>{max_frame}',
            f'    bcc @no_loop',
            f'    bne @loop_song',
            f'    lda frame_counter',
            f'    cmp #<{max_frame}',
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
        lines.append('    ; Check if frame is within range')
        lines.append(f'    lda frame_counter+1')
        lines.append(f'    cmp #>{max_frame}')
        lines.append('    bcc @in_range')
        lines.append('    bne @done')
        lines.append(f'    lda frame_counter')
        lines.append(f'    cmp #<{max_frame}')
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

        # Add channel-specific playback subroutines
        if 'pulse1' in all_channels:
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
                '    sta last_pulse1_note   ; Different note - update tracker',
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
                '    rts',
                '    ',
                '@sustain:',
                '    ; Note is sustaining - do nothing to avoid phase reset',
                '    rts',
                '.endproc',
                ''
            ])

        if 'pulse2' in all_channels:
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
                '    sta last_pulse2_note',
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
                '    rts',
                '    ',
                '@sustain:',
                '    rts',
                '.endproc',
                ''
            ])

        if 'triangle' in all_channels:
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
                '    sta last_triangle_note',
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
                '    rts',
                '    ',
                '@sustain:',
                '    rts',
                '.endproc',
                ''
            ])

        if has_noise:
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
                '    rts',
                '.endproc',
                ''
            ])

        if has_dpcm:
            # Mirrors audio_engine.asm @write_dpcm: trigger a one-shot sample on
            # a new note (sample_id = note-1), reusing the packer sample tables.
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
                '    ; Check for song end and loop',
                f'    lda frame_counter+1',
                f'    cmp #>{max_frame}',
                f'    bcc @no_loop',
                f'    bne @loop_song',
                f'    lda frame_counter',
                f'    cmp #<{max_frame}',
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

        # Write assembly file
        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))

        # Calculate total data size (4 tables per channel: note, control, timer_lo, timer_hi)
        total_bytes = (max_frame + 1) * 4 * len(all_channels)
        print(f"✅ Table-based export complete: {output_path}")
        print(f"   Data size: {total_bytes:,} bytes ({total_bytes/1024:.1f} KB)")
        print(f"   Channels exported: {', '.join(all_channels.keys())}")

        return output_path

    @staticmethod
    def _register_instrument(inst, instruments, instrument_defs):
        """Look up or assign an instrument id, guarding the single-byte
        CMD_INSTRUMENT operand (#80/EXP-04): with more than 256 unique
        (vol, arp, pitch, duty) macro combinations, `${inst_id:02X}` would
        widen past two hex digits, which ca65 rejects (or the engine's
        single-byte fetch would misread). Raises rather than emitting a
        corrupt operand, matching the sequence-bank-overflow guard below.
        """
        if inst not in instruments:
            new_id = len(instrument_defs)
            if new_id > 0xFF:
                raise ValueError(
                    "Too many unique instruments (>256 distinct volume/arp/"
                    "pitch/duty combinations) -- inst_id would exceed a "
                    "single byte. Reduce timbre variety or split the song."
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

    def export_tables_with_patterns(self, frames, patterns, references, output_path, standalone=True, mapper=None):
        """Export NES audio assembly from per-frame channel data.

        All emitted bytes derive from ``frames``. ``patterns`` is used only as a
        boolean switch: when empty, export the direct frame tables; when non-empty,
        emit the MMC3 macro-bytecode serializer (whose compression comes from
        macro/instrument de-duplication, not from the pattern detector). The
        ``references`` argument is **not consumed** — the detector's pattern
        references are analysis/metrics only and have no effect on output bytes
        (#4). It is retained for call-site compatibility.
        """
        if not patterns:
            return self.export_direct_frames(frames, output_path, standalone, mapper)

        print("🔧 CA65 Exporter: MMC3 Macro Bytecode mode")
        
        lines = []
        lines.append('; CA65 Assembly Export (MMC3 Macro Bytecode)')
        lines.append('')
        lines.append('.importzp ptr1, temp1, temp2, frame_counter')
        lines.append('')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('; DPCM Sample Bank (Mapped to $C000)')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('.segment "DPCM"')
        lines.append('.align 64')
        lines.append('; TODO: Insert actual .incbin statements for DPCM files here')
        lines.append('')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('; Macro & Sequence Data (Mapped to fixed $8000 bank)')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('.segment "CODE_8000"')
        lines.append('')
        # The DPCM lookup tables (dpcm_bank_table/pitch/addr/len) are owned by the
        # DPCM packer when real samples exist, and stubbed by the project builder
        # otherwise. Defining them here too would be a duplicate-symbol error once
        # the packer appends the real tables to music.asm.
        
        # Export symbols needed by the audio engine
        lines.append('.export pulse1_sequence, pulse2_sequence, triangle_sequence, noise_sequence, dpcm_sequence')
        lines.append('.export ntsc_period_low, ntsc_period_high')
        lines.append('.export triangle_period_low, triangle_period_high')
        lines.append('.export instrument_table')
        lines.append('')

        # Write Pitch Lookup Tables. Generated from the single authoritative
        # per-channel tables so the runtime base period matches the base_timer
        # the pitch offset was computed against (#16) — keeping them as separate
        # hardcoded copies is exactly how they drifted an octave apart. The
        # triangle channel needs its own /32 table or it plays an octave low (#12).
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

        channel_events = {ch: [] for ch in ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']}

        # Count tone-channel notes re-pitched by the range clamp below so the
        # loss is reported instead of silently altering pitch (#298/EXP-10).
        notes_clamped_high = 0  # note > 95 (above B6)
        notes_clamped_low = 0   # 0 < note < 24 (below C1, tone channels)

        for channel in ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']:
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
                vol = frame_data.get('volume', 0) if frame_data else 0
                control = frame_data.get('control', 0x80) if frame_data else 0x80
                duty = (control >> 6) & 0x03

                if frame_data and vol == 0:
                    note = 0
                    
                # The DPCM channel's `note` is sample_id + 1, not a MIDI note, so
                # it is bounded only by the single-byte frame format (<= 255), not
                # the 0-95 tone-note range — clamping it to 95 collapsed high-id
                # drums to one wrong sample (#67). Tone channels keep the note
                # ceiling. Either way `note` stays a single byte so the `${note:02X}`
                # operand below can never widen past two hex digits.
                orig_note = note
                if channel == 'dpcm':
                    if note > 255:
                        note = 255
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

        lines.append('; The Instrument Macro Pointers')
        lines.append('instrument_table:')
        for inst in instrument_defs:
            v_id, a_id, p_id, d_id = inst
            lines.append(f'    .word macro_vol_{v_id}, macro_arp_{a_id}, macro_pitch_{p_id}, macro_duty_{d_id}')
        lines.append('')
        
        for name, defs in [('vol', vol_macro_defs), ('arp', arp_macro_defs), ('pitch', pitch_macro_defs), ('duty', duty_macro_defs)]:
            lines.append(f'; --- {name.capitalize()} Macros ---')
            for i, seq in enumerate(defs):
                lines.append(f'macro_{name}_{i}:')
                lines.append('    .byte ' + ', '.join(f'${val:02X}' for val in seq))
            lines.append('')
        
        # Bytecode generation for channels
        from mappers.mmc3 import MMC3Mapper
        # Highest swap-bank index the MMC3 linker config defines (BANK_00..N-1).
        # Rolling past it would emit a .segment ld65 has no MEMORY region for (#127).
        MAX_SEQUENCE_BANK = MMC3Mapper.SWAP_BANK_COUNT - 1
        current_bank = 0
        bytes_in_current_bank = 0
        BANK_SIZE_LIMIT = 8192 - 256  # 8KB minus a safety margin
        
        lines.append('; ---------------------------------------------------------------------------')
        lines.append('; Sequence Data (Dynamically Banked)')
        lines.append('; ---------------------------------------------------------------------------')
        lines.append(f'.segment "BANK_{current_bank:02d}"')
        lines.append('')

        for channel in ['pulse1', 'pulse2', 'triangle', 'noise', 'dpcm']:
            lines.append(f'{channel}_sequence:')
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
                    jump_label = f'{channel}_seq_bank_{next_bank:02d}'
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
            
        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))

        # Expose the clamp tally for callers/tests; report it so an out-of-range
        # song does not get silently re-pitched (#298/EXP-10).
        self.notes_clamped = {'high': notes_clamped_high, 'low': notes_clamped_low}
        total_clamped = notes_clamped_high + notes_clamped_low
        if total_clamped:
            print(
                f"⚠ {total_clamped} note(s) clamped to the NES tone range (24-95): "
                f"{notes_clamped_high} above B6, {notes_clamped_low} below C1. "
                "Pitch may differ from the MIDI file."
            )

        print(f"✅ Macro Bytecode export complete: {output_path}")
        return output_path
