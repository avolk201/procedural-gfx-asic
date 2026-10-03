"""Two-hart RV32I instruction-set simulator.

Each hart has one contiguous 32 KiB byte-addressed RAM: 24 KiB instruction
RAM followed by 8 KiB data RAM, per docs/cpu-contract.md section 4. Fetches
must be four-byte aligned; a misaligned fetch halts that hart as ``illegal``.
Device addresses begin at 0x40000000 and are delegated to the machine's
device callback. Retirement records are appended by ``step`` in execution
order, so interleaved harts share one deterministic trace stream.

halt record rather than escape from a cosimulation run.
This increment executes the RV32I OP, OP-IMM, load, store, branch, jump,
U-type, and FENCE instruction families. Other legal instruction families
raise NotImplementedError until added. When a family is implemented, its
reserved encodings must decode to an ``illegal`` halt record rather than
escape from a cosimulation run.
"""

import random

if __package__:
    from .rv32enc import decode_mnemonic, fields, unpack_b, unpack_j
else:
    from rv32enc import decode_mnemonic, fields, unpack_b, unpack_j


# Contract §4: 24 KiB I-RAM + 8 KiB D-RAM per hart.
RAM_BYTES = 0x8000
DEVICE_BASE = 0x40000000
MASK32 = 0xFFFFFFFF
HALT_REASONS = (None, 'ebreak', 'ecall', 'illegal', 'budget', 'bus')
LOADS = {'lb': 1, 'lbu': 1, 'lh': 2, 'lhu': 2, 'lw': 4}
STORES = {'sb': 1, 'sh': 2, 'sw': 4}
BRANCHES = {
    'beq': lambda a, b: a == b,
    'bne': lambda a, b: a != b,
    'blt': lambda a, b: s32(a) < s32(b),
    'bge': lambda a, b: s32(a) >= s32(b),
    'bltu': lambda a, b: a < b,
    'bgeu': lambda a, b: a >= b,
}
JUMPS = ('jal', 'jalr')


def w32(value):
    return value & MASK32


def s32(value):
    return value - (1 << 32) if value >= (1 << 31) else value


def sign_extend(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


class Hart:
    def __init__(self, hart_id=0):
        self.hart_id = hart_id
        self.x = [0] * 32
        self.pc = 0
        self.halted = None
        self.mem = bytearray(RAM_BYTES)

    def reg_read(self, n):
        if not 0 <= n < 32:
            raise IndexError(f'invalid register index: {n}')
        return 0 if n == 0 else self.x[n]

    def reg_write(self, n, value):
        if not 0 <= n < 32:
            raise IndexError(f'invalid register index: {n}')
        if n != 0:
            self.x[n] = w32(value)


class Machine:
    """Two-hart ISS with private RAM and a global retired-instruction budget.

    ``device_dispatch(hart_id, address, is_write, value, size)`` handles
    addresses at or above DEVICE_BASE. Values are right-justified; the device
    callback owns byte-lane placement for writes. Return ``None`` for an
    unmapped access; mapped reads return a 32-bit word and mapped writes
    return any non-None value.
    """

    def __init__(self, max_steps=100000, device_dispatch=None, hart_count=2):
        if max_steps < 0:
            raise ValueError('max_steps must be non-negative')
        if hart_count < 1:
            raise ValueError('hart_count must be positive')
        self.harts = [Hart(hart_id) for hart_id in range(hart_count)]
        self.max_steps = max_steps
        self.device_dispatch = device_dispatch
        self.trace = []
        self.steps = 0

    def _halt_at_budget(self):
        for hart_id, hart in enumerate(self.harts):
            if hart.halted is None:
                self._record_halt(hart_id, 'budget', hart.pc)

    def _record_halt(self, hart_id, reason, pc=None, word=None):
        hart = self.harts[hart_id]
        hart.halted = reason
        self.trace.append(','.join((
            str(hart_id),
            '' if pc is None else f'{pc:08x}',
            '' if word is None else f'{word:08x}',
            '', '', f'halt:{reason}', '', '', '',
        )))

    def _record_retirement(self, hart_id, pc, word, rd, value):
        self.trace.append(','.join((
            str(hart_id), f'{pc:08x}', f'{word:08x}', str(rd),
            f'{value:08x}', '', '', '', '',
        )))

    def dispatch_device(self, hart_id, address, is_write=False, value=0,
                        size=4):
        if address < DEVICE_BASE:
            raise ValueError(f'not a device address: {address:#x}')
        hart = self.harts[hart_id]
        if self.device_dispatch is None:
            self._record_halt(hart_id, 'bus', hart.pc)
            return None
        access_value = w32(value)
        if is_write:
            access_value &= (1 << (size * 8)) - 1
        result = self.device_dispatch(
            hart_id, address, is_write, access_value, size
        )
        if result is None:
            self._record_halt(hart_id, 'bus', hart.pc)
            return None
        return result if is_write else w32(result)

    def step(self, hart_id):
        if not 0 <= hart_id < len(self.harts):
            raise IndexError(f'invalid hart index: {hart_id}')
        hart = self.harts[hart_id]
        if hart.halted is not None:
            return False
        if self.steps >= self.max_steps:
            self._halt_at_budget()
            return False

        pc = hart.pc
        if pc & 0x3:
            self._record_halt(hart_id, 'illegal', pc)
            return False
        if pc < 0 or pc + 4 > len(hart.mem):
            self._record_halt(hart_id, 'bus', pc)
            return False

        word = int.from_bytes(hart.mem[pc:pc + 4], 'little')
        decoded = decode_instruction(word)
        if decoded is None:
            self._record_halt(hart_id, 'illegal', pc, word)
            return False
        mnemonic, instruction_fields = decoded
        if mnemonic in ('ecall', 'ebreak'):
            self._record_halt(hart_id, mnemonic, pc, word)
            return False

        rd = instruction_fields['rd']
        rs1 = hart.reg_read(instruction_fields['rs1'])
        rs2 = hart.reg_read(instruction_fields['rs2'])

        if mnemonic in ('add', 'sub', 'sll', 'slt', 'sltu', 'xor',
                        'srl', 'sra', 'or', 'and'):
            shift = rs2 & 0x1F
            result = {
                'add': lambda: rs1 + rs2,
                'sub': lambda: rs1 - rs2,
                'sll': lambda: rs1 << shift,
                'slt': lambda: int(s32(rs1) < s32(rs2)),
                'sltu': lambda: int(rs1 < rs2),
                'xor': lambda: rs1 ^ rs2,
                'srl': lambda: rs1 >> shift,
                'sra': lambda: s32(rs1) >> shift,
                'or': lambda: rs1 | rs2,
                'and': lambda: rs1 & rs2,
            }[mnemonic]()
        elif mnemonic in ('addi', 'slli', 'slti', 'sltiu', 'xori',
                          'srli', 'srai', 'ori', 'andi'):
            immediate = sign_extend(instruction_fields['imm12'], 12)
            shift = instruction_fields['imm12'] & 0x1F
            result = {
                'addi': lambda: rs1 + immediate,
                'slli': lambda: rs1 << shift,
                'slti': lambda: int(s32(rs1) < immediate),
                'sltiu': lambda: int(rs1 < w32(immediate)),
                'xori': lambda: rs1 ^ w32(immediate),
                'srli': lambda: rs1 >> shift,
                'srai': lambda: s32(rs1) >> shift,
                'ori': lambda: rs1 | w32(immediate),
                'andi': lambda: rs1 & w32(immediate),
            }[mnemonic]()
        elif mnemonic in ('lui', 'auipc'):
            imm = instruction_fields['imm20'] << 12
            result = imm if mnemonic == 'lui' else pc + imm
        elif mnemonic in LOADS or mnemonic in STORES:
            if mnemonic in LOADS:
                immediate = sign_extend(instruction_fields['imm12'], 12)
            else:
                immediate = sign_extend(
                    (instruction_fields['s_imm11_5'] << 5) |
                    instruction_fields['s_imm4_0'], 12
                )
            addr = w32(rs1 + immediate)
            if mnemonic in LOADS:
                size = LOADS[mnemonic]
                raw = self.mem_read(hart_id, addr, size, word)
                if raw is None:
                    return False
                result = (sign_extend(raw, size * 8)
                          if mnemonic in ('lb', 'lh') else raw)
                hart.reg_write(rd, result)
                value = hart.reg_read(rd)
                hart.pc = w32(pc + 4)
                self.steps += 1
                self.trace.append(','.join((
                    str(hart_id), f'{pc:08x}', f'{word:08x}', str(rd),
                    f'{value:08x}', mnemonic, f'{addr:08x}', str(size),
                    f'{raw:08x}',
                )))
            else:
                size = STORES[mnemonic]
                if not self.mem_write(hart_id, addr, size, rs2, word):
                    return False
                shift = (addr & 0x3) * 8
                lanes = ((rs2 & ((1 << (size * 8)) - 1)) << shift) & MASK32
                hart.pc = w32(pc + 4)
                self.steps += 1
                self.trace.append(','.join((
                    str(hart_id), f'{pc:08x}', f'{word:08x}', '', '',
                    mnemonic, f'{addr:08x}', str(size), f'{lanes:08x}',
                )))
            if self.steps >= self.max_steps:
                self._halt_at_budget()
            return True
        elif mnemonic in BRANCHES:
            if BRANCHES[mnemonic](rs1, rs2):
                hart.pc = w32(pc + unpack_b(word))
            else:
                hart.pc = w32(pc + 4)
            self.steps += 1
            self._record_retirement(hart_id, pc, word, 0, 0)
            if self.steps >= self.max_steps:
                self._halt_at_budget()
            return True
        elif mnemonic in JUMPS:
            if mnemonic == 'jal':
                target = w32(pc + unpack_j(word))
            else:
                immediate = sign_extend(instruction_fields['imm12'], 12)
                target = w32((rs1 + immediate) & ~1)
            hart.pc = target
            hart.reg_write(rd, pc + 4)
            self.steps += 1
            self._record_retirement(hart_id, pc, word, rd, hart.reg_read(rd))
            if self.steps >= self.max_steps:
                self._halt_at_budget()
            return True
        elif mnemonic == 'fence':
            hart.pc = w32(pc + 4)
            self.steps += 1
            self._record_retirement(hart_id, pc, word, 0, 0)
            if self.steps >= self.max_steps:
                self._halt_at_budget()
            return True
        else:
            raise NotImplementedError(f'{mnemonic} is not implemented')

        hart.reg_write(rd, result)
        hart.pc = w32(pc + 4)
        self.steps += 1
        self._record_retirement(hart_id, pc, word, rd, hart.reg_read(rd))
        if self.steps >= self.max_steps:
            self._halt_at_budget()
        return True

    def run(self, schedule='rr', seed=None):
        """Run round-robin, seeded-random, or a scripted hart-ID sequence."""
        if schedule == 'rr':
            next_hart = 0
            while any(hart.halted is None for hart in self.harts):
                if self.steps >= self.max_steps:
                    self._halt_at_budget()
                    break
                hart_id = next_hart
                next_hart = (next_hart + 1) % len(self.harts)
                if self.harts[hart_id].halted is None:
                    self.step(hart_id)
        elif schedule == 'random':
            rng = random.Random(seed)
            while any(hart.halted is None for hart in self.harts):
                if self.steps >= self.max_steps:
                    self._halt_at_budget()
                    break
                active_harts = [
                    hart_id for hart_id, hart in enumerate(self.harts)
                    if hart.halted is None
                ]
                self.step(rng.choice(active_harts))
        elif isinstance(schedule, str):
            raise ValueError(f'unsupported schedule: {schedule}')
        else:
            for hart_id in schedule:
                if self.steps >= self.max_steps:
                    self._halt_at_budget()
                    break
                self.step(hart_id)
        return self.steps

    def mem_read(self, hart_id, addr, size, word):
        """Raw transferred bytes right-justified, or None after a halt.

        Check order is load-bearing: alignment before region. M4 and M6
        exist to prove this order stays.
        """
        hart = self.harts[hart_id]
        if addr & (size - 1):
            self._record_halt(hart_id, 'illegal', hart.pc, word)
            return None
        if addr + size <= RAM_BYTES:
            return int.from_bytes(hart.mem[addr:addr + size], 'little')
        if addr >= DEVICE_BASE:
            device_word = self.dispatch_device(hart_id, addr, False, 0, size)
            if device_word is None:
                return None

            shift = (addr & 0x3) * 8
            mask = (1 << (size * 8)) - 1
            return (device_word >> shift) & mask
        self._record_halt(hart_id, 'bus', hart.pc, word)
        return None

    def mem_write(self, hart_id, addr, size, value, word):
        hart = self.harts[hart_id]
        if addr & (size - 1):
            self._record_halt(hart_id, 'illegal', hart.pc, word)
            return False
        if addr + size <= RAM_BYTES:
            shift = (addr & 3) * 8
            lane = ((1 << (size * 8)) - 1) << shift
            base = addr & ~3
            old = int.from_bytes(hart.mem[base:base + 4], 'little')
            merged = (old & ~lane) | ((value << shift) & lane)
            hart.mem[base:base + 4] = merged.to_bytes(4, 'little')
            return True
        if addr >= DEVICE_BASE:
            # Device models own byte-lane placement for writes.
            result = self.dispatch_device(hart_id, addr, True, value, size)
            return result is not None
        self._record_halt(hart_id, 'bus', hart.pc, word)
        return False


def decode_instruction(word):
    """Return the shared mnemonic and fields, or None for an illegal word."""
    mnemonic = decode_mnemonic(word)
    if mnemonic is None:
        return None
    return mnemonic, fields(word)