from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rv32asm import assemble, encode_la, layout_source


CHECKS = 0
FAILS = 0


def check(name, ok, detail=''):
    global CHECKS, FAILS
    CHECKS += 1
    if not ok:
        FAILS += 1
    print(('PASS: ' if ok else 'FAIL: ') + name + (f'  {detail}' if detail and not ok else ''))
    return ok


GOLDEN_VECTORS = (
    ('add x1, x2, x3', '003100b3'),
    ('nop', '00000013'),
    ('srai x4, x5, 31', '41f2d213'),
    ('srli x4, x5, 31', '01f2d213'),
    ('addi x6, x7, 0xF', '00f38313'),
    ('addi x6, x7, -1', 'fff38313'),
    ('slti x1, x2, 3', '00312093'),
    ('sltiu x1, x2, 3', '00313093'),
    ('xori x1, x2, 3', '00314093'),
    ('ori x1, x2, 3', '00316093'),
    ('andi x1, x2, 3', '00317093'),
    ('slli x1, x2, 3', '00311093'),
    ('AdD X8, x9, X10', '00a48433'),
    ('sll x1, x2, x3', '003110b3'),
    ('slt x1, x2, x3', '003120b3'),
    ('sltu x1, x2, x3', '003130b3'),
    ('xor x1, x2, x3', '003140b3'),
    ('srl x1, x2, x3', '003150b3'),
    ('sra x1, x2, x3', '403150b3'),
    ('or x1, x2, x3', '003160b3'),
    ('and x1, x2, x3', '003170b3'),
    ('add a0, x1, x2', '00208533'),
    ('lb x1, -4(x2)', 'ffc10083'),
    ('lh x1, -4(x2)', 'ffc11083'),
    ('lhu x1, 0(x2)', '00015083'),
    ('sb x2, 8(x1)', '00208423'),
    ('lw x1, -4(x2)', 'ffc12083'),
    ('sw x2, 8(x1)', '0020a423'),
    ('lbu x3, 0(x1)', '0000c183'),
    ('sh x4, -2048(x5)', '80429023'),
    ('lw x1, (x2)', '00012083'),
)

DATA_VECTORS = (
    ('.word 0x12345678', '12345678'),
    ('.byte 0o10', '00000008'),
)

DATA_PROGRAM_VECTORS = (
    (' .word data\ndata: nop', ('00000004', '00000013')),
)

PROGRAM_VECTORS = (
    ('beq x1, x2, fwd\nnop\nfwd: nop',
     ('00208463', '00000013', '00000013')),
    ('blt x1, x2, fwd\nnop\nfwd: nop',
     ('0020c463', '00000013', '00000013')),
    ('bge x1, x2, fwd\nnop\nfwd: nop',
     ('0020d463', '00000013', '00000013')),
    ('bgeu x1, x2, fwd\nnop\nfwd: nop',
     ('0020f463', '00000013', '00000013')),
    ('back: nop\nbne x1, x2, back',
     ('00000013', 'fe209ee3')),
    ('bltu x1, x2, edge\n.org 4094\nedge:',
     ('7e20efe3',)),
    ('jal x1, fwd16\nnop\nnop\nnop\nfwd16: nop',
     ('010000ef', '00000013', '00000013', '00000013', '00000013')),
    ('jal x1, 16', ('010000ef',)),
    ('back: nop\njal x0, back',
     ('00000013', 'ffdff06f')),
    ('jalr x0, 0(x1)', ('00008067',)),
    ('jalr x1, x2, 4', ('004100e7',)),
    ('lui x1, 0xFFFFF', ('fffff0b7',)),
    ('auipc x1, 0', ('00000097',)),
    ('auipc x1, 0x12345', ('12345097',)),
    ('csrrw x1, 0xF14, x0', ('f14010f3',)),
    ('csrrs x1, 0xF14, x0', ('f14020f3',)),
    ('csrrs x1, mhartid, x0', ('f14020f3',)),
    ('csrrc x1, 0xF14, x0', ('f14030f3',)),
    ('csrrwi x1, 0xF14, 3', ('f141d0f3',)),
    ('csrrsi x1, 0xF14, 3', ('f141e0f3',)),
    ('csrrci x1, 0xF14, 3', ('f141f0f3',)),
    ('ecall\nebreak\nfence', ('00000073', '00100073', '0330000f')),
    ('fence iorw, iorw', ('0ff0000f',)),
)

LI_VECTORS = (
    ('li x1, -1', ('fff00093',)),
    ('li x1, 2047', ('7ff00093',)),
    ('li x1, 2048', ('000010b7', '80008093')),
    ('li x1, 0x12345800', ('123460b7', '80008093')),
    ('ret', ('00008067',)),
    ('mv x1, x2', ('00010093',)),
    ('j target\ntarget: nop', ('0040006f', '00000013')),
    ('jr x1', ('00008067',)),
    ('beqz x1, target\ntarget: nop', ('00008263', '00000013')),
    ('bnez x1, target\ntarget: nop', ('00009263', '00000013')),
    ('neg x1, x2', ('402000b3',)),
    ('not x1, x2', ('fff14093',)),
    ('seqz x1, x2', ('00113093',)),
    ('snez x1, x2', ('002030b3',)),
    ('csrr x1, mhartid', ('f14020f3',)),
    ('csrw mhartid, x1', ('f1409073',)),
    ('la x1, target\n.org 0x800\ntarget:',
     ('00001097', '80008093')),
    ('la x1, target\n.org 0x7FF\ntarget:',
     ('00000097', '7ff08093')),
    ('nop\nnop\nla x1, back\nback: nop',
        ('00000013', '00000013', '00000097', '00808093', '00000013')),
)

INVALID_PROGRAMS = (
    ('beq x1, x2, target\n.byte 1\n.space 2\ntarget:', 'odd branch offset'),
    ('beq x1, x2, target\n.org 4096\ntarget:', 'branch offset out of range'),
    ('jal x1, far\n.org 1048576\nfar:', 'jump offset out of range'),
    ('jal x1, -1048578', 'jump offset out of range'),
    ('.space 1048577', 'image exceeds maximum size'),
    ('.org 0x40000000', 'image exceeds maximum size'),
    ('li x1, 0x1FFFFFFFF', 'li immediate out of 32-bit range'),
)

INVALID_SOURCES = (
    ('addi x1, x2, 5000', 'I-type immediate out of range'),
    ('srli x1, x2, 32', 'Shift amount out of range'),
    ('add x1, x32, x2', 'Register out of range'),
    ('lw x1, 4096(x2)', 'offset out of range'),
    ('lw x1, 4(x32)', 'Register out of range'),
    ('.byte 010', 'Invalid integer'),
)


def selftest():
    with tempfile.TemporaryDirectory() as directory:
        temp_dir = Path(directory)
        for index, (source_line, expected_word) in enumerate(GOLDEN_VECTORS):
            source = temp_dir / f'golden_{index}.s'
            output = temp_dir / f'golden_{index}.hex'
            source.write_text(source_line + '\n')
            try:
                assemble(source, output)
                emitted = output.read_text().strip()
                check(source_line, emitted == expected_word,
                      f'expected {expected_word}, got {emitted}')
            except Exception as error:
                check(source_line, False, f'unexpected {type(error).__name__}: {error}')

        for index, (source_line, expected_word) in enumerate(DATA_VECTORS):
            source = temp_dir / f'data_{index}.s'
            output = temp_dir / f'data_{index}.hex'
            source.write_text(source_line + '\n')
            try:
                assemble(source, output)
                emitted = output.read_text().strip()
                check(source_line, emitted == expected_word,
                      f'expected {expected_word}, got {emitted}')
            except Exception as error:
                check(source_line, False, f'unexpected {type(error).__name__}: {error}')

        for index, (source_text, expected_words) in enumerate(DATA_PROGRAM_VECTORS):
            source = temp_dir / f'data_program_{index}.s'
            output = temp_dir / f'data_program_{index}.hex'
            source.write_text(source_text + '\n')
            try:
                assemble(source, output)
                emitted = tuple(output.read_text().splitlines())
                check(source_text.splitlines()[0], emitted == expected_words,
                      f'expected {expected_words}, got {emitted}')
            except Exception as error:
                check(source_text.splitlines()[0], False,
                      f'unexpected {type(error).__name__}: {error}')

        for index, (source_text, expected_words) in enumerate(PROGRAM_VECTORS + LI_VECTORS):
            source = temp_dir / f'program_{index}.s'
            output = temp_dir / f'program_{index}.hex'
            source.write_text(source_text + '\n')
            try:
                assemble(source, output)
                emitted = tuple(output.read_text().splitlines())
                compare = emitted[:len(expected_words)] if source_text.startswith(('bltu ', 'la ')) else emitted
                check(source_text.splitlines()[0], compare == expected_words,
                      f'expected {expected_words}, got {compare}')
            except Exception as error:
                check(source_text.splitlines()[0], False,
                      f'unexpected {type(error).__name__}: {error}')

        for index, (source_line, expected_error) in enumerate(INVALID_SOURCES):
            source = temp_dir / f'invalid_{index}.s'
            output = temp_dir / f'invalid_{index}.hex'
            source.write_text(source_line + '\n')
            try:
                assemble(source, output)
            except ValueError as error:
                message = str(error)
                check(source_line, expected_error in message,
                      f'expected message containing {expected_error!r}, got {message!r}')
            except Exception as error:
                check(source_line, False,
                      f'expected ValueError, got {type(error).__name__}: {error}')
            else:
                check(source_line, False, 'invalid source was accepted')

        for index, (source_text, expected_error) in enumerate(INVALID_PROGRAMS):
            source = temp_dir / f'invalid_program_{index}.s'
            output = temp_dir / f'invalid_program_{index}.hex'
            source.write_text(source_text + '\n')
            try:
                assemble(source, output)
            except ValueError as error:
                message = str(error)
                check(source_text.splitlines()[0], expected_error in message, message)
            except Exception as error:
                check(source_text.splitlines()[0], False,
                      f'expected ValueError, got {type(error).__name__}: {error}')
            else:
                check(source_text.splitlines()[0], False, 'invalid source was accepted')

        source = temp_dir / 'invalid_li.s'
        output = temp_dir / 'invalid_li.hex'
        source.write_text('li x1, 0x1FFFFFFFF\n')
        try:
            assemble(source, output)
        except ValueError as error:
            message = str(error)
            check('LI range errors retain source location and diagnosis',
                  'line 1:' in message and 'li immediate out of 32-bit range' in message,
                  message)
        else:
            check('LI range errors retain source location and diagnosis', False,
                  'invalid LI was accepted')

        source = temp_dir / 'listing.s'
        output = temp_dir / 'listing.hex'
        source.write_text('nop\n')
        try:
            assemble(source, output, temp_dir / 'listing.lst')
        except ValueError as error:
            check('--lst is not silently ignored', 'not implemented' in str(error), str(error))
        else:
            check('--lst is not silently ignored', False, 'listing option was accepted')

        source = temp_dir / 'multiple_errors.s'
        output = temp_dir / 'multiple_errors.hex'
        source.write_text('lw x1, 4096(x2)\nadd x1, x32, x2\n')
        try:
            assemble(source, output)
        except ValueError as error:
            message = str(error)
            check('all errors carry source line numbers',
                  'line 1:' in message and 'line 2:' in message, message)
            check('assembly reports both invalid lines',
                  'offset out of range' in message and 'Register out of range' in message,
                  message)
        else:
            check('assembly reports all errors instead of aborting early', False,
                  'invalid source was accepted')

        layout_items, symbols, layout_errors, end_pc = layout_source(
            ['start: add x1, x2, x3', '.word 0x12345678', 'later: nop'])
        check('forward label gets byte address after data and instruction',
              symbols.get('later') == 8,
              f"expected later=8, got {symbols.get('later')}")
        check('layout pass sizes the complete source', end_pc == 12,
              f'expected end PC 12, got {end_pc}')
        check('same-line label retains its instruction item',
              any(item.kind == 'instruction' and item.line_num == 1 for item in layout_items),
              'instruction after start: was not included in layout')
        check('valid layout has no diagnostics', not layout_errors,
              '\n'.join(layout_errors))

        source = temp_dir / 'same_line_label.s'
        output = temp_dir / 'same_line_label.hex'
        source.write_text('loop: add x1, x2, x3\n')
        assemble(source, output)
        check('same-line label assembles its instruction',
              output.read_text().strip() == '003100b3', output.read_text().strip())

        source = temp_dir / 'backward_org.s'
        output = temp_dir / 'backward_org.hex'
        source.write_text('add x1, x2, x3\n.org 0\naddi x1, x0, 1\n')
        try:
            assemble(source, output)
        except ValueError as error:
            message = str(error)
            check('backward .org is rejected with its source line',
                  'line 2:' in message and '.org' in message, message)
            check('backward .org does not produce an artifact', not output.exists(),
                  'output file was written despite layout error')
        else:
            check('backward .org is rejected', False, 'assembly succeeded')

        la_trap = encode_la('x1', 'target', {'target': 0x12345800}, 0)
        la_words = tuple(f'{int.from_bytes(la_trap[index:index + 4], "little"):08x}'
                         for index in (0, 4))
        check('LA +0x800 upper-part correction',
              la_words == ('12346097', '80008093'),
              f'got {la_words}')

    print(f'\nSummary: {FAILS} failed out of {CHECKS} checks')
    return FAILS


if __name__ == '__main__':
    sys.exit(selftest())