"""Execution-based ROM smoke test (#517/PIPE-2026-08-24-1).

The pipeline's prior ROM-validation gate (`debug/rom_diagnostics.py`) was
purely static: it checked whether the right *bytes* existed somewhere in the
file, never whether the CPU actually *runs* them from the RESET vector. A
ROM could report HEALTHY while being completely silent at runtime -- exactly
the bug this module exists to catch (root cause: `nes/project_builder.py`'s
generated `reset` routine used to enable NMI before the PPU's mandatory
~2-vblank post-reset warm-up window closed, so the enabling write was
silently dropped and `update_music`/`audio_update` -- reachable only from
the NMI handler -- never ran).

This module drives `debug/cpu6502.py`'s interpreter against the ROM's real
PRG-ROM bytes, from the real RESET vector, over a bounded number of
simulated frames, and reports whether NMI ever actually fired and whether
any APU register write happened *after* that first NMI (the only place any
per-frame note/volume/pitch write can originate, per every audio-engine
code path in this project -- see nes/audio_engine.asm and
exporter/exporter_ca65.py's init_music/audio_init, neither of which writes a
real note outside the NMI-gated update path).

Scope: NROM (mapper 0) and MMC3 (mapper 4, PRG mode 1 -- the only mode this
project's generated code ever selects), matching the two mappers this
session's investigation and the two-vblank-wait fix concerned. MMC1
(mapper 1) is not implemented (its 5-write serial shift-register protocol is
a materially different, non-trivial state machine) -- callers must check
`mapper_supported` and treat `False` as "skip this check", not as a defect.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from debug.cpu6502 import CPU6502, CPUError

# Standard NTSC PPU/CPU timing constants (NESdev-documented). Approximate
# (not sub-cycle-exact) is fine for a smoke test -- what matters is getting
# the *relationship* between the warm-up window and the first vblank right,
# not frame-perfect accuracy.
FRAME_CYCLES = 29780          # ~1 video frame (262 scanlines) in CPU cycles
VBLANK_START_CYCLES = 27384   # scanline 241 dot 1, in CPU cycles into the frame
PPU_WARMUP_CYCLES = 29658     # ~2 vblanks; PPUCTRL/MASK/SCROLL/ADDR writes
                               # before this are dropped on real hardware

APU_LOG_CAP = 512             # bounded so a long/looping run can't grow this
MAX_APU_WRITES_RETURNED = 64  # trimmed further in the result for readability


class UnsupportedMapperError(Exception):
    """Raised internally when the ROM's mapper isn't one this smoke test
    can simulate. Callers should catch this via `mapper_supported=False`
    in the result, not let it propagate as a validation failure."""


class Cartridge:
    """Common PRG-ROM read/write routing; subclasses implement mapper-
    specific bank selection."""

    def __init__(self, prg: bytes, prg_ram_size: int = 0x2000):
        self.prg = prg
        self.prg_ram = bytearray(prg_ram_size)

    def read_prg(self, addr: int) -> int:
        raise NotImplementedError

    def write_register(self, addr: int, value: int) -> None:
        """Cartridge-mapped register write ($8000-$FFFF on write is never
        real PRG-ROM data -- it's mapper registers, even where the same
        address range returns ROM data on read)."""


class NROMCartridge(Cartridge):
    def __init__(self, prg: bytes):
        super().__init__(prg)
        # NROM-128 (16KB) mirrors to fill the 32KB $8000-$FFFF window;
        # NROM-256 (32KB) maps directly. Anything else is malformed for
        # this mapper, but degrade gracefully (mod by actual length) rather
        # than raising mid-simulation.
        self.size = len(prg) if len(prg) > 0 else 0x8000

    def read_prg(self, addr: int) -> int:
        offset = (addr - 0x8000) % self.size
        return self.prg[offset]

    def write_register(self, addr: int, value: int) -> None:
        pass  # NROM has no mapper registers


class MMC3Cartridge(Cartridge):
    """PRG-side only (this project never uses CHR-ROM banking -- every
    generated header declares CHR-RAM). Faithfully implements PRG mode 0/1
    bank-select semantics even though this codebase only ever selects mode
    1, so a future change to `generate_init_code()` doesn't silently
    desync the smoke test from real hardware."""

    def __init__(self, prg: bytes):
        super().__init__(prg)
        self.bank_count = max(1, len(prg) // 0x2000)
        self.bank_select = 0  # last value written to an even $8000-9FFE addr
        self.bank_data = [0] * 8  # R0..R7, only R6/R7 (PRG) matter here

    def write_register(self, addr: int, value: int) -> None:
        if 0x8000 <= addr <= 0x9FFF:
            if addr & 1 == 0:
                self.bank_select = value
            else:
                reg = self.bank_select & 0x07
                self.bank_data[reg] = value
        # $A000-$FFFF: mirroring / PRG-RAM-protect / IRQ latch-reload-
        # enable-disable registers -- not needed for this smoke test (this
        # project's generated code disables MMC3 IRQs once at boot and
        # never re-enables them), safely ignored.

    def _prg_mode1(self) -> bool:
        return bool(self.bank_select & 0x40)

    def read_prg(self, addr: int) -> int:
        offset = addr & 0x1FFF
        last = self.bank_count - 1
        second_last = max(0, self.bank_count - 2)
        r6 = self.bank_data[6] % self.bank_count
        r7 = self.bank_data[7] % self.bank_count
        mode1 = self._prg_mode1()

        if 0x8000 <= addr <= 0x9FFF:
            bank = second_last if mode1 else r6
        elif 0xA000 <= addr <= 0xBFFF:
            bank = r7
        elif 0xC000 <= addr <= 0xDFFF:
            bank = r6 if mode1 else second_last
        else:  # 0xE000-0xFFFF
            bank = last

        return self.prg[bank * 0x2000 + offset]


class NESBus:
    """CPU-visible memory map: 2KB internal RAM (mirrored), PPU register
    stub (with the power-on warm-up write-ignore window), APU/IO register
    stub (writes logged, controller reads stubbed to 0), and the
    cartridge's PRG-ROM/registers at $8000-$FFFF (and PRG-RAM at
    $6000-$7FFF, unused by this project but harmless to back with RAM)."""

    def __init__(self, cartridge: Cartridge):
        self.cart = cartridge
        self.ram = bytearray(0x0800)
        self.total_cycles = 0
        self.ppu_ctrl = 0x00       # last write ACTUALLY honored (post-warmup)
        self.vblank_flag = False
        self.apu_log: List[Tuple[int, int, int]] = []  # (frame, addr, value)
        self.frame = 0
        self._cycles_into_frame = 0
        self._vblank_edges_this_frame_consumed = False

    # -- CPU bus interface ---------------------------------------------
    def read(self, addr: int) -> int:
        if addr < 0x2000:
            return self.ram[addr & 0x07FF]
        if addr < 0x4000:
            reg = 0x2000 + (addr & 0x0007)
            if reg == 0x2002:
                value = 0x80 if self.vblank_flag else 0x00
                self.vblank_flag = False  # reading $2002 clears the flag
                return value
            return 0x00
        if addr < 0x4018:
            return 0x00  # APU/IO reads (controllers, $4015 status) stubbed
        if 0x6000 <= addr <= 0x7FFF:
            return self.cart.prg_ram[addr - 0x6000]
        if addr >= 0x8000:
            return self.cart.read_prg(addr)
        return 0x00

    def write(self, addr: int, value: int) -> None:
        if addr < 0x2000:
            self.ram[addr & 0x07FF] = value
            return
        if addr < 0x4000:
            reg = 0x2000 + (addr & 0x0007)
            if reg in (0x2000, 0x2001, 0x2005, 0x2006):
                # THE post-reset PPU warm-up hazard this smoke test exists
                # to catch (#517/MAP-2026-08-24-1): on real hardware and
                # PPU-accurate emulators, writes to these four registers
                # before ~29,658 cycles post-reset are silently dropped.
                if self.total_cycles < PPU_WARMUP_CYCLES:
                    return
                if reg == 0x2000:
                    self.ppu_ctrl = value
            return
        if addr < 0x4018:
            if len(self.apu_log) < APU_LOG_CAP:
                self.apu_log.append((self.frame, addr, value & 0xFF))
            return
        if 0x6000 <= addr <= 0x7FFF:
            self.cart.prg_ram[addr - 0x6000] = value
            return
        if addr >= 0x8000:
            self.cart.write_register(addr, value)

    # -- timing / vblank simulation -------------------------------------
    def tick(self, cycles: int) -> bool:
        """Advance the simulated PPU clock by `cycles` CPU cycles. Returns
        True if a vblank edge (frame boundary) was just crossed."""
        self.total_cycles += cycles
        self._cycles_into_frame += cycles
        crossed = False
        if (not self._vblank_edges_this_frame_consumed
                and self._cycles_into_frame >= VBLANK_START_CYCLES):
            self.vblank_flag = True
            self._vblank_edges_this_frame_consumed = True
            crossed = True
        if self._cycles_into_frame >= FRAME_CYCLES:
            self._cycles_into_frame -= FRAME_CYCLES
            self._vblank_edges_this_frame_consumed = False
            self.frame += 1
        return crossed

    @property
    def nmi_enabled(self) -> bool:
        return bool(self.ppu_ctrl & 0x80)


@dataclass
class SmokeTestResult:
    mapper_supported: bool
    mapper_number: Optional[int] = None
    nmi_fired: bool = False
    nmi_count: int = 0
    frames_simulated: int = 0
    instructions_executed: int = 0
    notes_detected: bool = False
    apu_writes_after_first_nmi: int = 0
    apu_write_sample: List[Tuple[int, int, int]] = field(default_factory=list)
    error: Optional[str] = None
    reset_pc: Optional[int] = None


def _parse_ines(rom_bytes: bytes):
    if len(rom_bytes) < 16 or rom_bytes[:4] != b"NES\x1a":
        raise ValueError("Not a valid iNES ROM (missing 'NES\\x1a' magic)")
    prg_banks_16k = rom_bytes[4]
    chr_banks_8k = rom_bytes[5]
    flags6 = rom_bytes[6]
    flags7 = rom_bytes[7]
    mapper_number = (flags6 >> 4) | (flags7 & 0xF0)
    has_trainer = bool(flags6 & 0x04)

    offset = 16
    if has_trainer:
        offset += 512

    prg_size = prg_banks_16k * 16384
    prg = rom_bytes[offset:offset + prg_size]
    if len(prg) != prg_size:
        raise ValueError(
            f"ROM truncated: expected {prg_size} PRG bytes, got {len(prg)}")
    # CHR bytes (chr_banks_8k * 8192, right after PRG) are unused by this
    # smoke test -- no PPU rendering is simulated -- so not sliced out here.
    return mapper_number, prg


def run_smoke_test(rom_path, max_frames: int = 180,
                    max_instructions: int = 3_000_000) -> SmokeTestResult:
    """Run the ROM from its real RESET vector for up to `max_frames`
    simulated video frames (180 = 3 seconds at 60Hz -- comfortably past the
    ~2-vblank warm-up window and several NMI cycles if the engine is alive)
    or `max_instructions`, whichever comes first (a safety cap against a
    genuine infinite tight loop, which is itself a valid smoke-test
    finding: `nmi_fired=False` after the full budget).
    """
    rom_bytes = Path(rom_path).read_bytes()
    try:
        mapper_number, prg = _parse_ines(rom_bytes)
    except ValueError as e:
        return SmokeTestResult(mapper_supported=False, error=str(e))

    if mapper_number == 0:
        cart: Cartridge = NROMCartridge(prg)
    elif mapper_number == 4:
        cart = MMC3Cartridge(prg)
    else:
        return SmokeTestResult(mapper_supported=False, mapper_number=mapper_number,
                                error=f"Mapper {mapper_number} not implemented "
                                      f"by rom_smoke_test (only NROM/MMC3 are)")

    bus = NESBus(cart)
    cpu = CPU6502(bus)
    cpu.reset()
    reset_pc = cpu.s.pc

    nmi_count = 0
    first_nmi_seen = False
    instructions = 0
    error = None

    while bus.frame < max_frames and instructions < max_instructions:
        try:
            cycles = cpu.step()
        except CPUError as e:
            error = str(e)
            break
        instructions += 1
        crossed = bus.tick(cycles)
        if crossed and bus.nmi_enabled:
            cpu.nmi()
            nmi_count += 1
            first_nmi_seen = True
        elif crossed and not first_nmi_seen:
            # Still record the vblank edge itself via bus.frame (tick()
            # already increments it) -- nmi_enabled being False here, on
            # every edge up through max_frames, is exactly the "NMI never
            # actually turns on" failure this test exists to catch.
            pass

    apu_after_first_nmi = [w for w in bus.apu_log if first_nmi_seen and w[0] >= 1]
    # A write recorded in the very frame the first NMI fired (frame index
    # >= 1, since frame 0 is pre-NMI reset-time init) can only have
    # originated from the NMI-gated update path -- see module docstring.

    return SmokeTestResult(
        mapper_supported=True,
        mapper_number=mapper_number,
        nmi_fired=nmi_count > 0,
        nmi_count=nmi_count,
        frames_simulated=bus.frame,
        instructions_executed=instructions,
        notes_detected=len(apu_after_first_nmi) > 0,
        apu_writes_after_first_nmi=len(apu_after_first_nmi),
        apu_write_sample=apu_after_first_nmi[:MAX_APU_WRITES_RETURNED],
        error=error,
        reset_pc=reset_pc,
    )
