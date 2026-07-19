from collections import defaultdict
from .pitch_table import PitchProcessor
from collections import defaultdict
from .envelope_processor import EnvelopeProcessor, velocity_to_volume


class NESEmulatorCore:
    def __init__(self):
        self.pitch_processor = PitchProcessor()
        self.envelope_processor = EnvelopeProcessor()

    def midi_to_nes_pitch(self, note, channel_type='pulse'):
        return self.pitch_processor.get_channel_pitch(note, channel_type)

    @staticmethod
    def _collapse_same_frame_events(events, channel_label):
        """Collapse note-ons that quantize to the same 60Hz frame on one channel.

        A NES channel is monophonic, so when several note-ons land on the same
        frame only one can sound. The frame-build loops key by frame, so the later
        write silently overwrote the earlier note and dropped it with no trace
        (#96). Keep the loudest note for each frame (ties keep the later event)
        and return ``(kept_events, dropped_count)`` so the caller can surface the
        loss. The arranger avoids this collapse entirely by allocating/arpeggiating
        polyphony across channels upstream.
        """
        note_ons = sorted(
            (e for e in events if e.get('velocity', e.get('volume', 0)) > 0),
            key=lambda e: e['frame'])
        kept = []
        dropped = 0
        for e in note_ons:
            vel = e.get('velocity', e.get('volume', 0))
            if kept and kept[-1]['frame'] == e['frame']:
                dropped += 1
                prev_vel = kept[-1].get('velocity', kept[-1].get('volume', 0))
                if vel >= prev_vel:
                    kept[-1] = e  # louder note wins; equal velocity keeps the later one (#344/TEMPO-15)
            else:
                kept.append(e)
        if dropped:
            print(f"Warning: {dropped} note(s) on {channel_label} dropped — "
                  f"multiple notes quantized to the same 60Hz frame "
                  f"(monophonic channel; use --arranger to arpeggiate polyphony).")
        return kept, dropped

    def compile_channel_to_frames(self, events, channel_type='pulse', default_duty=2, sustain_frames=4):
        """
        Extend note-on events to simulate duration across frames with envelope processing.
        """
        frames = defaultdict(dict)

        # Real note-off pairing (#160): a fixed sustain_frames used to be the
        # *only* source of duration, discarding whatever length the MIDI note
        # actually had. Search the original (unfiltered) events for each
        # note-on's matching note-off before they get collapsed away below.
        all_events_sorted = sorted(events, key=lambda e: e['frame'])

        # Collapse same-frame note-ons (mono channel) so a later note never
        # silently overwrites an earlier one for the shared frames (#96). After
        # this, every kept event has a unique frame, so the truncation guard
        # below (next_event['frame'] > start_frame) always fires correctly.
        events, _ = self._collapse_same_frame_events(events, channel_type)
        num_events = len(events)

        for i, event in enumerate(events):
            # Handle both 'velocity' and 'volume' fields for compatibility
            velocity = event.get('velocity', event.get('volume', 0))
            if velocity == 0:
                continue  # We simulate note-off via time

            start_frame = event['frame']
            note_pitch = event['note']

            # Use the matching note-off's frame as the real duration; fall
            # back to sustain_frames only when this note-on has none (same
            # fallback the arranger front-end uses for unpaired notes).
            end_frame = start_frame + sustain_frames
            for other in all_events_sorted:
                if other['frame'] <= start_frame:
                    continue
                other_velocity = other.get('velocity', other.get('volume', 0))
                if other_velocity == 0 and other.get('note') == note_pitch:
                    end_frame = other['frame']
                    break

            # Stop early if another note starts before this note's end
            for j in range(i + 1, num_events):
                next_event = events[j]
                next_velocity = next_event.get('velocity', next_event.get('volume', 0))
                if next_velocity > 0 and next_event['frame'] > start_frame:
                    end_frame = min(end_frame, next_event['frame'])
                    break

            # Use the pitch_processor instance instead of static function
            pitch = self.midi_to_nes_pitch(event['note'], channel_type)
            # envelope_type is currently always 'default' — no pipeline stage sets
            # it yet (the ADSR/effects engine is inert scaffolding, #166). Kept so
            # a future GM-based producer can drive real envelopes without re-plumbing.
            envelope_type = event.get('envelope_type', 'default')

            for f in range(start_frame, end_frame):
                frame_offset = f - start_frame
                if channel_type.startswith('pulse'):
                    control_byte = self.envelope_processor.get_envelope_control_byte(
                        envelope_type, frame_offset, end_frame - start_frame, default_duty, None, velocity
                    )
                    frames[f] = {
                        "pitch": pitch,
                        "control": control_byte,
                        "note": event['note'],
                        "volume": velocity_to_volume(velocity)
                    }
                else:
                    # Apply power curve for volume fidelity on all non-pulse channels too
                    frames[f] = {
                        "pitch": pitch,
                        "volume": velocity_to_volume(velocity),
                        "note": event['note']
                    }

        return dict(sorted(frames.items()))

    def process_all_tracks(self, nes_tracks):
        processed = {}
        
        for channel_name, events in nes_tracks.items():
            if channel_name in ['pulse1', 'pulse2', 'triangle']:
                duty = 2 if 'pulse' in channel_name else None
                processed[channel_name] = self.compile_channel_to_frames(
                    events, 
                    channel_type=channel_name, 
                    default_duty=duty
                )
            elif channel_name == 'noise':
                # Noise frames must carry the data the exporters turn into APU
                # writes (#9): `note` = 4-bit period index ($400E low nibble),
                # mode bit folded into `control` bit 6 (the engine reads it as
                # the duty/mode bit), and a scaled `volume`. Both playback paths
                # force constant-volume + halt ($30) on $400C, so there is no
                # hardware envelope or length-counter decay to rely on (#162/
                # NH-19) -- emit a short software volume ramp across several
                # frames instead. The macro/frame-table serializers already
                # read `volume` per frame, so a per-hit ramp here becomes a
                # real vol_seq/frame-table decay for free downstream.
                noise_frames = {}
                # Same monophonic same-frame collapse as the tonal channels (#96):
                # keep one hit per frame and count the drops instead of letting the
                # last write silently win.
                events, _ = self._collapse_same_frame_events(events, 'noise')
                sorted_events = sorted(events, key=lambda ev: ev['frame'])
                NOISE_DECAY_FRAMES = 6  # ~100ms decay simulating a drum strike
                for i, e in enumerate(sorted_events):
                    velocity = e.get('velocity', e.get('volume', 0))
                    if velocity <= 0:
                        continue
                    # Period index 0 is the bytecode rest sentinel, so floor an
                    # active hit at 1 (loses only the very highest noise pitch).
                    period = max(1, self.midi_to_nes_pitch(e['note'], 'noise'))
                    mode = e.get('noise_mode', 0) & 1
                    peak_volume = velocity_to_volume(velocity)

                    start_frame = e['frame']
                    end_frame = start_frame + NOISE_DECAY_FRAMES
                    # A re-trigger cuts the previous strike's decay short
                    # rather than blending into it.
                    if i + 1 < len(sorted_events):
                        next_frame = sorted_events[i + 1]['frame']
                        if next_frame > start_frame:
                            end_frame = min(end_frame, next_frame)

                    span = end_frame - start_frame
                    for offset in range(span):
                        decayed_volume = max(1, round(peak_volume * (span - offset) / span))
                        noise_frames[start_frame + offset] = {
                            "note": period,
                            "control": mode << 6,
                            "volume": decayed_volume,
                        }
                processed[channel_name] = noise_frames
            elif channel_name == 'dpcm':
                # DPCM frames carry `note` = dense_id + 1 (the engine recovers
                # dense_id as note-1 and uses it to index the sample tables);
                # note 0 stays the rest sentinel (#9). A single-frame trigger
                # starts the sample, which then plays to completion via DMA.
                #
                # `sample_id` here is the raw dpcm_index.json catalog id
                # (0-1922 in the shipped index), but the frame `note` is a
                # single byte -- min(255, sample_id + 1) used to collapse
                # every catalog id >= 255 onto note 255, so any two of the
                # shipped catalog's real drums (e.g. kick=1318, snare=1620)
                # silently aliased onto the same wrong sample (#200/D-14).
                # Remap the catalog ids this SONG actually references to a
                # dense, song-local 0..N-1 range (ascending catalog-id order,
                # matching the packer's own ordering convention) before
                # encoding: a real song rarely references anywhere near 255
                # distinct drums, so this survives the byte ceiling correctly
                # instead of just detecting the collision after the fact.
                # `dpcm_sample_map` (dense_id -> catalog_id) is emitted
                # alongside so the export/pack stage can resolve the actual
                # sample files a JSON stage boundary later.
                dpcm_frames = {}
                # Same monophonic same-frame collapse (#96): two drum hits on one
                # frame can't both trigger, so keep the loudest and count the drop.
                events, _ = self._collapse_same_frame_events(events, 'dpcm')

                referenced_ids = sorted({
                    e.get('sample_id', 0) for e in events
                    if e.get('velocity', e.get('volume', 0)) > 0
                })
                dense_id_of = {raw_id: i for i, raw_id in enumerate(referenced_ids)}

                # The dense remap above only survives the note=min(255, dense_id+1)
                # byte ceiling up to 255 distinct samples: dense_id 255 also
                # encodes to note 255, colliding with dense_id 254, so every
                # dense_id >= 255 becomes unreachable and silently plays the
                # dense_id=254 sample instead (#343/DP-DPCM-04). Warn the same
                # way the same-frame collapse above does, rather than aliasing
                # silently.
                if len(referenced_ids) > 255:
                    print(f"Warning: {len(referenced_ids)} distinct DPCM samples "
                          f"referenced on {channel_name}, exceeding the 255-sample "
                          f"dense-id ceiling — samples beyond the 255th will silently "
                          f"alias onto the 255th sample.")

                for e in events:
                    velocity = e.get('velocity', e.get('volume', 0))
                    if velocity <= 0:
                        continue
                    sample_id = e.get('sample_id', 0)
                    dense_id = dense_id_of[sample_id]
                    frame = {
                        "note": min(255, dense_id + 1),
                        "volume": 15,
                    }
                    dpcm_frames[e['frame']] = frame
                processed[channel_name] = dpcm_frames
                if referenced_ids:
                    processed['dpcm_sample_map'] = {
                        str(dense_id): raw_id for raw_id, dense_id in dense_id_of.items()
                    }

        return processed


# The non-channel key process_all_tracks injects alongside the real channels
# (see above): a dense_id -> catalog_id side table, not a per-frame channel.
DPCM_SAMPLE_MAP_KEY = 'dpcm_sample_map'


def frames_to_events(frames):
    """Flatten a ``process_all_tracks`` frames dict into a frame-sorted event
    list for pattern detection.

    Skips the ``dpcm_sample_map`` side table (#200/D-14) — it is a
    ``{str(dense_id): catalog_id}`` map, not a ``{frame_num: {...}}`` channel,
    so iterating it as one would call ``int.get('note')`` and raise. This is the
    single shared extractor for every ``frames``->events call site (the two
    ``main.py`` pattern-detection paths and the benchmark harness) so the guard
    cannot drift out of one of them again (#261).
    """
    events = []
    for channel_name, channel_frames in frames.items():
        if channel_name == DPCM_SAMPLE_MAP_KEY:
            continue
        for frame_num, frame_data in channel_frames.items():
            events.append({
                'frame': int(frame_num),
                'note': frame_data.get('note', 0),
                'volume': frame_data.get('volume', 0),
            })
    events.sort(key=lambda e: e['frame'])
    return events
