"""NES On-Screen Volume-Bar Visualizer

Generates CA65 assembly for a minimal PPU rendering pipeline that draws four
background-tile volume bars (Pulse1, Pulse2, Triangle, Noise) driven purely
by data the audio engine already computes each frame.

The NES APU registers are write-only -- there is no way to read "current
channel volume" back from hardware. Instead, the runtime engine
(nes/audio_engine.asm, and exporter/exporter_ca65.py's direct-export procs)
snapshots the 0-15 volume value it is about to write to each channel into a
small RAM array, `channel_vis_vol` (declared/exported by
NESProjectBuilder._generate_main_asm). This module only has to read that
array and draw bars -- see docs on `channel_vis_vol` in project_builder.py
and audio_engine.asm for where it's populated.

This is also the first real PPU rendering in the repo: unlike
nes/debug_overlay.py (which writes ASCII bytes into the nametable as tile
indices but never loads a font into CHR-RAM and never enables PPUMASK, so it
has likely never actually been visible), this module owns the full
init sequence -- vblank wait, nametable clear, CHR-RAM tile upload, palette
init, and enabling background rendering via PPUMASK ($2001, the first write
of that register anywhere in this codebase).
"""

# NES color palette bytes, matching NESDebugOverlay.COLORS' convention.
BACKDROP_COLOR = 0x0F   # black
BAR_COLOR = 0x2A         # green

# Bar geometry: 4 channels, each a 2-tile-tall (16px) bar built from a 9-tile
# fill set (tile N = bottom N of 8 rows filled, N = 0..8). Placed near the
# bottom of the screen, spaced out across the nametable's 32 columns.
NUM_CHANNELS = 4
CHANNEL_LABELS = ("Pulse1", "Pulse2", "Triangle", "Noise")
BAR_COLUMNS = (4, 10, 16, 22)
BAR_ROW_BOTTOM = 26
BAR_ROW_TOP = 25

# 9 CHR-RAM tiles (fill levels 0..8), 16 bytes each (8 bytes/bitplane x 2
# identical bitplanes -- a filled pixel reads color index 3, an empty pixel
# reads color index 0/transparent-to-backdrop; this pattern never produces
# index 1 or 2). Tile N fills the BOTTOM N of its 8 rows.
NUM_TILES = 9


def _tile_plane(fill_rows: int) -> bytes:
    """8 bytes for one bitplane of a fill-level tile: the bottom `fill_rows`
    of 8 rows are solid ($FF), the rest are empty ($00)."""
    empty_rows = 8 - fill_rows
    return bytes([0x00] * empty_rows + [0xFF] * fill_rows)


def generate_chr_tiles() -> bytes:
    """Build the full 9-tile (144-byte) CHR-RAM upload payload."""
    data = bytearray()
    for fill_rows in range(NUM_TILES):
        plane = _tile_plane(fill_rows)
        data.extend(plane)  # bitplane 0
        data.extend(plane)  # bitplane 1 (identical -> 2-color tile)
    return bytes(data)


def _nametable_addr(row: int, col: int) -> int:
    return 0x2000 + row * 32 + col


class NESVisualizer:
    """Generates NES assembly code for the on-screen volume-bar UI."""

    def __init__(self, enable_visualizer: bool = True):
        self.enable_visualizer = enable_visualizer

    def _generate_chr_table_asm(self) -> str:
        tiles = generate_chr_tiles()
        byte_lines = []
        for i in range(0, len(tiles), 16):
            chunk = tiles[i:i + 16]
            byte_lines.append("    .byte " + ", ".join(f"${b:02X}" for b in chunk))
        return "visualizer_chr_tiles:\n" + "\n".join(byte_lines) + "\n"

    def _generate_palette_table_asm(self) -> str:
        # 4 background palette groups, only group 0 is actually referenced by
        # the bar tiles (attribute table is left zeroed by the nametable
        # clear), but all 4 are initialized to avoid PPU power-on garbage.
        group = [BACKDROP_COLOR, BACKDROP_COLOR, BACKDROP_COLOR, BAR_COLOR]
        row = group * 4
        return ("visualizer_palette:\n    .byte "
                + ", ".join(f"${b:02X}" for b in row) + "\n")

    def generate_visualizer_data(self) -> str:
        """CHR tile data + palette table (RODATA)."""
        if not self.enable_visualizer:
            return "; Visualizer data disabled\n"

        return f"""; ============================================
; Visualizer CHR Tile Data & Palette
; ============================================
.pushseg
.segment "RODATA"
{self._generate_chr_table_asm()}
{self._generate_palette_table_asm()}
.popseg

"""

    def generate_visualizer_init(self) -> str:
        """Reset-time PPU setup: vblank wait, nametable clear, CHR-RAM tile
        upload, palette init, enable background rendering."""
        if not self.enable_visualizer:
            return "; Visualizer init disabled\n"

        return """; ============================================
; Visualizer Initialization (called once from reset, before NMI is enabled)
; ============================================
visualizer_init:
    ; Wait for two VBlanks so the PPU is warmed up before we touch it.
@vis_vblankwait1:
    bit $2002
    bpl @vis_vblankwait1
@vis_vblankwait2:
    bit $2002
    bpl @vis_vblankwait2

    ; Clear the nametable + attribute table ($2000-$23FF, 1024 bytes) to
    ; tile 0 -- which is also our "bar empty" tile, so no separate blank
    ; background tile is needed.
    bit $2002
    lda #$20
    sta $2006
    lda #$00
    sta $2006
    ldx #$04        ; 4 pages of 256 bytes = 1024 bytes
    ldy #$00
    lda #$00
@vis_clear_nt_loop:
    sta $2007
    iny
    bne @vis_clear_nt_loop
    dex
    bne @vis_clear_nt_loop

    ; Upload the 9-tile (144-byte) bar fill set into CHR-RAM pattern table 0
    ; ($0000-$1FFF; PPUCTRL's background-pattern-table bit is left at 0, so
    ; background tiles read from $0000).
    bit $2002
    lda #$00
    sta $2006
    lda #$00
    sta $2006
    ldy #$00
@vis_chr_upload_loop:
    lda visualizer_chr_tiles, y
    sta $2007
    iny
    cpy #144
    bne @vis_chr_upload_loop

    ; Initialize background palette RAM.
    bit $2002
    lda #$3F
    sta $2006
    lda #$00
    sta $2006
    ldy #$00
@vis_palette_loop:
    lda visualizer_palette, y
    sta $2007
    iny
    cpy #16
    bne @vis_palette_loop

    ; Enable background rendering.
    lda #$08
    sta $2001

    rts

"""

    def generate_visualizer_update(self) -> str:
        """Per-NMI update: read channel_vis_vol[0..3] and redraw each bar's
        two tiles. channel_vis_vol is owned/exported by main.asm
        (NESProjectBuilder._generate_main_asm) and populated every frame by
        nes/audio_engine.asm (bytecode builds) or exporter_ca65.py's
        direct-export per-channel procs -- never read back from the APU."""
        if not self.enable_visualizer:
            return "; Visualizer update disabled\n"

        macro_calls = []
        for i in range(NUM_CHANNELS):
            addr_bottom = _nametable_addr(BAR_ROW_BOTTOM, BAR_COLUMNS[i])
            addr_top = _nametable_addr(BAR_ROW_TOP, BAR_COLUMNS[i])
            macro_calls.append(
                f"    VIS_DRAW_BAR {i}, ${addr_bottom:04X}, ${addr_top:04X}  ; {CHANNEL_LABELS[i]}"
            )
        calls_asm = "\n".join(macro_calls)

        return f"""; ============================================
; Visualizer Update (called from NMI, after jsr update_music)
; ============================================

; VIS_DRAW_BAR chan_off, addr_bottom, addr_top
; Splits channel_vis_vol[chan_off] (0-15) into a bottom-tile fill level
; (0-8) and a top-tile fill level (0-7), then writes both tiles to the
; given nametable addresses.
.macro VIS_DRAW_BAR chan_off, addr_bottom, addr_top
    .local @no_overflow
    .local @write
    lda channel_vis_vol+chan_off
    cmp #9
    bcc @no_overflow
    sta visualizer_scratch_hi   ; hold raw vol
    lda #8
    sta visualizer_scratch_lo   ; bottom = 8 (full)
    lda visualizer_scratch_hi
    sec
    sbc #8
    sta visualizer_scratch_hi   ; top = vol - 8
    jmp @write
@no_overflow:
    sta visualizer_scratch_lo   ; bottom = vol
    lda #0
    sta visualizer_scratch_hi   ; top = 0
@write:
    lda #>(addr_bottom)
    sta $2006
    lda #<(addr_bottom)
    sta $2006
    lda visualizer_scratch_lo
    sta $2007

    lda #>(addr_top)
    sta $2006
    lda #<(addr_top)
    sta $2006
    lda visualizer_scratch_hi
    sta $2007
.endmacro

visualizer_update:
    bit $2002    ; reset the PPU address latch once; nothing else touches
                 ; $2006 during this NMI before we get here
{calls_asm}
    rts

.pushseg
.segment "BSS"
visualizer_scratch_lo: .res 1
visualizer_scratch_hi: .res 1
.popseg

"""

    def generate_full_visualizer_system(self) -> str:
        """Generate the complete visualizer CA65 source: init + update + data.

        Code (init/update) comes first, with the RODATA tile/palette tables
        appended last via their own `.pushseg`/`.popseg` block -- forward
        references to labels defined later in the same module are fine
        (ca65 is two-pass). This mirrors nes/debug_overlay.py's convention
        (code first, `.pushseg`-declared variables after) so that whatever
        segment the CALLER had active before calling this (main.asm/
        project_builder.py sets an explicit "CODE" segment first, matching
        the #388/MAP-2026-08-05-1 fix for the sibling --debug overlay)
        is still the active segment right up to `visualizer_init:` -- not
        just restored-by-`.popseg`, but never left in the first place.
        """
        parts = [
            "; ============================================",
            "; MIDI2NES Volume-Bar Visualizer",
            "; Generated automatically -- draws per-channel volume bars",
            "; on screen, driven by the audio engine's own frame data",
            "; (the APU is write-only and cannot be read back).",
            "; ============================================",
            "",
            self.generate_visualizer_init(),
            self.generate_visualizer_update(),
            self.generate_visualizer_data(),
        ]
        return "\n".join(parts)
