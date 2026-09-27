"""Shared RV32I encoding constants and pure instruction bit operations."""

PRIMARY_OPCODES = {
    'OP_LUI': 0b0110111,
    'OP_AUIPC': 0b0010111,
    'OP_JAL': 0b1101111,
    'OP_JALR': 0b1100111,
    'OP_BRANCH': 0b1100011,
    'OP_LOAD': 0b0000011,
    'OP_STORE': 0b0100011,
    'OP_OPIMM': 0b0010011,
    'OP_OP': 0b0110011,
    'OP_MISC': 0b0001111,
    'OP_SYSTEM': 0b1110011,
}

F7_NORM = 0b0000000
F7_ALT = 0b0100000
F7_SELECTORS = {'F7_NORM': F7_NORM, 'F7_ALT': F7_ALT}
CSR_NAMES = {'mhartid': 0xF14}

# Bounds are inclusive; B/J bounds also require an even displacement.
IMM_RANGES = {
    'I': (-2048, 2047),
    'S': (-2048, 2047),
    'B': (-4096, 4094),
    'U': (-(1 << 19), (1 << 20) - 1),
    'J': (-(1 << 20), (1 << 20) - 2),
    'SHAMT': (0, 31),
    'CSR': (0, 0xFFF),
    'ZIMM': (0, 31),
    'FENCE': (0, 0xF),
}

# mnemonic -> (format, opcode, funct3, funct7-or-None); names are lowercase.
ENC = {
    'add':    ('R', PRIMARY_OPCODES['OP_OP'], 0b000, F7_NORM),
    'sub':    ('R', PRIMARY_OPCODES['OP_OP'], 0b000, F7_ALT),
    'sll':    ('R', PRIMARY_OPCODES['OP_OP'], 0b001, F7_NORM),
    'slt':    ('R', PRIMARY_OPCODES['OP_OP'], 0b010, F7_NORM),
    'sltu':   ('R', PRIMARY_OPCODES['OP_OP'], 0b011, F7_NORM),
    'xor':    ('R', PRIMARY_OPCODES['OP_OP'], 0b100, F7_NORM),
    'srl':    ('R', PRIMARY_OPCODES['OP_OP'], 0b101, F7_NORM),
    'sra':    ('R', PRIMARY_OPCODES['OP_OP'], 0b101, F7_ALT),
    'or':     ('R', PRIMARY_OPCODES['OP_OP'], 0b110, F7_NORM),
    'and':    ('R', PRIMARY_OPCODES['OP_OP'], 0b111, F7_NORM),
    'addi':   ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b000, None),
    'slli':   ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b001, F7_NORM),
    'slti':   ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b010, None),
    'sltiu':  ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b011, None),
    'xori':   ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b100, None),
    'srli':   ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b101, F7_NORM),
    'srai':   ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b101, F7_ALT),
    'ori':    ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b110, None),
    'andi':   ('I', PRIMARY_OPCODES['OP_OPIMM'], 0b111, None),
    'beq':    ('B', PRIMARY_OPCODES['OP_BRANCH'], 0b000, None),
    'bne':    ('B', PRIMARY_OPCODES['OP_BRANCH'], 0b001, None),
    'blt':    ('B', PRIMARY_OPCODES['OP_BRANCH'], 0b100, None),
    'bge':    ('B', PRIMARY_OPCODES['OP_BRANCH'], 0b101, None),
    'bltu':   ('B', PRIMARY_OPCODES['OP_BRANCH'], 0b110, None),
    'bgeu':   ('B', PRIMARY_OPCODES['OP_BRANCH'], 0b111, None),
    'lb':     ('I', PRIMARY_OPCODES['OP_LOAD'], 0b000, None),
    'lh':     ('I', PRIMARY_OPCODES['OP_LOAD'], 0b001, None),
    'lw':     ('I', PRIMARY_OPCODES['OP_LOAD'], 0b010, None),
    'lbu':    ('I', PRIMARY_OPCODES['OP_LOAD'], 0b100, None),
    'lhu':    ('I', PRIMARY_OPCODES['OP_LOAD'], 0b101, None),
    'sb':     ('S', PRIMARY_OPCODES['OP_STORE'], 0b000, None),
    'sh':     ('S', PRIMARY_OPCODES['OP_STORE'], 0b001, None),
    'sw':     ('S', PRIMARY_OPCODES['OP_STORE'], 0b010, None),
    'jalr':   ('I', PRIMARY_OPCODES['OP_JALR'], 0b000, None),
    'jal':    ('J', PRIMARY_OPCODES['OP_JAL'], None, None),
    'lui':    ('U', PRIMARY_OPCODES['OP_LUI'], None, None),
    'auipc':  ('U', PRIMARY_OPCODES['OP_AUIPC'], None, None),
    'ecall':  ('SYS0', PRIMARY_OPCODES['OP_SYSTEM'], 0b000, None),
    'ebreak': ('SYS0', PRIMARY_OPCODES['OP_SYSTEM'], 0b000, None),
    'fence':  ('FENCE', PRIMARY_OPCODES['OP_MISC'], 0b000, None),
    'csrrw':  ('Z', PRIMARY_OPCODES['OP_SYSTEM'], 0b001, None),
    'csrrs':  ('Z', PRIMARY_OPCODES['OP_SYSTEM'], 0b010, None),
    'csrrc':  ('Z', PRIMARY_OPCODES['OP_SYSTEM'], 0b011, None),
    'csrrwi': ('Z', PRIMARY_OPCODES['OP_SYSTEM'], 0b101, None),
    'csrrsi': ('Z', PRIMARY_OPCODES['OP_SYSTEM'], 0b110, None),
    'csrrci': ('Z', PRIMARY_OPCODES['OP_SYSTEM'], 0b111, None),
}

# SYS0 instructions share the ordinary SYSTEM/funct3 decode key and are
# distinguished by inst[31:20], so they are the only exempt table collision.
DECODE_COLLISION_EXEMPT = frozenset({frozenset({'ecall', 'ebreak'})})
SYS0_IMMEDIATES = {0: 'ecall', 1: 'ebreak'}


def _encode(opcode, rd=0, funct3=0, rs1=0, rs2=0, funct7=0):
    return ((funct7 << 25) | (rs2 << 20) | (rs1 << 15) |
            (funct3 << 12) | (rd << 7) | opcode)


def _check_range(name, value):
    lower, upper = IMM_RANGES[name]
    if not isinstance(value, int) or not lower <= value <= upper:
        label = {
            'I': 'I-type immediate',
            'S': 'store offset',
            'B': 'branch offset',
            'U': 'U-type immediate',
            'J': 'jump offset',
            'SHAMT': 'Shift amount',
            'CSR': 'CSR address',
            'ZIMM': 'CSR immediate',
            'FENCE': 'fence field',
        }[name]
        raise ValueError(f'{label} out of range: {value}')
    return value


def _check_field(name, value, bits):
    if not isinstance(value, int) or not 0 <= value < (1 << bits):
        raise ValueError(f'{name} value out of range: {value}')
    return value


def pack_r(rd, rs1, rs2, f3, f7, opcode=PRIMARY_OPCODES['OP_OP']):
    _check_field('opcode', opcode, 7)
    _check_field('rd', rd, 5)
    _check_field('rs1', rs1, 5)
    _check_field('rs2', rs2, 5)
    _check_field('funct3', f3, 3)
    _check_field('funct7', f7, 7)
    return _encode(opcode, rd, f3, rs1, rs2, f7)


def pack_i(rd, rs1, f3, imm12, opcode=PRIMARY_OPCODES['OP_OPIMM']):
    _check_field('opcode', opcode, 7)
    _check_field('rd', rd, 5)
    _check_field('rs1', rs1, 5)
    _check_field('funct3', f3, 3)
    _check_range('I', imm12)
    return ((imm12 & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | opcode


def pack_shift_i(rd, rs1, shamt, f3, f7,
                 opcode=PRIMARY_OPCODES['OP_OPIMM']):
    _check_field('opcode', opcode, 7)
    _check_field('rd', rd, 5)
    _check_field('rs1', rs1, 5)
    _check_field('funct3', f3, 3)
    _check_range('SHAMT', shamt)
    if (f3, f7) not in ((0b001, F7_NORM), (0b101, F7_NORM), (0b101, F7_ALT)):
        raise ValueError('illegal RV32I shift funct fields')
    return _encode(opcode, rd=rd, funct3=f3, rs1=rs1,
                   rs2=shamt, funct7=f7)


def pack_s(rs1, rs2, f3, off, opcode=PRIMARY_OPCODES['OP_STORE']):
    _check_field('opcode', opcode, 7)
    _check_field('rs1', rs1, 5)
    _check_field('rs2', rs2, 5)
    _check_field('funct3', f3, 3)
    _check_range('S', off)
    immediate = off & 0xFFF
    return (((immediate >> 5) << 25) | (rs2 << 20) | (rs1 << 15) |
            (f3 << 12) | ((immediate & 0x1F) << 7) | opcode)


def pack_b(rs1, rs2, f3, off,
           opcode=PRIMARY_OPCODES['OP_BRANCH']):
    _check_field('opcode', opcode, 7)
    _check_field('rs1', rs1, 5)
    _check_field('rs2', rs2, 5)
    _check_field('funct3', f3, 3)
    _check_range('B', off)
    if off & 1:
        raise ValueError(f'odd branch offset: {off}')
    immediate = off & 0x1FFF
    return (((immediate >> 12) & 1) << 31) | (((immediate >> 5) & 0x3F) << 25) \
        | (rs2 << 20) | (rs1 << 15) | (f3 << 12) \
        | (((immediate >> 1) & 0xF) << 8) | (((immediate >> 11) & 1) << 7) | opcode


def pack_u(rd, imm20, opcode=PRIMARY_OPCODES['OP_LUI']):
    _check_field('opcode', opcode, 7)
    _check_field('rd', rd, 5)
    _check_range('U', imm20)
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | opcode


def pack_j(rd, off, opcode=PRIMARY_OPCODES['OP_JAL']):
    _check_field('opcode', opcode, 7)
    _check_field('rd', rd, 5)
    _check_range('J', off)
    if off & 1:
        raise ValueError(f'odd jump offset: {off}')
    immediate = off & 0x1FFFFF
    return (((immediate >> 20) & 1) << 31) | (((immediate >> 1) & 0x3FF) << 21) \
        | (((immediate >> 11) & 1) << 20) | (((immediate >> 12) & 0xFF) << 12) \
        | (rd << 7) | opcode


def pack_z(rd, csr, f3, rs1_or_zimm,
           opcode=PRIMARY_OPCODES['OP_SYSTEM']):
    _check_field('opcode', opcode, 7)
    _check_field('rd', rd, 5)
    _check_range('CSR', csr)
    _check_field('funct3', f3, 3)
    _check_range('ZIMM', rs1_or_zimm)
    return (csr << 20) | (rs1_or_zimm << 15) | (f3 << 12) | (rd << 7) | opcode


def pack_fence(fm, pred, succ,
               opcode=PRIMARY_OPCODES['OP_MISC']):
    _check_field('opcode', opcode, 7)
    _check_range('FENCE', fm)
    _check_range('FENCE', pred)
    _check_range('FENCE', succ)
    return (fm << 28) | (pred << 24) | (succ << 20) | opcode


def fields(word):
    """Return fixed fields and raw immediate slices from a 32-bit word."""
    _check_field('instruction', word, 32)
    return {
        'opcode': word & 0x7F,
        'rd': (word >> 7) & 0x1F,
        'funct3': (word >> 12) & 0x7,
        'rs1': (word >> 15) & 0x1F,
        'rs2': (word >> 20) & 0x1F,
        'funct7': (word >> 25) & 0x7F,
        'imm12': (word >> 20) & 0xFFF,
        'imm20': (word >> 12) & 0xFFFFF,
        's_imm11_5': (word >> 25) & 0x7F,
        's_imm4_0': (word >> 7) & 0x1F,
        'b_imm12': (word >> 31) & 1,
        'b_imm10_5': (word >> 25) & 0x3F,
        'b_imm4_1': (word >> 8) & 0xF,
        'b_imm11': (word >> 7) & 1,
        'j_imm20': (word >> 31) & 1,
        'j_imm10_1': (word >> 21) & 0x3FF,
        'j_imm11': (word >> 20) & 1,
        'j_imm19_12': (word >> 12) & 0xFF,
    }


def _sign_extend(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def unpack_b(word):
    bit_fields = fields(word)
    immediate = ((bit_fields['b_imm12'] << 12) |
                 (bit_fields['b_imm11'] << 11) |
                 (bit_fields['b_imm10_5'] << 5) |
                 (bit_fields['b_imm4_1'] << 1))
    return _sign_extend(immediate, 13)


def unpack_j(word):
    bit_fields = fields(word)
    immediate = ((bit_fields['j_imm20'] << 20) |
                 (bit_fields['j_imm19_12'] << 12) |
                 (bit_fields['j_imm11'] << 11) |
                 (bit_fields['j_imm10_1'] << 1))
    return _sign_extend(immediate, 21)


def _table_key(row):
    _fmt, opcode, funct3, funct7 = row
    return opcode, funct3, funct7


def _collision_groups():
    groups = {}
    for mnemonic, row in ENC.items():
        groups.setdefault(_table_key(row), set()).add(mnemonic)
    return {key: frozenset(names) for key, names in groups.items() if len(names) > 1}


def validate_decode_uniqueness():
    collisions = frozenset(_collision_groups().values())
    if collisions != DECODE_COLLISION_EXEMPT:
        raise AssertionError(f'unexpected ENC decode collisions: {collisions}')
    return True


DECODE = {
    _table_key(row): mnemonic
    for mnemonic, row in ENC.items()
    if row[0] != 'SYS0'
}


def decode_mnemonic(word):
    bit_fields = fields(word)
    opcode = bit_fields['opcode']
    funct3 = bit_fields['funct3']
    if opcode == PRIMARY_OPCODES['OP_SYSTEM'] and funct3 == 0:
        return SYS0_IMMEDIATES.get(bit_fields['imm12'])

    funct7 = bit_fields['funct7']
    # RV32I OP-IMM shifts require exactly 0000000 (SLLI/SRLI) or
    # 0100000 (SRAI) in inst[31:25]; other patterns are illegal.
    exact = DECODE.get((opcode, funct3, funct7))
    if exact is not None:
        return exact
    generic = DECODE.get((opcode, funct3, None))
    if generic is not None:
        return generic
    return DECODE.get((opcode, None, None))