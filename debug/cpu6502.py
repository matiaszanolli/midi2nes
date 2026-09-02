"""Minimal but real MOS 6502 (NTSC 2A03, no decimal mode) CPU interpreter.

Written for #517's execution-based ROM smoke test (`debug/rom_smoke_test.py`):
the validation pipeline needs to know whether a compiled ROM's `reset`/`nmi`
code actually *runs* (NMI fires, real APU register values get written), not
just whether the right bytes exist somewhere in the file
(`debug/rom_diagnostics.py`'s prior static-only checks).

Scope, deliberately: only the 151 official (documented) opcodes -- this
project's own `.asm` sources and CC65-assembled output never emit illegal/
undocumented opcodes, so there's nothing to gain from supporting them here.
No decimal mode (the 2A03 disables it in hardware; ADC/SBC never do BCD).
Cycle counts follow the standard 6502 reference (branch-taken/page-cross
penalties included) since the smoke test derives PPU vblank timing from the
running cycle count -- approximate timing would either starve NMI or fire it
far too often, defeating the point of the test.
"""

from dataclasses import dataclass
from typing import Optional


class CPUError(Exception):
    """Raised on a genuinely fatal CPU condition (BRK reached, stack
    underflow/overflow, or -- most usefully for a smoke test -- infinite
    tight-loop detection is left to the caller's instruction budget, not
    this class)."""


FLAG_C = 0x01
FLAG_Z = 0x02
FLAG_I = 0x04
FLAG_D = 0x08
FLAG_B = 0x10
FLAG_U = 0x20  # unused, always set when pushed
FLAG_V = 0x40
FLAG_N = 0x80


@dataclass
class CPUState:
    a: int = 0
    x: int = 0
    y: int = 0
    sp: int = 0xFD
    pc: int = 0
    p: int = FLAG_U | FLAG_I  # power-on: I set, unused bit set
    cycles: int = 0


class CPU6502:
    """A single 6502 core driven by `step()`, one instruction at a time.

    `bus` must implement `read(addr) -> int` and `write(addr, value)`, both
    over the full 16-bit address space (mirroring/banking is the bus's
    responsibility, not the CPU's -- matches how real hardware separates
    the two).
    """

    def __init__(self, bus):
        self.bus = bus
        self.s = CPUState()
        self._build_table()

    # -- convenience flag helpers -------------------------------------
    def _set_zn(self, value: int) -> None:
        value &= 0xFF
        if value == 0:
            self.s.p |= FLAG_Z
        else:
            self.s.p &= ~FLAG_Z
        if value & 0x80:
            self.s.p |= FLAG_N
        else:
            self.s.p &= ~FLAG_N

    def _get_flag(self, mask: int) -> bool:
        return bool(self.s.p & mask)

    def _set_flag(self, mask: int, on: bool) -> None:
        if on:
            self.s.p |= mask
        else:
            self.s.p &= ~mask

    # -- memory helpers ---------------------------------------------
    def _read(self, addr: int) -> int:
        return self.bus.read(addr & 0xFFFF) & 0xFF

    def _read16(self, addr: int) -> int:
        lo = self._read(addr)
        hi = self._read((addr + 1) & 0xFFFF)
        return lo | (hi << 8)

    def _read16_bug(self, addr: int) -> int:
        """Indirect JMP's famous page-wrap bug: if the low byte of the
        pointer is $FF, the high byte is fetched from the START of the
        same page, not the next page. Reproduced faithfully since real
        ROMs (and buggy ones a smoke test should treat identically to
        real hardware) can rely on it."""
        lo_addr = addr
        hi_addr = (addr & 0xFF00) | ((addr + 1) & 0x00FF)
        lo = self._read(lo_addr)
        hi = self._read(hi_addr)
        return lo | (hi << 8)

    def _write(self, addr: int, value: int) -> None:
        self.bus.write(addr & 0xFFFF, value & 0xFF)

    def _push(self, value: int) -> None:
        self._write(0x0100 | self.s.sp, value & 0xFF)
        self.s.sp = (self.s.sp - 1) & 0xFF

    def _pop(self) -> int:
        self.s.sp = (self.s.sp + 1) & 0xFF
        return self._read(0x0100 | self.s.sp)

    def _push16(self, value: int) -> None:
        self._push((value >> 8) & 0xFF)
        self._push(value & 0xFF)

    def _pop16(self) -> int:
        lo = self._pop()
        hi = self._pop()
        return lo | (hi << 8)

    # -- power-on / reset ---------------------------------------------
    def reset(self, pc: Optional[int] = None) -> None:
        self.s = CPUState()
        self.s.pc = pc if pc is not None else self._read16(0xFFFC)

    def nmi(self) -> int:
        """Push PC+flags and jump to the NMI vector; NMI ignores the I
        flag on real hardware, matched here. Returns cycles consumed (7,
        standard for any hardware interrupt)."""
        self._push16(self.s.pc)
        # B flag is clear on a hardware-triggered push (only BRK sets it).
        self._push((self.s.p | FLAG_U) & ~FLAG_B)
        self.s.p |= FLAG_I
        self.s.pc = self._read16(0xFFFA)
        self.s.cycles += 7
        return 7

    # -- addressing modes: each returns (effective_address, extra_cycle) --
    # extra_cycle is the page-cross penalty for modes that have one; the
    # opcode table adds it only for instructions where the penalty applies
    # (branches/some read-modify-write don't get it the same way).
    def _imm(self):
        addr = self.s.pc
        self.s.pc = (self.s.pc + 1) & 0xFFFF
        return addr, 0

    def _zp(self):
        addr = self._read(self.s.pc)
        self.s.pc = (self.s.pc + 1) & 0xFFFF
        return addr, 0

    def _zpx(self):
        base = self._read(self.s.pc)
        self.s.pc = (self.s.pc + 1) & 0xFFFF
        return (base + self.s.x) & 0xFF, 0

    def _zpy(self):
        base = self._read(self.s.pc)
        self.s.pc = (self.s.pc + 1) & 0xFFFF
        return (base + self.s.y) & 0xFF, 0

    def _abs(self):
        addr = self._read16(self.s.pc)
        self.s.pc = (self.s.pc + 2) & 0xFFFF
        return addr, 0

    def _absx(self):
        base = self._read16(self.s.pc)
        self.s.pc = (self.s.pc + 2) & 0xFFFF
        addr = (base + self.s.x) & 0xFFFF
        extra = 1 if (base & 0xFF00) != (addr & 0xFF00) else 0
        return addr, extra

    def _absy(self):
        base = self._read16(self.s.pc)
        self.s.pc = (self.s.pc + 2) & 0xFFFF
        addr = (base + self.s.y) & 0xFFFF
        extra = 1 if (base & 0xFF00) != (addr & 0xFF00) else 0
        return addr, extra

    def _ind(self):
        ptr = self._read16(self.s.pc)
        self.s.pc = (self.s.pc + 2) & 0xFFFF
        return self._read16_bug(ptr), 0

    def _indx(self):
        base = self._read(self.s.pc)
        self.s.pc = (self.s.pc + 1) & 0xFFFF
        ptr = (base + self.s.x) & 0xFF
        addr = self._read(ptr) | (self._read((ptr + 1) & 0xFF) << 8)
        return addr, 0

    def _indy(self):
        base = self._read(self.s.pc)
        self.s.pc = (self.s.pc + 1) & 0xFFFF
        lo = self._read(base)
        hi = self._read((base + 1) & 0xFF)
        addr = ((lo | (hi << 8)) + self.s.y) & 0xFFFF
        extra = 1 if (lo | (hi << 8)) & 0xFF00 != addr & 0xFF00 else 0
        return addr, extra

    def _rel(self):
        offset = self._read(self.s.pc)
        self.s.pc = (self.s.pc + 1) & 0xFFFF
        if offset & 0x80:
            offset -= 0x100
        return offset, 0

    # -- instruction implementations -----------------------------------
    def _op_lda(self, addr):
        self.s.a = self._read(addr)
        self._set_zn(self.s.a)

    def _op_ldx(self, addr):
        self.s.x = self._read(addr)
        self._set_zn(self.s.x)

    def _op_ldy(self, addr):
        self.s.y = self._read(addr)
        self._set_zn(self.s.y)

    def _op_sta(self, addr):
        self._write(addr, self.s.a)

    def _op_stx(self, addr):
        self._write(addr, self.s.x)

    def _op_sty(self, addr):
        self._write(addr, self.s.y)

    def _op_adc(self, addr):
        m = self._read(addr)
        carry = 1 if self._get_flag(FLAG_C) else 0
        total = self.s.a + m + carry
        self._set_flag(FLAG_C, total > 0xFF)
        result = total & 0xFF
        self._set_flag(FLAG_V, (~(self.s.a ^ m) & (self.s.a ^ result) & 0x80) != 0)
        self.s.a = result
        self._set_zn(self.s.a)

    def _op_sbc(self, addr):
        m = self._read(addr) ^ 0xFF
        carry = 1 if self._get_flag(FLAG_C) else 0
        total = self.s.a + m + carry
        self._set_flag(FLAG_C, total > 0xFF)
        result = total & 0xFF
        self._set_flag(FLAG_V, (~(self.s.a ^ m) & (self.s.a ^ result) & 0x80) != 0)
        self.s.a = result
        self._set_zn(self.s.a)

    def _cmp_base(self, reg, addr):
        m = self._read(addr)
        result = (reg - m) & 0x1FF
        self._set_flag(FLAG_C, reg >= m)
        self._set_zn(result & 0xFF)

    def _op_cmp(self, addr):
        self._cmp_base(self.s.a, addr)

    def _op_cpx(self, addr):
        self._cmp_base(self.s.x, addr)

    def _op_cpy(self, addr):
        self._cmp_base(self.s.y, addr)

    def _op_and(self, addr):
        self.s.a &= self._read(addr)
        self._set_zn(self.s.a)

    def _op_ora(self, addr):
        self.s.a |= self._read(addr)
        self._set_zn(self.s.a)

    def _op_eor(self, addr):
        self.s.a ^= self._read(addr)
        self._set_zn(self.s.a)

    def _op_bit(self, addr):
        m = self._read(addr)
        self._set_flag(FLAG_Z, (self.s.a & m) == 0)
        self._set_flag(FLAG_V, (m & 0x40) != 0)
        self._set_flag(FLAG_N, (m & 0x80) != 0)

    def _op_inc(self, addr):
        v = (self._read(addr) + 1) & 0xFF
        self._write(addr, v)
        self._set_zn(v)

    def _op_dec(self, addr):
        v = (self._read(addr) - 1) & 0xFF
        self._write(addr, v)
        self._set_zn(v)

    def _op_asl_mem(self, addr):
        v = self._read(addr)
        self._set_flag(FLAG_C, (v & 0x80) != 0)
        v = (v << 1) & 0xFF
        self._write(addr, v)
        self._set_zn(v)

    def _op_lsr_mem(self, addr):
        v = self._read(addr)
        self._set_flag(FLAG_C, (v & 0x01) != 0)
        v = v >> 1
        self._write(addr, v)
        self._set_zn(v)

    def _op_rol_mem(self, addr):
        v = self._read(addr)
        carry_in = 1 if self._get_flag(FLAG_C) else 0
        self._set_flag(FLAG_C, (v & 0x80) != 0)
        v = ((v << 1) | carry_in) & 0xFF
        self._write(addr, v)
        self._set_zn(v)

    def _op_ror_mem(self, addr):
        v = self._read(addr)
        carry_in = 0x80 if self._get_flag(FLAG_C) else 0
        self._set_flag(FLAG_C, (v & 0x01) != 0)
        v = (v >> 1) | carry_in
        self._write(addr, v)
        self._set_zn(v)

    def _op_asl_acc(self):
        self._set_flag(FLAG_C, (self.s.a & 0x80) != 0)
        self.s.a = (self.s.a << 1) & 0xFF
        self._set_zn(self.s.a)

    def _op_lsr_acc(self):
        self._set_flag(FLAG_C, (self.s.a & 0x01) != 0)
        self.s.a >>= 1
        self._set_zn(self.s.a)

    def _op_rol_acc(self):
        carry_in = 1 if self._get_flag(FLAG_C) else 0
        self._set_flag(FLAG_C, (self.s.a & 0x80) != 0)
        self.s.a = ((self.s.a << 1) | carry_in) & 0xFF
        self._set_zn(self.s.a)

    def _op_ror_acc(self):
        carry_in = 0x80 if self._get_flag(FLAG_C) else 0
        self._set_flag(FLAG_C, (self.s.a & 0x01) != 0)
        self.s.a = (self.s.a >> 1) | carry_in
        self._set_zn(self.s.a)

    def _branch(self, cond: bool):
        offset, _ = self._rel()
        extra = 0
        if cond:
            old_pc = self.s.pc
            self.s.pc = (self.s.pc + offset) & 0xFFFF
            extra = 1
            if (old_pc & 0xFF00) != (self.s.pc & 0xFF00):
                extra += 1
        return extra

    def _build_table(self):
        # name -> (addressing-mode fn or None, base_cycles, has_page_penalty)
        # Table entries: opcode -> (mnemonic, mode, cycles)
        # mode is one of: 'imp','acc','imm','zp','zpx','zpy','abs','absx',
        # 'absy','ind','indx','indy','rel'
        T = {}

        def add(op, mnem, mode, cycles):
            T[op] = (mnem, mode, cycles)

        # Loads
        add(0xA9, 'LDA', 'imm', 2); add(0xA5, 'LDA', 'zp', 3)
        add(0xB5, 'LDA', 'zpx', 4); add(0xAD, 'LDA', 'abs', 4)
        add(0xBD, 'LDA', 'absx', 4); add(0xB9, 'LDA', 'absy', 4)
        add(0xA1, 'LDA', 'indx', 6); add(0xB1, 'LDA', 'indy', 5)

        add(0xA2, 'LDX', 'imm', 2); add(0xA6, 'LDX', 'zp', 3)
        add(0xB6, 'LDX', 'zpy', 4); add(0xAE, 'LDX', 'abs', 4)
        add(0xBE, 'LDX', 'absy', 4)

        add(0xA0, 'LDY', 'imm', 2); add(0xA4, 'LDY', 'zp', 3)
        add(0xB4, 'LDY', 'zpx', 4); add(0xAC, 'LDY', 'abs', 4)
        add(0xBC, 'LDY', 'absx', 4)

        # Stores
        add(0x85, 'STA', 'zp', 3); add(0x95, 'STA', 'zpx', 4)
        add(0x8D, 'STA', 'abs', 4); add(0x9D, 'STA', 'absx', 5)
        add(0x99, 'STA', 'absy', 5); add(0x81, 'STA', 'indx', 6)
        add(0x91, 'STA', 'indy', 6)

        add(0x86, 'STX', 'zp', 3); add(0x96, 'STX', 'zpy', 4)
        add(0x8E, 'STX', 'abs', 4)

        add(0x84, 'STY', 'zp', 3); add(0x94, 'STY', 'zpx', 4)
        add(0x8C, 'STY', 'abs', 4)

        # Transfers
        add(0xAA, 'TAX', 'imp', 2); add(0x8A, 'TXA', 'imp', 2)
        add(0xA8, 'TAY', 'imp', 2); add(0x98, 'TYA', 'imp', 2)
        add(0x9A, 'TXS', 'imp', 2); add(0xBA, 'TSX', 'imp', 2)

        # Stack
        add(0x48, 'PHA', 'imp', 3); add(0x68, 'PLA', 'imp', 4)
        add(0x08, 'PHP', 'imp', 3); add(0x28, 'PLP', 'imp', 4)

        # Inc/Dec
        add(0xE6, 'INC', 'zp', 5); add(0xF6, 'INC', 'zpx', 6)
        add(0xEE, 'INC', 'abs', 6); add(0xFE, 'INC', 'absx', 7)
        add(0xC6, 'DEC', 'zp', 5); add(0xD6, 'DEC', 'zpx', 6)
        add(0xCE, 'DEC', 'abs', 6); add(0xDE, 'DEC', 'absx', 7)
        add(0xE8, 'INX', 'imp', 2); add(0xC8, 'INY', 'imp', 2)
        add(0xCA, 'DEX', 'imp', 2); add(0x88, 'DEY', 'imp', 2)

        # Arithmetic
        add(0x69, 'ADC', 'imm', 2); add(0x65, 'ADC', 'zp', 3)
        add(0x75, 'ADC', 'zpx', 4); add(0x6D, 'ADC', 'abs', 4)
        add(0x7D, 'ADC', 'absx', 4); add(0x79, 'ADC', 'absy', 4)
        add(0x61, 'ADC', 'indx', 6); add(0x71, 'ADC', 'indy', 5)

        add(0xE9, 'SBC', 'imm', 2); add(0xE5, 'SBC', 'zp', 3)
        add(0xF5, 'SBC', 'zpx', 4); add(0xED, 'SBC', 'abs', 4)
        add(0xFD, 'SBC', 'absx', 4); add(0xF9, 'SBC', 'absy', 4)
        add(0xE1, 'SBC', 'indx', 6); add(0xF1, 'SBC', 'indy', 5)

        add(0xC9, 'CMP', 'imm', 2); add(0xC5, 'CMP', 'zp', 3)
        add(0xD5, 'CMP', 'zpx', 4); add(0xCD, 'CMP', 'abs', 4)
        add(0xDD, 'CMP', 'absx', 4); add(0xD9, 'CMP', 'absy', 4)
        add(0xC1, 'CMP', 'indx', 6); add(0xD1, 'CMP', 'indy', 5)

        add(0xE0, 'CPX', 'imm', 2); add(0xE4, 'CPX', 'zp', 3)
        add(0xEC, 'CPX', 'abs', 4)
        add(0xC0, 'CPY', 'imm', 2); add(0xC4, 'CPY', 'zp', 3)
        add(0xCC, 'CPY', 'abs', 4)

        # Logic
        add(0x29, 'AND', 'imm', 2); add(0x25, 'AND', 'zp', 3)
        add(0x35, 'AND', 'zpx', 4); add(0x2D, 'AND', 'abs', 4)
        add(0x3D, 'AND', 'absx', 4); add(0x39, 'AND', 'absy', 4)
        add(0x21, 'AND', 'indx', 6); add(0x31, 'AND', 'indy', 5)

        add(0x09, 'ORA', 'imm', 2); add(0x05, 'ORA', 'zp', 3)
        add(0x15, 'ORA', 'zpx', 4); add(0x0D, 'ORA', 'abs', 4)
        add(0x1D, 'ORA', 'absx', 4); add(0x19, 'ORA', 'absy', 4)
        add(0x01, 'ORA', 'indx', 6); add(0x11, 'ORA', 'indy', 5)

        add(0x49, 'EOR', 'imm', 2); add(0x45, 'EOR', 'zp', 3)
        add(0x55, 'EOR', 'zpx', 4); add(0x4D, 'EOR', 'abs', 4)
        add(0x5D, 'EOR', 'absx', 4); add(0x59, 'EOR', 'absy', 4)
        add(0x41, 'EOR', 'indx', 6); add(0x51, 'EOR', 'indy', 5)

        add(0x24, 'BIT', 'zp', 3); add(0x2C, 'BIT', 'abs', 4)

        # Shifts/rotates
        add(0x0A, 'ASL', 'acc', 2); add(0x06, 'ASL', 'zp', 5)
        add(0x16, 'ASL', 'zpx', 6); add(0x0E, 'ASL', 'abs', 6)
        add(0x1E, 'ASL', 'absx', 7)

        add(0x4A, 'LSR', 'acc', 2); add(0x46, 'LSR', 'zp', 5)
        add(0x56, 'LSR', 'zpx', 6); add(0x4E, 'LSR', 'abs', 6)
        add(0x5E, 'LSR', 'absx', 7)

        add(0x2A, 'ROL', 'acc', 2); add(0x26, 'ROL', 'zp', 5)
        add(0x36, 'ROL', 'zpx', 6); add(0x2E, 'ROL', 'abs', 6)
        add(0x3E, 'ROL', 'absx', 7)

        add(0x6A, 'ROR', 'acc', 2); add(0x66, 'ROR', 'zp', 5)
        add(0x76, 'ROR', 'zpx', 6); add(0x6E, 'ROR', 'abs', 6)
        add(0x7E, 'ROR', 'absx', 7)

        # Jumps/calls
        add(0x4C, 'JMP', 'abs', 3); add(0x6C, 'JMP', 'ind', 5)
        add(0x20, 'JSR', 'abs', 6); add(0x60, 'RTS', 'imp', 6)
        add(0x40, 'RTI', 'imp', 6)

        # Branches
        add(0x10, 'BPL', 'rel', 2); add(0x30, 'BMI', 'rel', 2)
        add(0x50, 'BVC', 'rel', 2); add(0x70, 'BVS', 'rel', 2)
        add(0x90, 'BCC', 'rel', 2); add(0xB0, 'BCS', 'rel', 2)
        add(0xD0, 'BNE', 'rel', 2); add(0xF0, 'BEQ', 'rel', 2)

        # Status flags
        add(0x18, 'CLC', 'imp', 2); add(0x38, 'SEC', 'imp', 2)
        add(0x58, 'CLI', 'imp', 2); add(0x78, 'SEI', 'imp', 2)
        add(0xB8, 'CLV', 'imp', 2); add(0xD8, 'CLD', 'imp', 2)
        add(0xF8, 'SED', 'imp', 2)

        # Misc
        add(0xEA, 'NOP', 'imp', 2); add(0x00, 'BRK', 'imp', 7)

        self.table = T
        self._mode_fns = {
            'imm': self._imm, 'zp': self._zp, 'zpx': self._zpx,
            'zpy': self._zpy, 'abs': self._abs, 'absx': self._absx,
            'absy': self._absy, 'ind': self._ind, 'indx': self._indx,
            'indy': self._indy,
        }

    def step(self) -> int:
        """Execute one instruction, return cycles consumed. Raises
        CPUError on an opcode not in the official documented set (a real
        ROM built by this codebase's own asm sources never emits one --
        landing on one during simulation means execution has run off into
        data or a genuinely corrupt ROM, either of which the caller should
        treat as a smoke-test failure, not silently continue past)."""
        opcode = self._read(self.s.pc)
        self.s.pc = (self.s.pc + 1) & 0xFFFF

        entry = self.table.get(opcode)
        if entry is None:
            raise CPUError(
                f"Undocumented/illegal opcode ${opcode:02X} at "
                f"${(self.s.pc - 1) & 0xFFFF:04X} -- execution ran off "
                f"into data or a corrupt ROM.")
        mnem, mode, cycles = entry
        extra = 0

        if mode == 'imp':
            cycles += self._exec_implied(mnem)
        elif mode == 'acc':
            self._exec_acc(mnem)
        elif mode == 'rel':
            extra = self._exec_branch(mnem)
        else:
            addr, page_extra = self._mode_fns[mode]()
            extra = self._exec_addr(mnem, addr, mode, page_extra)

        total = cycles + extra
        self.s.cycles += total
        return total

    def _exec_implied(self, mnem: str) -> int:
        """Implied-mode ops. Returns extra cycles beyond the table value
        (RTS/RTI/JSR-adjacent implied ops are already correctly costed in
        the table; this only handles their side effects)."""
        if mnem == 'TAX':
            self.s.x = self.s.a; self._set_zn(self.s.x)
        elif mnem == 'TXA':
            self.s.a = self.s.x; self._set_zn(self.s.a)
        elif mnem == 'TAY':
            self.s.y = self.s.a; self._set_zn(self.s.y)
        elif mnem == 'TYA':
            self.s.a = self.s.y; self._set_zn(self.s.a)
        elif mnem == 'TXS':
            self.s.sp = self.s.x
        elif mnem == 'TSX':
            self.s.x = self.s.sp; self._set_zn(self.s.x)
        elif mnem == 'PHA':
            self._push(self.s.a)
        elif mnem == 'PLA':
            self.s.a = self._pop(); self._set_zn(self.s.a)
        elif mnem == 'PHP':
            self._push(self.s.p | FLAG_U | FLAG_B)
        elif mnem == 'PLP':
            self.s.p = (self._pop() | FLAG_U) & ~FLAG_B
        elif mnem == 'INX':
            self.s.x = (self.s.x + 1) & 0xFF; self._set_zn(self.s.x)
        elif mnem == 'INY':
            self.s.y = (self.s.y + 1) & 0xFF; self._set_zn(self.s.y)
        elif mnem == 'DEX':
            self.s.x = (self.s.x - 1) & 0xFF; self._set_zn(self.s.x)
        elif mnem == 'DEY':
            self.s.y = (self.s.y - 1) & 0xFF; self._set_zn(self.s.y)
        elif mnem == 'RTS':
            self.s.pc = (self._pop16() + 1) & 0xFFFF
        elif mnem == 'RTI':
            self.s.p = (self._pop() | FLAG_U) & ~FLAG_B
            self.s.pc = self._pop16()
        elif mnem == 'CLC':
            self._set_flag(FLAG_C, False)
        elif mnem == 'SEC':
            self._set_flag(FLAG_C, True)
        elif mnem == 'CLI':
            self._set_flag(FLAG_I, False)
        elif mnem == 'SEI':
            self._set_flag(FLAG_I, True)
        elif mnem == 'CLV':
            self._set_flag(FLAG_V, False)
        elif mnem == 'CLD':
            self._set_flag(FLAG_D, False)
        elif mnem == 'SED':
            self._set_flag(FLAG_D, True)
        elif mnem == 'NOP':
            pass
        elif mnem == 'BRK':
            # Real BRK pushes PC+2 and jumps through the IRQ/BRK vector
            # ($FFFE). This codebase's `irq: rti` stub is the only thing
            # that vector ever points to, so simulate the same real
            # semantics rather than treating BRK as fatal -- landing here
            # unexpectedly (misaligned execution reading a padding $00
            # byte as an instruction) already gets caught by the "did
            # anything sensible happen" checks in rom_smoke_test.py.
            self.s.pc = (self.s.pc + 1) & 0xFFFF
            self._push16(self.s.pc)
            self._push(self.s.p | FLAG_U | FLAG_B)
            self._set_flag(FLAG_I, True)
            self.s.pc = self._read16(0xFFFE)
        return 0

    def _exec_acc(self, mnem: str) -> None:
        if mnem == 'ASL':
            self._op_asl_acc()
        elif mnem == 'LSR':
            self._op_lsr_acc()
        elif mnem == 'ROL':
            self._op_rol_acc()
        elif mnem == 'ROR':
            self._op_ror_acc()

    def _exec_branch(self, mnem: str) -> int:
        cond_map: dict = {
            'BPL': not self._get_flag(FLAG_N),
            'BMI': self._get_flag(FLAG_N),
            'BVC': not self._get_flag(FLAG_V),
            'BVS': self._get_flag(FLAG_V),
            'BCC': not self._get_flag(FLAG_C),
            'BCS': self._get_flag(FLAG_C),
            'BNE': not self._get_flag(FLAG_Z),
            'BEQ': self._get_flag(FLAG_Z),
        }
        return self._branch(cond_map[mnem])

    def _exec_addr(self, mnem: str, addr: int, mode: str, page_extra: int) -> int:
        # Instructions that get the page-cross penalty when it applies;
        # STA/read-modify-write ops never do on real hardware.
        applies_page_penalty = mnem in (
            'LDA', 'LDX', 'LDY', 'ADC', 'SBC', 'CMP', 'AND', 'ORA', 'EOR')
        extra = page_extra if applies_page_penalty and mode in ('absx', 'absy', 'indy') else 0

        dispatch: dict = {
            'LDA': self._op_lda, 'LDX': self._op_ldx, 'LDY': self._op_ldy,
            'STA': self._op_sta, 'STX': self._op_stx, 'STY': self._op_sty,
            'ADC': self._op_adc, 'SBC': self._op_sbc,
            'CMP': self._op_cmp, 'CPX': self._op_cpx, 'CPY': self._op_cpy,
            'AND': self._op_and, 'ORA': self._op_ora, 'EOR': self._op_eor,
            'BIT': self._op_bit,
            'INC': self._op_inc, 'DEC': self._op_dec,
            'ASL': self._op_asl_mem, 'LSR': self._op_lsr_mem,
            'ROL': self._op_rol_mem, 'ROR': self._op_ror_mem,
        }
        if mnem == 'JMP':
            self.s.pc = addr
            return 0
        if mnem == 'JSR':
            self._push16((self.s.pc - 1) & 0xFFFF)
            self.s.pc = addr
            return 0
        fn = dispatch.get(mnem)
        if fn is None:
            raise CPUError(f"Unhandled mnemonic {mnem} in addressed dispatch")
        fn(addr)
        return extra
