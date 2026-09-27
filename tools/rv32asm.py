# tools/rv32asm.py
# python3 tools/rv32asm.py prog.s -o prog.hex [--lst prog.lst (stub)]

from pathlib import Path
from dataclasses import dataclass

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
    upper_word = encode_u_type(upper, rd, opcode=0b0010111)
    lower_word = encode_i_type(rd, lower, 0b000, rd, opcode=0b0010011)
    return upper_word.to_bytes(4, 'little') + lower_word.to_bytes(4, 'little')

def instruction_handler(mnemonic: str, operands: list, symbol_table: dict, pc=0):
    # Handle instruction encoding based on mnemonic and operands
    # This is a placeholder for actual instruction encoding logic
    load_funct3 = {"LB": 0b000, "LH": 0b001, "LW": 0b010,
                   "LBU": 0b100, "LHU": 0b101}
    store_funct3 = {"SB": 0b000, "SH": 0b001, "SW": 0b010}
    branch_funct3 = {"BEQ": 0b000, "BNE": 0b001, "BLT": 0b100,
                     "BGE": 0b101, "BLTU": 0b110, "BGEU": 0b111}
    if mnemonic in branch_funct3:
        if len(operands) != 3:
            raise ValueError(f"{mnemonic.lower()} expects rs1, rs2, target")
        offset = resolve_pc_relative(operands[2], pc, symbol_table)
        return encode_b_type(operands[0], operands[1], offset,
                             branch_funct3[mnemonic], opcode=0b1100011)
    elif mnemonic == "JAL":
        if len(operands) != 2:
            raise ValueError("jal expects rd, target")
        offset = resolve_pc_relative(operands[1], pc, symbol_table)
        return encode_j_type(operands[0], offset, opcode=0b1101111)
    elif mnemonic == "JALR":
        if len(operands) == 2:
            offset, rs1 = parse_memory_operand(operands[1])
        elif len(operands) == 3:
            rs1, offset = operands[1], operands[2]
        else:
            raise ValueError("jalr expects rd, offset(rs1) or rd, rs1, offset")
        return encode_i_type(rs1, offset, 0b000, operands[0], opcode=0b1100111)
    elif mnemonic in load_funct3:
        if len(operands) != 2:
            raise ValueError(f"{mnemonic.lower()} expects rd, offset(rs1)")
        rd = operands[0]
        offset, rs1 = parse_memory_operand(operands[1])
        return encode_memory_i_type(rs1, offset, load_funct3[mnemonic], rd, opcode=0b0000011)
    elif mnemonic in store_funct3:
        if len(operands) != 2:
            raise ValueError(f"{mnemonic.lower()} expects rs2, offset(rs1)")
        rs2 = operands[0]
        offset, rs1 = parse_memory_operand(operands[1])
        return encode_s_type(rs2, rs1, offset, store_funct3[mnemonic], opcode=0b0100011)
    elif mnemonic == "ADD":
        # Example: add rd, rs1, rs2
        rd, rs1, rs2 = operands
        # Encode the instruction into machine code
        funct_7 = 0b0000000
        funct_3 = 0b000
        return encode_r_type(funct_7, rs2, rs1, funct_3, rd, opcode=0b0110011)
    elif mnemonic == "SUB":
        # Example: sub rd, rs1, rs2
        rd, rs1, rs2 = operands
        # Encode the instruction into machine code
        funct_7 = 0b0100000
        funct_3 = 0b000
        return encode_r_type(funct_7, rs2, rs1, funct_3, rd, opcode=0b0110011)
    elif mnemonic == "LUI":
        if len(operands) != 2:
            raise ValueError("lui expects rd, immediate")
        return encode_u_type(operands[1], operands[0], opcode=0b0110111)
    elif mnemonic == "AUIPC":
        if len(operands) != 2:
            raise ValueError("auipc expects rd, immediate")
        return encode_u_type(operands[1], operands[0], opcode=0b0010111)
    elif mnemonic in ('ECALL', 'EBREAK'):
        if operands:
            raise ValueError(f"{mnemonic.lower()} takes no operands")
        return 0x00000073 if mnemonic == 'ECALL' else 0x00100073
    elif mnemonic == 'FENCE':
        if not operands:
            predecessor = successor = 0b0011
            fm = 0
        elif len(operands) in (2, 3):
            predecessor = parse_fence_mask(operands[0])
            successor = parse_fence_mask(operands[1])
            fm = parse_integer(operands[2]) if len(operands) == 3 else 0
            if not 0 <= fm <= 0xF:
                raise ValueError(f"fence fm out of range: {fm}")
        else:
            raise ValueError("fence expects no operands or predecessor, successor[, fm]")
        return (fm << 28) | (predecessor << 24) | (successor << 20) | 0x0F
    elif mnemonic in ('CSRRW', 'CSRRS', 'CSRRC', 'CSRRWI', 'CSRRSI', 'CSRRCI'):
        if len(operands) != 3:
            raise ValueError(f"{mnemonic.lower()} expects rd, csr, rs1/zimm")
        csr = parse_csr(operands[1])
        if not 0 <= csr <= 0xFFF:
            raise ValueError(f"CSR address out of range: {operands[1]}")
        funct3 = {'CSRRW': 0b001, 'CSRRS': 0b010, 'CSRRC': 0b011,
                  'CSRRWI': 0b101, 'CSRRSI': 0b110, 'CSRRCI': 0b111}[mnemonic]
        if mnemonic.endswith('I'):
            zimm = parse_integer(operands[2])
            if not 0 <= zimm <= 31:
                raise ValueError(f"CSR immediate out of range: {operands[2]}")
            rs1 = zimm
        else:
            rs1 = parse_register(operands[2])
        rd = parse_register(operands[0])
        return (csr << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | 0b1110011
    elif mnemonic == "SLL":
        # Encode the instruction into machine code
        return encode_r_type(funct_7=0b0000000, rs2=operands[2], rs1=operands[1], funct_3=0b001, rd=operands[0], opcode=0b0110011)
    elif mnemonic == "SLT":
        # Encode the instruction into machine code
        return encode_r_type(funct_7=0b0000000, rs2=operands[2], rs1=operands[1], funct_3=0b010, rd=operands[0], opcode=0b0110011)
    elif mnemonic == "SLTU":
        # Encode the instruction into machine code
        return encode_r_type(funct_7=0b0000000, rs2=operands[2], rs1=operands[1], funct_3=0b011, rd=operands[0], opcode=0b0110011)
    elif mnemonic == "XOR":
        # Encode the instruction into machine code
        return encode_r_type(funct_7=0b0000000, rs2=operands[2], rs1=operands[1], funct_3=0b100, rd=operands[0], opcode=0b0110011)
    elif mnemonic == "SRL":
        # Encode the instruction into machine code
        return encode_r_type(funct_7=0b0000000, rs2=operands[2], rs1=operands[1], funct_3=0b101, rd=operands[0], opcode=0b0110011)
    elif mnemonic == "SRA":
        # Encode the instruction into machine code
        return encode_r_type(funct_7=0b0100000, rs2=operands[2], rs1=operands[1], funct_3=0b101, rd=operands[0], opcode=0b0110011)
    elif mnemonic == "OR":
        # Encode the instruction into machine code
        return encode_r_type(funct_7=0b0000000, rs2=operands[2], rs1=operands[1], funct_3=0b110, rd=operands[0], opcode=0b0110011)
    elif mnemonic == "AND":
        # Encode the instruction into machine code
        return encode_r_type(funct_7=0b0000000, rs2=operands[2], rs1=operands[1], funct_3=0b111, rd=operands[0], opcode=0b0110011)
    elif mnemonic == "ADDI":
        # Example: addi rd, rs1, imm
        rd, rs1, imm = operands
        # Encode the instruction into machine code
        funct_3 = 0b000
        return encode_i_type(rs1, imm, funct_3, rd, opcode=0b0010011)
    elif mnemonic == "SLTI":
        # Example: slti rd, rs1, imm
        rd, rs1, imm = operands
        # Encode the instruction into machine code
        funct_3 = 0b010
        return encode_i_type(rs1, imm, funct_3, rd, opcode=0b0010011)
    elif mnemonic == "SLTIU":
        # Example: sltiu rd, rs1, imm
        rd, rs1, imm = operands
        # Encode the instruction into machine code
        funct_3 = 0b011
        return encode_i_type(rs1, imm, funct_3, rd, opcode=0b0010011)
    elif mnemonic == "XORI":
        # Example: xori rd, rs1, imm
        rd, rs1, imm = operands
        # Encode the instruction into machine code
        funct_3 = 0b100
        return encode_i_type(rs1, imm, funct_3, rd, opcode=0b0010011)
    elif mnemonic == "ORI":
        # Example: ori rd, rs1, imm
        rd, rs1, imm = operands
        # Encode the instruction into machine code
        funct_3 = 0b110
        return encode_i_type(rs1, imm, funct_3, rd, opcode=0b0010011)
    elif mnemonic == "ANDI":
        # Example: andi rd, rs1, imm
        rd, rs1, imm = operands
        # Encode the instruction into machine code
        funct_3 = 0b111
        return encode_i_type(rs1, imm, funct_3, rd, opcode=0b0010011)
    elif mnemonic == "SLLI":
        # Example: slli rd, rs1, shamt
        rd, rs1, shamt = operands
        # Encode the instruction into machine code
        funct_3 = 0b001
        return encode_shift_i_type(rs1, shamt, funct_3, rd, opcode=0b0010011)
    elif mnemonic == "SRLI":
        # Example: srli rd, rs1, shamt
        rd, rs1, shamt = operands
        # Encode the instruction into machine code
        funct_3 = 0b101
        return encode_shift_i_type(rs1, shamt, funct_3, rd, opcode=0b0010011)
    elif mnemonic == "SRAI":
        # Example: srai rd, rs1, shamt
        rd, rs1, shamt = operands
        # Encode the instruction into machine code
        funct_3 = 0b101
        return encode_shift_i_type(rs1, shamt, funct_3, rd, opcode=0b0010011, funct_7=0b0100000)
    else:
        raise ValueError(f"Unknown instruction mnemonic: {mnemonic}")

def encode_r_type(funct_7, rs2, rs1, funct_3, rd, opcode):
    rs1_num = parse_register(rs1)
    rs2_num = parse_register(rs2)
    rd_num = parse_register(rd)
    instruction = (funct_7 << 25) | (rs2_num << 20) | (rs1_num << 15) | (funct_3 << 12) | (rd_num << 7) | opcode
    return instruction

def encode_i_type(rs1, imm, funct_3, rd, opcode):
    rs1_num = parse_register(rs1)
    rd_num = parse_register(rd)
    imm_num = parse_integer(imm)
    if not -2048 <= imm_num <= 2047:
        raise ValueError(f"I-type immediate out of range: {imm}")
    imm_num &= 0xFFF
    instruction = (imm_num << 20) | (rs1_num << 15) | (funct_3 << 12) | (rd_num << 7) | opcode
    return instruction


def encode_memory_i_type(rs1, offset, funct_3, rd, opcode):
    offset_num = parse_integer(offset)
    if not -2048 <= offset_num <= 2047:
        raise ValueError(f"memory offset out of range: {offset}")
    return encode_i_type(rs1, offset_num, funct_3, rd, opcode)


def encode_s_type(rs2, rs1, offset, funct_3, opcode):
    rs1_num = parse_register(rs1)
    rs2_num = parse_register(rs2)
    offset_num = parse_integer(offset)
    if not -2048 <= offset_num <= 2047:
        raise ValueError(f"store offset out of range: {offset}")
    immediate = offset_num & 0xFFF
    return (((immediate >> 5) << 25) | (rs2_num << 20) | (rs1_num << 15)
            | (funct_3 << 12) | ((immediate & 0x1F) << 7) | opcode)


def resolve_pc_relative(target, pc, symbol_table):
    if target in symbol_table:
        return symbol_table[target] - pc
    try:
        return parse_integer(target)
    except ValueError as error:
        raise ValueError(f"undefined symbol: {target}") from error


def encode_b_type(rs1, rs2, offset, funct_3, opcode):
    rs1_num = parse_register(rs1)
    rs2_num = parse_register(rs2)
    offset_num = parse_integer(offset)
    if offset_num & 1:
        raise ValueError(f"odd branch offset: {offset_num}")
    if not -4096 <= offset_num <= 4094:
        raise ValueError(f"branch offset out of range: {offset_num}")
    immediate = offset_num & 0x1FFF
    return (((immediate >> 12) & 1) << 31) | (((immediate >> 5) & 0x3F) << 25) \
        | (rs2_num << 20) | (rs1_num << 15) | (funct_3 << 12) \
        | (((immediate >> 1) & 0xF) << 8) | (((immediate >> 11) & 1) << 7) | opcode


def encode_j_type(rd, offset, opcode):
    rd_num = parse_register(rd)
    offset_num = parse_integer(offset)
    if offset_num & 1:
        raise ValueError(f"odd jump offset: {offset_num}")
    if not -(1 << 20) <= offset_num <= (1 << 20) - 2:
        raise ValueError(f"jump offset out of range: {offset_num}")
    immediate = offset_num & 0x1FFFFF
    return (((immediate >> 20) & 1) << 31) | (((immediate >> 1) & 0x3FF) << 21) \
        | (((immediate >> 11) & 1) << 20) | (((immediate >> 12) & 0xFF) << 12) \
        | (rd_num << 7) | opcode


def encode_u_type(immediate, rd, opcode):
    imm_num = parse_integer(immediate)
    if not -(1 << 19) <= imm_num < (1 << 20):
        raise ValueError(f"U-type immediate out of range: {immediate}")
    return ((imm_num & 0xFFFFF) << 12) | (parse_register(rd) << 7) | opcode


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

def encode_shift_i_type(rs1, shamt, funct_3, rd, opcode, funct_7=0):
    shamt_num = parse_integer(shamt)
    if not 0 <= shamt_num <= 31:
        raise ValueError(f"Shift amount out of range: {shamt}")
    return encode_i_type(rs1, (funct_7 << 5) | shamt_num, funct_3, rd, opcode)

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


CSR_NAMES = {'mhartid': 0xF14}


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