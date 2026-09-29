"""Two-hart RV32I instruction-set simulator.

Each hart has one contiguous 32 KiB byte-addressed RAM: 24 KiB instruction
RAM followed by 8 KiB data RAM, per docs/cpu-contract.md section 4. Fetches
must be four-byte aligned; a misaligned fetch halts that hart as ``illegal``.
Device addresses begin at 0x40000000 and are delegated to the machine's
device callback. Retirement records are appended by ``step`` in execution
order, so interleaved harts share one deterministic trace stream.

This increment executes the RV32I OP and OP-IMM instruction families.
Other legal instruction families raise NotImplementedError until added. When a
family is implemented, its reserved encodings must decode to an ``illegal``
halt record rather than escape from a cosimulation run.
"""

import random

if __package__:
    from .rv32enc import decode_mnemonic, fields
else:
    from rv32enc import decode_mnemonic, fields


# Contract §4: 24 KiB I-RAM + 8 KiB D-RAM per hart.
RAM_BYTES = 0x8000
DEVICE_BASE = 0x40000000
MASK32 = 0xFFFFFFFF
HALT_REASONS = (None, 'ebreak', 'ecall', 'illegal', 'budget', 'bus')


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

    ``device_dispatch(hart_id, address, is_write, value)`` handles addresses
    at or above DEVICE_BASE. Return ``None`` for an unmapped access; mapped
    reads return an integer and mapped writes return any non-None value.
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

    def dispatch_device(self, hart_id, address, is_write=False, value=0):
        if address < DEVICE_BASE:
            raise ValueError(f'not a device address: {address:#x}')
        hart = self.harts[hart_id]
        if self.device_dispatch is None:
            self._record_halt(hart_id, 'bus', hart.pc)
            return None
        result = self.device_dispatch(hart_id, address, is_write, w32(value))
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


def decode_instruction(word):
    """Return the shared mnemonic and fields, or None for an illegal word."""
    mnemonic = decode_mnemonic(word)
    if mnemonic is None:
        return None
    return mnemonic, fields(word)