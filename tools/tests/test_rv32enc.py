from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rv32asm import parse_csr, parse_integer, parse_memory_operand, parse_register
from tools.tests.test_rv32asm import GOLDEN_VECTORS
from tools.rv32iss import decode_instruction
from tools.rv32enc import (
    DECODE_COLLISION_EXEMPT, ENC, F7_ALT, F7_NORM, IMM_RANGES,
    PRIMARY_OPCODES, decode_mnemonic, fields, pack_b, pack_fence, pack_i,
    pack_j, pack_r, pack_s, pack_shift_i, pack_u, pack_z,
    unpack_b, unpack_j, validate_decode_uniqueness,
)


CHECKS = 0
FAILS = 0


def check(name, passed, detail=''):
    global CHECKS, FAILS
    CHECKS += 1
    FAILS += not passed
    print(('PASS: ' if passed else 'FAIL: ') + name +
          (f'  {detail}' if detail and not passed else ''))


def signed(value, bits):
    return (value ^ (1 << (bits - 1))) - (1 << (bits - 1))


def instruction_source(source):
    parts = source.split(None, 1)
    return parts[0].lower(), [part.strip() for part in parts[1].split(',')] if len(parts) > 1 else []


def selftest():
    formats = {'R', 'I', 'S', 'B', 'U', 'J', 'Z', 'SYS0', 'FENCE'}
    check('ENC has 46 rows', len(ENC) == 46, f'got {len(ENC)}')
    check('ENC mnemonics are unique', len(ENC) == len(set(ENC)))
    check('ENC formats are known', all(row[0] in formats for row in ENC.values()))
    check('ENC opcode/funct fields fit', all(
        0 <= row[1] <= 0x7F and (row[2] is None or 0 <= row[2] <= 7) and
        (row[3] is None or 0 <= row[3] <= 0x7F) for row in ENC.values()))
    check('only documented decode collision exists', validate_decode_uniqueness() and
          DECODE_COLLISION_EXEMPT == frozenset({frozenset({'ecall', 'ebreak'})}))

    for mnemonic, (fmt, opcode, f3, f7) in ENC.items():
        if fmt == 'R':
            word = pack_r(1, 2, 3, f3, f7, opcode)
        elif fmt == 'I' and f7 is not None:
            word = pack_shift_i(1, 2, 3, f3, f7, opcode)
        elif fmt == 'I':
            word = pack_i(1, 2, f3, 3, opcode)
        elif fmt == 'S':
            word = pack_s(2, 3, f3, 4, opcode)
        elif fmt == 'B':
            word = pack_b(2, 3, f3, 4, opcode)
        elif fmt == 'U':
            word = pack_u(1, 3, opcode)
        elif fmt == 'J':
            word = pack_j(1, 4, opcode)
        elif fmt == 'Z':
            word = pack_z(1, 0xF14, f3, 2, opcode)
        elif fmt == 'SYS0':
            word = 0x00000073 if mnemonic == 'ecall' else 0x00100073
        else:
            word = pack_fence(0, 3, 3, opcode)
        check(f'decode table row {mnemonic}', decode_mnemonic(word) == mnemonic)
        check(f'ISS shared decode row {mnemonic}',
              decode_instruction(word)[0] == mnemonic)

    b_anchor = pack_b(1, 2, 0, 8)
    check('B +8 immediate contribution',
          b_anchor - pack_b(1, 2, 0, 0) == 0x00000400,
          f'word={b_anchor:08x}')
    check('B -4 literal anchor', pack_b(1, 2, 1, -4) == 0xFE209EE3)
    j_anchor = pack_j(1, 16)
    check('J +16 immediate contribution',
          j_anchor - pack_j(1, 0) == 0x01000000,
          f'word={j_anchor:08x}')
    check('J -4 literal anchor', pack_j(0, -4) == 0xFFDFF06F)
    check('I +15 literal anchor', pack_i(6, 7, 0, 15) == 0x00F38313)

    r_word = pack_r(7, 11, 19, 5, F7_ALT)
    r_fields = fields(r_word)
    check('R fields round trip', (r_fields['rd'], r_fields['rs1'], r_fields['rs2'],
          r_fields['funct3'], r_fields['funct7']) == (7, 11, 19, 5, F7_ALT) and
          pack_r(r_fields['rd'], r_fields['rs1'], r_fields['rs2'],
                 r_fields['funct3'], r_fields['funct7']) == r_word)

    for value in (0, 2, -2, 2047, 2046, -2048, -2047, 0x555):
        if -2048 <= value <= 2047:
            word = pack_i(9, 17, 3, value)
            actual = signed(fields(word)['imm12'], 12)
            check(f'I immediate round trip {value}', actual == value and
                  pack_i(9, 17, 3, actual) == word)

    for value in (0, 2, -2, 2047, 2046, -2048, -2047, 0x555):
        if -2048 <= value <= 2047:
            word = pack_s(17, 9, 2, value)
            raw = (fields(word)['s_imm11_5'] << 5) | fields(word)['s_imm4_0']
            actual = signed(raw, 12)
            check(f'S immediate round trip {value}', actual == value and
                  pack_s(17, 9, 2, actual) == word)

    for value in (0, 2, -2, 4094, -4096, 0x554, 4092, -4094):
        word = pack_b(17, 9, 5, value)
        check(f'B displacement round trip {value}', unpack_b(word) == value and
              pack_b(17, 9, 5, unpack_b(word)) == word)

    for value in (0, 2, -2, (1 << 19) - 1, (1 << 19) - 2,
                  -(1 << 19), -(1 << 19) + 1, 0x55555):
        if IMM_RANGES['U'][0] <= value <= IMM_RANGES['U'][1]:
            word = pack_u(9, value)
            actual = signed(fields(word)['imm20'], 20)
            check(f'U immediate round trip {value}', actual == value and
                  pack_u(9, actual) == word)

    for value in (0, 2, -2, (1 << 20) - 2, -(1 << 20), 0x55554,
                  (1 << 20) - 4, -(1 << 20) + 2):
        word = pack_j(9, value)
        check(f'J displacement round trip {value}', unpack_j(word) == value and
              pack_j(9, unpack_j(word)) == word)

    for csr, source in ((0, 0), (0xF14, 31), (0x555, 0x15), (0xFFF, 1)):
        word = pack_z(9, csr, 6, source)
        decoded = fields(word)
        check(f'Z fields round trip {csr:#x}',
              (decoded['rd'], decoded['imm12'], decoded['funct3'], decoded['rs1']) ==
              (9, csr, 6, source) and pack_z(9, csr, 6, source) == word)

    for fm, pred, succ in ((0, 0, 0), (0, 3, 3), (15, 5, 10), (1, 15, 1)):
        word = pack_fence(fm, pred, succ)
        check(f'FENCE fields round trip {fm}:{pred}:{succ}',
              ((word >> 28) & 0xF, (word >> 24) & 0xF, (word >> 20) & 0xF) ==
              (fm, pred, succ) and pack_fence(fm, pred, succ) == word)

    for source, expected_hex in GOLDEN_VECTORS:
        mnemonic, operands = instruction_source(source)
        expected_mnemonic = 'addi' if mnemonic == 'nop' else mnemonic
        expected_operands = ['x0', 'x0', '0'] if mnemonic == 'nop' else operands
        word = int(expected_hex, 16)
        bit_fields = fields(word)
        decoded = decode_mnemonic(word)
        check(f'golden mnemonic {mnemonic}', decoded == expected_mnemonic,
              f'decoded {decoded!r} from {word:08x}')
        mnemonic = expected_mnemonic
        operands = expected_operands
        if decoded is None or mnemonic not in ENC:
            continue
        fmt, opcode, f3, f7 = ENC[mnemonic]
        rd, rs1, rs2 = bit_fields['rd'], bit_fields['rs1'], bit_fields['rs2']
        if fmt == 'R':
            recovered = (rd, rs1, rs2)
            expected = tuple(parse_register(value) for value in operands)
            rebuilt = pack_r(rd, rs1, rs2, f3, f7, opcode)
        elif fmt == 'I' and opcode == PRIMARY_OPCODES['OP_LOAD']:
            immediate = signed(bit_fields['imm12'], 12)
            source_offset, source_rs1 = parse_memory_operand(operands[1])
            recovered, expected = (rd, rs1, immediate), (
                parse_register(operands[0]), parse_register(source_rs1), source_offset)
            rebuilt = pack_i(rd, rs1, f3, immediate, opcode)
        elif fmt == 'I' and f7 is not None:
            recovered, expected = (rd, rs1, rs2), (
                parse_register(operands[0]), parse_register(operands[1]),
                parse_integer(operands[2]))
            rebuilt = pack_shift_i(rd, rs1, rs2, f3, f7, opcode)
        elif fmt == 'I':
            immediate = signed(bit_fields['imm12'], 12)
            recovered, expected = (rd, rs1, immediate), (
                parse_register(operands[0]), parse_register(operands[1]),
                parse_integer(operands[2]) if mnemonic != 'jalr' or len(operands) == 3 else
                parse_memory_operand(operands[1])[0])
            if mnemonic == 'jalr' and len(operands) == 2:
                expected = (parse_register(operands[0]),
                            parse_register(parse_memory_operand(operands[1])[1]),
                            parse_memory_operand(operands[1])[0])
                recovered = (rd, rs1, immediate)
            rebuilt = pack_i(rd, rs1, f3, immediate, opcode)
        elif fmt == 'S':
            immediate = signed((bit_fields['s_imm11_5'] << 5) |
                               bit_fields['s_imm4_0'], 12)
            source_offset, source_rs1 = parse_memory_operand(operands[1])
            recovered, expected = (rs1, rs2, immediate), (
                parse_register(source_rs1), parse_register(operands[0]), source_offset)
            rebuilt = pack_s(rs1, rs2, f3, immediate, opcode)
        elif fmt == 'U':
            immediate = bit_fields['imm20']
            recovered, expected = (rd, immediate), (
                parse_register(operands[0]), parse_integer(operands[1]) & 0xFFFFF)
            rebuilt = pack_u(rd, immediate, opcode)
        elif fmt == 'J':
            immediate = unpack_j(word)
            recovered, expected = (rd, immediate), (
                parse_register(operands[0]), parse_integer(operands[1]))
            rebuilt = pack_j(rd, immediate, opcode)
        elif fmt == 'Z':
            csr = bit_fields['imm12']
            recovered = (rd, csr, bit_fields['rs1'])
            expected = (parse_register(operands[0]), parse_csr(operands[1]),
                        parse_integer(operands[2]) if mnemonic.endswith('i') else
                        parse_register(operands[2]))
            rebuilt = pack_z(rd, csr, f3, bit_fields['rs1'], opcode)
        elif fmt == 'SYS0':
            rebuilt = word
            recovered = expected = ()
        elif fmt == 'FENCE':
            fm, pred, succ = ((word >> 28) & 0xF, (word >> 24) & 0xF,
                              (word >> 20) & 0xF)
            rebuilt = pack_fence(fm, pred, succ, opcode)
            recovered = expected = (fm, pred, succ)
        else:
            continue
        check(f'golden operands {mnemonic}', recovered == expected,
              f'expected {expected}, recovered {recovered}')
        check(f'golden repack {mnemonic}', rebuilt == word,
              f'expected {word:08x}, got {rebuilt:08x}')

    bad_shift = (0b0000001 << 25) | (0b001 << 12) | PRIMARY_OPCODES['OP_OPIMM']
    check('illegal OP-IMM shift funct7 does not decode', decode_mnemonic(bad_shift) is None)
    check('shared CSR name is canonical', CSR_NAMES_CHECK(), 'mhartid mapping')

    print(f'\nSummary: {FAILS} failed out of {CHECKS} checks')
    return FAILS


def CSR_NAMES_CHECK():
    from tools.rv32enc import CSR_NAMES
    return CSR_NAMES == {'mhartid': 0xF14}


if __name__ == '__main__':
    sys.exit(selftest())