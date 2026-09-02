"""Unit tests for debug/cpu6502.py's 6502 interpreter, in isolation from any
NES-specific bus/mapper concerns (see tests/test_rom_smoke_test.py for the
full ROM-execution integration tests). A simple flat 64KB RAM bus is used
here so these tests pin CPU correctness independent of memory-mapping."""

import pytest

from debug.cpu6502 import CPU6502, CPUError, FLAG_C, FLAG_N, FLAG_V, FLAG_Z


class FlatRAMBus:
    """Trivial 64KB RAM bus -- every address is plain read/write memory,
    no mirroring/mapping. Good enough for pinning CPU semantics."""

    def __init__(self):
        self.mem = bytearray(0x10000)

    def read(self, addr):
        return self.mem[addr & 0xFFFF]

    def write(self, addr, value):
        self.mem[addr & 0xFFFF] = value & 0xFF

    def load(self, addr, data):
        for i, b in enumerate(data):
            self.mem[(addr + i) & 0xFFFF] = b


@pytest.fixture
def cpu():
    bus = FlatRAMBus()
    c = CPU6502(bus)
    return c, bus


def run(cpu, bus, addr, program, start_pc=None):
    bus.load(addr, program)
    cpu.s.pc = start_pc if start_pc is not None else addr
    return cpu


class TestLoadStore:
    def test_lda_immediate_sets_accumulator(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA9, 0x42])  # LDA #$42
        c.step()
        assert c.s.a == 0x42
        assert not c.s.p & FLAG_Z
        assert not c.s.p & FLAG_N

    def test_lda_immediate_zero_sets_zero_flag(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA9, 0x00])
        c.step()
        assert c.s.p & FLAG_Z

    def test_lda_immediate_negative_sets_negative_flag(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA9, 0x80])
        c.step()
        assert c.s.p & FLAG_N

    def test_sta_absolute_roundtrips_through_memory(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA9, 0x37, 0x8D, 0x00, 0x03])  # LDA #$37; STA $0300
        c.step(); c.step()
        assert bus.read(0x0300) == 0x37

    def test_ldx_ldy_and_transfers(self, cpu):
        c, bus = cpu
        # LDX #$05; TXA; TAY; INY
        run(c, bus, 0x8000, [0xA2, 0x05, 0x8A, 0xA8, 0xC8])
        for _ in range(4):
            c.step()
        assert c.s.x == 0x05
        assert c.s.a == 0x05
        assert c.s.y == 0x06


class TestArithmetic:
    def test_adc_no_carry(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0x18, 0xA9, 0x01, 0x69, 0x01])  # CLC; LDA #1; ADC #1
        for _ in range(3):
            c.step()
        assert c.s.a == 0x02
        assert not c.s.p & FLAG_C

    def test_adc_sets_carry_on_overflow(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0x18, 0xA9, 0xFF, 0x69, 0x01])  # CLC; LDA #$FF; ADC #1
        for _ in range(3):
            c.step()
        assert c.s.a == 0x00
        assert c.s.p & FLAG_C
        assert c.s.p & FLAG_Z

    def test_adc_sets_signed_overflow_flag(self, cpu):
        c, bus = cpu
        # 0x7F + 0x01 = 0x80: signed overflow (positive + positive = negative)
        run(c, bus, 0x8000, [0x18, 0xA9, 0x7F, 0x69, 0x01])
        for _ in range(3):
            c.step()
        assert c.s.a == 0x80
        assert c.s.p & FLAG_V

    def test_sbc_with_carry_set_is_clean_subtract(self, cpu):
        c, bus = cpu
        # SEC; LDA #5; SBC #3 -> 2, carry stays set (no borrow)
        run(c, bus, 0x8000, [0x38, 0xA9, 0x05, 0xE9, 0x03])
        for _ in range(3):
            c.step()
        assert c.s.a == 0x02
        assert c.s.p & FLAG_C

    def test_cmp_sets_carry_when_a_gte_operand(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA9, 0x05, 0xC9, 0x03])  # LDA #5; CMP #3
        c.step(); c.step()
        assert c.s.p & FLAG_C
        assert not c.s.p & FLAG_Z

    def test_cmp_sets_zero_when_equal(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA9, 0x05, 0xC9, 0x05])
        c.step(); c.step()
        assert c.s.p & FLAG_Z
        assert c.s.p & FLAG_C


class TestIncDec:
    def test_inx_wraps_at_256(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA2, 0xFF, 0xE8])  # LDX #$FF; INX
        c.step(); c.step()
        assert c.s.x == 0x00
        assert c.s.p & FLAG_Z

    def test_dec_memory(self, cpu):
        c, bus = cpu
        bus.write(0x10, 0x01)
        run(c, bus, 0x8000, [0xC6, 0x10])  # DEC $10 (zeropage)
        c.step()
        assert bus.read(0x10) == 0x00
        assert c.s.p & FLAG_Z


class TestBranchesAndJumps:
    def test_beq_taken_when_zero_flag_set(self, cpu):
        c, bus = cpu
        # LDA #0 (sets Z); BEQ +2 (skip the next LDA); LDA #$FF; LDA #$AA
        run(c, bus, 0x8000, [0xA9, 0x00, 0xF0, 0x02, 0xA9, 0xFF, 0xA9, 0xAA])
        c.step()  # LDA #0
        c.step()  # BEQ, taken -> pc jumps past the LDA #$FF
        c.step()  # should execute LDA #$AA, not LDA #$FF
        assert c.s.a == 0xAA

    def test_bne_not_taken_when_zero_flag_set(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA9, 0x00, 0xD0, 0x02, 0xA9, 0xFF, 0xA9, 0xAA])
        c.step()  # LDA #0
        c.step()  # BNE, not taken
        c.step()  # falls through to LDA #$FF
        assert c.s.a == 0xFF

    def test_jmp_absolute(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0x4C, 0x00, 0x90])  # JMP $9000
        c.step()
        assert c.s.pc == 0x9000

    def test_jsr_rts_roundtrips_pc_and_stack(self, cpu):
        c, bus = cpu
        # $8000: JSR $9000
        # $9000: RTS
        bus.load(0x8000, [0x20, 0x00, 0x90])
        bus.load(0x9000, [0x60])
        c.s.pc = 0x8000
        c.step()  # JSR -> pc = 0x9000, return addr (0x8002) pushed
        assert c.s.pc == 0x9000
        c.step()  # RTS -> pc = 0x8002 + 1 = 0x8003
        assert c.s.pc == 0x8003


class TestStackAndFlags:
    def test_pha_pla_roundtrip(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0xA9, 0x55, 0x48, 0xA9, 0x00, 0x68])  # LDA #$55; PHA; LDA #0; PLA
        for _ in range(4):
            c.step()
        assert c.s.a == 0x55

    def test_sei_sets_interrupt_disable(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0x78])  # SEI
        c.step()
        assert c.s.p & 0x04  # FLAG_I

    def test_clc_sec(self, cpu):
        c, bus = cpu
        run(c, bus, 0x8000, [0x38, 0x18])  # SEC; CLC
        c.step()
        assert c.s.p & FLAG_C
        c.step()
        assert not c.s.p & FLAG_C


class TestNMIAndReset:
    def test_reset_reads_vector_from_fffc(self, cpu):
        c, bus = cpu
        bus.write(0xFFFC, 0x00)
        bus.write(0xFFFD, 0x80)
        c.reset()
        assert c.s.pc == 0x8000

    def test_nmi_pushes_pc_and_flags_then_jumps_to_vector(self, cpu):
        c, bus = cpu
        bus.write(0xFFFA, 0x34)
        bus.write(0xFFFB, 0x12)
        c.s.pc = 0xABCD
        c.s.sp = 0xFF
        cycles = c.nmi()
        assert c.s.pc == 0x1234
        assert cycles == 7
        # Stack: SP decremented by 3 (PC hi, PC lo, flags)
        assert c.s.sp == 0xFC
        # Verify pushed return address is the original PC
        pushed_lo = bus.read(0x01FE)
        pushed_hi = bus.read(0x01FF)
        assert (pushed_hi << 8 | pushed_lo) == 0xABCD


class TestIllegalOpcode:
    def test_undocumented_opcode_raises_cpu_error(self, cpu):
        c, bus = cpu
        # $02 is not in the official documented opcode set.
        run(c, bus, 0x8000, [0x02])
        with pytest.raises(CPUError):
            c.step()


class TestIndirectAddressing:
    def test_jmp_indirect_page_wrap_bug_reproduced(self, cpu):
        c, bus = cpu
        # Classic 6502 bug: JMP ($30FF) reads high byte from $3000, not $3100.
        bus.write(0x30FF, 0x00)
        bus.write(0x3000, 0x90)  # if the bug is reproduced, hi byte = $90
        bus.write(0x3100, 0xFF)  # if NOT reproduced (naive +1), hi byte = $FF
        run(c, bus, 0x8000, [0x6C, 0xFF, 0x30])  # JMP ($30FF)
        c.step()
        assert c.s.pc == 0x9000

    def test_indirect_indexed_indy(self, cpu):
        c, bus = cpu
        # LDY #$00 is implicit via cpu default y=0; set up ($10),Y
        bus.write(0x10, 0x00)
        bus.write(0x11, 0x90)
        bus.write(0x9000, 0x42)
        run(c, bus, 0x8000, [0xB1, 0x10])  # LDA ($10),Y  (Y=0)
        c.step()
        assert c.s.a == 0x42
