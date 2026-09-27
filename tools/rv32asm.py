# tools/rv32asm.py
# python3 tools/rv32asm.py prog.s -o prog.hex [--lst prog.lst (stub)]

from pathlib import Path
from dataclasses import dataclass

if __package__:
    from .rv32enc import (
        CSR_NAMES, ENC, PRIMARY_OPCODES, pack_b, pack_fence, pack_i, pack_j,
        pack_r, pack_s, pack_shift_i, pack_u, pack_z,
    )
else:
    from rv32enc import (
        CSR_NAMES, ENC, PRIMARY_OPCODES, pack_b, pack_fence, pack_i, pack_j,
        pack_r, pack_s, pack_shift_i, pack_u, pack_z,
    )

# Dialect choices: bare FENCE is rw,rw; JAL requires rd; three-operand JALR
# uses rd, rs1, offset; integer targets are relative offsets, symbols absolute.
# Literals use int(token, 0): decimal by default, with 0x/0b/0o prefixes.
# LA is AUIPC+ADDI for the symbol address relative to the LA instruction PC.
MAX_IMAGE_BYTES = 1 << 20

def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Assemble RISC-V assembly code into machine code.")
    parser.add_argument("input_file", type=Path, help="Input assembly file (.s)")
    parser.add_argument("-o", "--output_file", type=Path, required=True, help="Output hex file (.hex)")
    parser.add_argument("--lst", type=Path, help="Optional listing file (.lst)")

    args = parser.parse_args()

    try:
        assemble(args.input_file, args.output_file, args.lst)
    except AssemblyError as error:
        print(f"assembly failed:\n{error}", file=sys.stderr)
        return 1
    return 0


class AssemblyError(ValueError):
    pass


@dataclass
class AssemblyItem:
    kind: str
    line_num: int
    address: int
    name: str
    operands: list
    size: int


def assemble(input_file: Path, output_file: Path, lst_file: Path = None):
    if lst_file is not None:
        raise AssemblyError("--lst is not implemented")
    lines = Path(input_file).read_text().splitlines()
    items, symbol_table, errors, end_pc = layout_source(lines)
    if errors:
        raise AssemblyError('\n'.join(errors))
    image = bytearray(end_pc)

    for item in items:
        if item.kind in ('label', 'org'):
            continue
        try:
            if item.kind == 'directive':
                data = directive_handler(item.name, item.operands, symbol_table)
                if len(data) != item.size:
                    raise ValueError(f"{item.name} emitted {len(data)} bytes, expected {item.size}")
            elif item.name == 'LA':
                data = encode_la(item.operands[0], item.operands[1],
                                 symbol_table, item.address)
            else:
                word = instruction_handler(item.name, item.operands, symbol_table,
                                           item.address)
                data = word.to_bytes(4, 'little')
            image[item.address:item.address + len(data)] = data
        except (ValueError, IndexError, OverflowError) as error:
            errors.append(f"line {item.line_num}: {error}")

    if errors:
        raise AssemblyError('\n'.join(errors))

    if len(image) % 4:
        image.extend(bytes(4 - len(image) % 4))
    with open(output_file, 'w') as output:
        for offset in range(0, len(image), 4):
            word = int.from_bytes(image[offset:offset + 4], 'little')
            output.write(f"{word:08x}\n")


def layout_source(lines):
    items = []
    symbol_table = {}
    errors = []
    pc = 0

    for line_num, raw_line in expand_pseudoinstructions(lines, errors):
        line = normalize_line(raw_line)
        if not line:
            continue

        if ':' in line:
            label, _, remainder = line.partition(':')
            if not label.strip():
                errors.append(f"line {line_num}: empty label")
                line = remainder.strip()
            elif not any(character.isspace() for character in label):
                label = label.strip()
                if label in symbol_table:
                    errors.append(f"line {line_num}: duplicate label: {label}")
                else:
                    symbol_table[label] = pc
                items.append(AssemblyItem('label', line_num, pc, label, [], 0))
                line = remainder.strip()
                if not line:
                    continue

        if line.startswith('.'):
            directive_parts = line[1:].strip().split(None, 1)
            name = directive_parts[0].lower() if directive_parts else ''
            argument_text = directive_parts[1] if len(directive_parts) == 2 else ''
            operands = split_operands(argument_text)
            if name == 'org':
                items.append(AssemblyItem('org', line_num, pc, name, operands, 0))
                try:
                    if len(operands) != 1:
                        raise ValueError(".org expects one address")
                    origin = parse_integer(operands[0])
                    if origin < 0:
                        raise ValueError(f"invalid .org address: {origin}")
                    if origin > MAX_IMAGE_BYTES:
                        raise ValueError(f"image exceeds maximum size of {MAX_IMAGE_BYTES} bytes")
                    if origin < pc:
                        raise ValueError(
                            f".org cannot move backward from {pc} to {origin}")
                    pc = origin
                except ValueError as error:
                    errors.append(f"line {line_num}: {error}")
                continue

            size = directive_reservation(name, operands)
            items.append(AssemblyItem('directive', line_num, pc, name, operands, size))
            pc += size
            if pc > MAX_IMAGE_BYTES:
                errors.append(
                    f"line {line_num}: image exceeds maximum size of {MAX_IMAGE_BYTES} bytes")
            continue

        parts = line.split(None, 1)
        mnemonic = parts[0].upper()
        operands = split_operands(parts[1] if len(parts) == 2 else '')
        size = 8 if mnemonic == 'LA' else 4
        items.append(AssemblyItem('instruction', line_num, pc, mnemonic, operands, size))
        pc += size
        if pc > MAX_IMAGE_BYTES:
            errors.append(
                f"line {line_num}: image exceeds maximum size of {MAX_IMAGE_BYTES} bytes")

    return items, symbol_table, errors, pc


def expand_pseudoinstructions(lines, errors=None):
    if errors is None:
        errors = []
    expanded = []
    for line_num, raw_line in enumerate(lines, start=1):
        line = normalize_line(raw_line)
        if not line:
            expanded.append((line_num, raw_line))
            continue
        label_prefix = ''
        if ':' in line:
            label, _, remainder = line.partition(':')
            if label.strip() and not any(character.isspace() for character in label):
                label_prefix = label.strip() + ': '
                line = remainder.strip()
        if not line:
            expanded.append((line_num, label_prefix.rstrip()))
            continue

        parts = line.split(None, 1)
        mnemonic = parts[0].upper()
        operands = split_operands(parts[1] if len(parts) == 2 else '')
        replacements = None
        if mnemonic == 'NOP' and not operands:
            replacements = ['addi x0, x0, 0']
        elif mnemonic == 'RET' and not operands:
            replacements = ['jalr x0, 0(x1)']
        elif mnemonic == 'MV' and len(operands) == 2:
            replacements = [f"addi {operands[0]}, {operands[1]}, 0"]
        elif mnemonic == 'J' and len(operands) == 1:
            replacements = [f"jal x0, {operands[0]}"]
        elif mnemonic == 'JR' and len(operands) == 1:
            replacements = [f"jalr x0, 0({operands[0]})"]
        elif mnemonic in ('BEQZ', 'BNEZ') and len(operands) == 2:
            base = 'beq' if mnemonic == 'BEQZ' else 'bne'
            replacements = [f"{base} {operands[0]}, x0, {operands[1]}"]
        elif mnemonic == 'NEG' and len(operands) == 2:
            replacements = [f"sub {operands[0]}, x0, {operands[1]}"]
        elif mnemonic == 'NOT' and len(operands) == 2:
            replacements = [f"xori {operands[0]}, {operands[1]}, -1"]
        elif mnemonic == 'SEQZ' and len(operands) == 2:
            replacements = [f"sltiu {operands[0]}, {operands[1]}, 1"]
        elif mnemonic == 'SNEZ' and len(operands) == 2:
            replacements = [f"sltu {operands[0]}, x0, {operands[1]}"]
        elif mnemonic == 'CSRR' and len(operands) == 2:
            replacements = [f"csrrs {operands[0]}, {operands[1]}, x0"]
        elif mnemonic == 'CSRW' and len(operands) == 2:
            replacements = [f"csrrw x0, {operands[0]}, {operands[1]}"]
        elif mnemonic == 'LA' and len(operands) == 2:
            expanded.append((line_num, label_prefix + f"la {operands[0]}, {operands[1]}"))
            continue
        elif mnemonic == 'LI' and len(operands) == 2:
            try:
                value = parse_integer(operands[1])
                if 0 <= value <= 0xFFFFFFFF and value > 0x7FFFFFFF:
                    value -= 1 << 32
                if not -(1 << 31) <= value <= 0x7FFFFFFF:
                    raise ValueError(f"li immediate out of 32-bit range: {operands[1]}")
                if -2048 <= value <= 2047:
                    replacements = [f"addi {operands[0]}, x0, {value}"]
                else:
                    upper = (value + 0x800) >> 12
                    lower = value - (upper << 12)
                    replacements = [f"lui {operands[0]}, {upper}",
                                    f"addi {operands[0]}, {operands[0]}, {lower}"]
            except ValueError as error:
                errors.append(f"line {line_num}: {error}")
                continue

        if replacements is None:
            expanded.append((line_num, label_prefix + line))
        else:
            for index, replacement in enumerate(replacements):
                prefix = label_prefix if index == 0 else ''
                expanded.append((line_num, prefix + replacement))
    return expanded


def directive_handler(directive: str, operands: list, symbol_table=None):
    if symbol_table is None:
        symbol_table = {}
    if directive == "text":
        if operands:
            raise ValueError(".text takes no arguments")
        return b''
    elif directive == "word":
        return encode_data_values(operands, 4, symbol_table)
    elif directive == "byte":
        return encode_data_values(operands, 1)
    elif directive == "half":
        return encode_data_values(operands, 2)
    elif directive == "space":
        if len(operands) != 1:
            raise ValueError(".space expects one size")
        size = parse_integer(operands[0])
        if size < 0:
            raise ValueError(f"invalid .space size: {size}")
        return bytes(size)
    else:
        raise ValueError(f"Unknown directive: {directive}")


def encode_data_values(operands, width, symbol_table=None):
    if symbol_table is None:
        symbol_table = {}
    if not operands:
        raise ValueError("data directive expects at least one value")
    encoded = bytearray()
    bits = width * 8
    for operand in operands:
        if width == 4 and operand in symbol_table:
            value = symbol_table[operand]
        else:
            value = parse_integer(operand)
        if not -(1 << (bits - 1)) <= value < (1 << bits):
            raise ValueError(f"data value out of range for {bits} bits: {operand}")
        encoded.extend((value & ((1 << bits) - 1)).to_bytes(width, 'little'))
    return bytes(encoded)


def directive_reservation(directive, operands):
    width = {'byte': 1, 'half': 2, 'word': 4}.get(directive)
    if width is not None:
        return width * len(operands)
    if directive == 'space' and len(operands) == 1:
        try:
            return max(0, parse_integer(operands[0]))
        except ValueError:
            return 0
    return 0


def split_operands(text):
    return [operand.strip() for operand in text.split(',') if operand.strip()]


def encode_la(rd, symbol, symbol_table, pc):
    if symbol not in symbol_table:
        raise ValueError(f"undefined symbol: {symbol}")
    address = symbol_table[symbol]
    relative = address - pc
    if not -(1 << 31) <= relative < (1 << 31):
        raise ValueError(f"la displacement out of 32-bit range: {relative}")
    upper = (relative + 0x800) >> 12
    lower = relative - (upper << 12)
    upper_word = pack_u(parse_register(rd), upper, PRIMARY_OPCODES['OP_AUIPC'])
    lower_word = pack_i(parse_register(rd), parse_register(rd), 0b000, lower,
                        PRIMARY_OPCODES['OP_OPIMM'])
    return upper_word.to_bytes(4, 'little') + lower_word.to_bytes(4, 'little')

def instruction_handler(mnemonic: str, operands: list, symbol_table: dict, pc=0):
    mnemonic = mnemonic.lower()
    try:
        fmt, opcode, f3, f7 = ENC[mnemonic]
    except KeyError as error:
        raise ValueError(f"Unknown instruction mnemonic: {mnemonic.upper()}") from error

    if fmt == 'R':
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} expects rd, rs1, rs2")
        rd, rs1, rs2 = (parse_register(value) for value in operands)
        return pack_r(rd, rs1, rs2, f3, f7, opcode)

    if fmt == 'I':
        if opcode == PRIMARY_OPCODES['OP_LOAD']:
            if len(operands) != 2:
                raise ValueError(f"{mnemonic} expects rd, offset(rs1)")
            offset_text, rs1_text = parse_memory_operand(operands[1])
            rd, rs1 = parse_register(operands[0]), parse_register(rs1_text)
            immediate = parse_integer(offset_text)
            try:
                return pack_i(rd, rs1, f3, immediate, opcode)
            except ValueError as error:
                if 'I-type immediate out of range' in str(error):
                    raise ValueError(f"memory offset out of range: {offset_text}") from error
                raise
        if opcode == PRIMARY_OPCODES['OP_JALR']:
            if len(operands) == 2:
                offset, rs1_text = parse_memory_operand(operands[1])
            elif len(operands) == 3:
                rs1_text, offset = operands[1], operands[2]
            else:
                raise ValueError("jalr expects rd, offset(rs1) or rd, rs1, offset")
            return pack_i(parse_register(operands[0]), parse_register(rs1_text), f3,
                          parse_integer(offset), opcode)
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} expects rd, rs1, immediate")
        rd, rs1 = parse_register(operands[0]), parse_register(operands[1])
        if f7 is not None:
            return pack_shift_i(rd, rs1, parse_integer(operands[2]), f3, f7, opcode)
        return pack_i(rd, rs1, f3, parse_integer(operands[2]), opcode)

    if fmt == 'S':
        if len(operands) != 2:
            raise ValueError(f"{mnemonic} expects rs2, offset(rs1)")
        offset_text, rs1_text = parse_memory_operand(operands[1])
        return pack_s(parse_register(rs1_text), parse_register(operands[0]), f3,
                      parse_integer(offset_text), opcode)

    if fmt == 'B':
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} expects rs1, rs2, target")
        offset = resolve_pc_relative(operands[2], pc, symbol_table)
        return pack_b(parse_register(operands[0]), parse_register(operands[1]),
                      f3, offset, opcode)

    if fmt == 'U':
        if len(operands) != 2:
            raise ValueError(f"{mnemonic} expects rd, immediate")
        return pack_u(parse_register(operands[0]), parse_integer(operands[1]), opcode)

    if fmt == 'J':
        if len(operands) != 2:
            raise ValueError("jal expects rd, target")
        offset = resolve_pc_relative(operands[1], pc, symbol_table)
        return pack_j(parse_register(operands[0]), offset, opcode)

    if fmt == 'SYS0':
        if operands:
            raise ValueError(f"{mnemonic} takes no operands")
        return 0x00000073 if mnemonic == 'ecall' else 0x00100073

    if fmt == 'FENCE':
        if not operands:
            predecessor = successor = 0b0011
            fm = 0
        elif len(operands) in (2, 3):
            predecessor = parse_fence_mask(operands[0])
            successor = parse_fence_mask(operands[1])
            fm = parse_integer(operands[2]) if len(operands) == 3 else 0
        else:
            raise ValueError("fence expects no operands or predecessor, successor[, fm]")
        try:
            return pack_fence(fm, predecessor, successor, opcode)
        except ValueError as error:
            if 'fence field out of range' in str(error):
                raise ValueError(f"fence fm out of range: {fm}") from error
            raise

    if fmt == 'Z':
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} expects rd, csr, rs1/zimm")
        csr = parse_csr(operands[1])
        source = parse_integer(operands[2]) if mnemonic.endswith('i') else parse_register(operands[2])
        try:
            return pack_z(parse_register(operands[0]), csr, f3, source, opcode)
        except ValueError as error:
            if 'CSR address out of range' in str(error):
                raise ValueError(f"CSR address out of range: {operands[1]}") from error
            if 'CSR immediate out of range' in str(error):
                raise ValueError(f"CSR immediate out of range: {operands[2]}") from error
            raise

    raise AssertionError(f"unsupported ENC format: {fmt}")


def resolve_pc_relative(target, pc, symbol_table):
    if target in symbol_table:
        return symbol_table[target] - pc
    try:
        return parse_integer(target)
    except ValueError as error:
        raise ValueError(f"undefined symbol: {target}") from error


def parse_fence_mask(mask):
    mask = mask.strip().lower()
    if mask == '0':
        return 0
    bits = {'i': 0b1000, 'o': 0b0100, 'r': 0b0010, 'w': 0b0001}
    result = 0
    for letter in mask:
        if letter not in bits:
            raise ValueError(f"invalid fence mask: {mask}")
        result |= bits[letter]
    return result


def parse_memory_operand(operand):
    opening = operand.find('(')
    closing = operand.find(')', opening + 1)
    if opening < 0 or closing != len(operand) - 1 or ')' in operand[closing + 1:]:
        raise ValueError(f"expected offset(rs1) operand: {operand}")
    offset_text = operand[:opening].strip()
    register = operand[opening + 1:closing].strip()
    if not register:
        raise ValueError(f"missing base register in memory operand: {operand}")
    return (parse_integer(offset_text) if offset_text else 0), register

def parse_integer(token):
    if isinstance(token, int):
        return token
    try:
        return int(token.strip(), 0)
    except ValueError as error:
        raise ValueError(f"Invalid integer: {token}") from error

def parse_register(register):
    token = register.strip()
    if token.upper().startswith('X'):
        try:
            number = int(token[1:], 10)
        except ValueError as error:
            raise ValueError(f"Invalid register name: {register}") from error
    elif token.lower() in ABI_REGISTERS:
        number = ABI_REGISTERS[token.lower()]
    else:
        try:
            number = int(token, 10)
        except ValueError as error:
            raise ValueError(f"Invalid register: {register}") from error
    if not 0 <= number <= 31:
        raise ValueError(f"Register out of range: {register}")
    return number


ABI_REGISTERS = {
    'zero': 0, 'ra': 1, 'sp': 2, 'gp': 3, 'tp': 4,
    't0': 5, 't1': 6, 't2': 7, 's0': 8, 'fp': 8, 's1': 9,
    'a0': 10, 'a1': 11, 'a2': 12, 'a3': 13,
    'a4': 14, 'a5': 15, 'a6': 16, 'a7': 17,
    's2': 18, 's3': 19, 's4': 20, 's5': 21, 's6': 22,
    's7': 23, 's8': 24, 's9': 25, 's10': 26, 's11': 27,
    't3': 28, 't4': 29, 't5': 30, 't6': 31,
}


def parse_csr(csr):
    token = csr.strip().lower()
    if token in CSR_NAMES:
        return CSR_NAMES[token]
    return parse_integer(csr)

def normalize_line(line: str) -> str:
    line = line.split('#')[0]  # Remove comments
    return line.strip()

if __name__ == "__main__":
    import sys
    sys.exit(main())