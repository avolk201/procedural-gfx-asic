from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rv32enc import ENC, pack_i, pack_r, pack_s, pack_shift_i
from tools.rv32iss import (
    DEVICE_BASE, HALT_REASONS, RAM_BYTES, Hart, Machine, decode_instruction,
)


CHECKS = 0
FAILS = 0


def check(name, passed):
    global CHECKS, FAILS
    CHECKS += 1
    FAILS += not passed
    print(('PASS: ' if passed else 'FAIL: ') + name)


OP_EXPECTED = {
    'add': 0xFFFFFFFF,
    'sub': 0xFFFFFFFD,
    'sll': 0xFFFFFFFC,
    'slt': 1,
    'sltu': 0,
    'xor': 0xFFFFFFFF,
    'srl': 0x7FFFFFFF,
    'sra': 0xFFFFFFFF,
    'or': 0xFFFFFFFF,
    'and': 0,
}

OPIMM_EXPECTED = {
    'addi': 0xFFFFFFFF,
    'slli': 0xFFFFFFFC,
    'slti': 1,
    'sltiu': 0,
    'xori': 0xFFFFFFFF,
    'srli': 0x7FFFFFFF,
    'srai': 0xFFFFFFFF,
    'ori': 0xFFFFFFFF,
    'andi': 0,
}

JUMP_VECTORS = (
    ('jal_x1_p4', 0x004000EF, 0x00001000, {1: 0xFFFFFFFF}, 0x00001004, 1,
     0x00001004),
    ('jal_x0_p8', 0x0080006F, 0x00001000, {}, 0x00001008, 0, 0x00000000),
    ('jal_x1_m4', 0xFFDFF0EF, 0x00001000, {}, 0x00000FFC, 1, 0x00001004),
    ('jal_x1_0', 0x000000EF, 0x00001000, {}, 0x00001000, 1, 0x00001004),
    ('jal_x1_max_p', 0x7FFFF0EF, 0x00000000, {}, 0x000FFFFE, 1, 0x00000004),
    ('jal_x1_min_m', 0x800000EF, 0x00001000, {}, 0xFFF01000, 1, 0x00001004),
    ('jal_x1_wrap_fwd', 0x008000EF, 0x00007FFC, {}, 0x00008004, 1,
     0x00008000),
    ('jal_x1_wrap_bwd', 0xFFDFF0EF, 0x00000000, {}, 0xFFFFFFFC, 1,
     0x00000004),
    ('jal_x31_p4', 0x00400FEF, 0x00001000, {31: 0xDEADBEEF}, 0x00001004, 31,
     0x00001004),
    ('jalr_x1_x2_0', 0x000100E7, 0x00001000, {2: 0x00002000}, 0x00002000, 1,
     0x00001004),
    ('jalr_ret', 0x00008067, 0x00001000, {1: 0x00002004}, 0x00002004, 0,
     0x00000000),
    ('jalr_jr_x2', 0x00010067, 0x00001000, {2: 0x00003000}, 0x00003000, 0,
     0x00000000),
    ('jalr_x1_x2_p8', 0x008100E7, 0x00001000, {2: 0x00002000}, 0x00002008, 1,
     0x00001004),
    ('jalr_x1_x2_m4', 0xFFC100E7, 0x00001000, {2: 0x00002000}, 0x00001FFC, 1,
     0x00001004),
    ('jalr_x1_x2_max_imm', 0x7FF100E7, 0x00001000, {2: 0x00001801},
     0x00002000, 1, 0x00001004),
    ('jalr_x1_x2_min_imm', 0x800100E7, 0x00001000, {2: 0x00002800},
     0x00002000, 1, 0x00001004),
    ('jalr_x1_x2_odd_imm_clear', 0x001100E7, 0x00001000, {2: 0x00002000},
     0x00002000, 1, 0x00001004),
    ('jalr_x2_x2_p4', 0x00410167, 0x00001000, {2: 0x00002000}, 0x00002004, 2,
     0x00001004),
    ('jalr_x1_x0_p8', 0x008000E7, 0x00001000, {}, 0x00000008, 1, 0x00001004),
    ('jalr_x1_x2_wrap_carry', 0x001100E7, 0x00001000, {2: 0xFFFFFFFF},
     0x00000000, 1, 0x00001004),
    ('jalr_x1_x2_wrap_borrow', 0xFF8100E7, 0x00001000, {2: 0x00000004},
     0xFFFFFFFC, 1, 0x00001004),
    ('jalr_x0_x2_p4', 0x00410067, 0x00001000, {2: 0x00002000}, 0x00002004, 0,
     0x00000000),
)

BRANCH_VECTORS = (
    ('beq_taken_x1eqx1_p8', 0x00108463, {1: 0xFFFFFFFF}, 0x00001008),
    ('beq_nt_p1_m8', 0xFE208CE3, {1: 0xFFFFFFFF, 2: 1}, 0x00001004),
    ('bne_taken_p1_m4', 0xFE209EE3, {1: 0xFFFFFFFF, 2: 1}, 0x00000FFC),
    ('bne_nt_x1eqx1_p8', 0x00109463, {1: 1}, 0x00001004),
    ('blt_taken_p1_m4', 0xFE20CEE3, {1: 0xFFFFFFFF, 2: 1}, 0x00000FFC),
    ('blt_nt_p2_p8', 0x0020C463, {1: 1, 2: 0xFFFFFFFF}, 0x00001004),
    ('bge_taken_p2_p8', 0x0020D463, {1: 1, 2: 0xFFFFFFFF}, 0x00001008),
    ('bge_nt_p1_m8', 0xFE20DCE3, {1: 0xFFFFFFFF, 2: 1}, 0x00001004),
    ('bltu_taken_p2_p8', 0x0020E463, {1: 1, 2: 0xFFFFFFFF}, 0x00001008),
    ('bltu_nt_p1_m4', 0xFE20EEE3, {1: 0xFFFFFFFF, 2: 1}, 0x00001004),
    ('bgeu_taken_p1_m4', 0xFE20FEE3, {1: 0xFFFFFFFF, 2: 1}, 0x00000FFC),
    ('bgeu_nt_p2_m8', 0xFE20FCE3, {1: 1, 2: 0xFFFFFFFF}, 0x00001004),
    ('beq_taken_x0eqx0_p8', 0x00000463, {}, 0x00001008),
)

U_VECTORS = (
    ('lui_x5_p12345', 0x123452B7, 0x00001000, 5, 0x12345000),
    ('lui_x0_dead0', 0xDEAD0037, 0x00001000, 0, 0x00000000),
    ('auipc_x5_p12345', 0x12345297, 0x00001000, 5, 0x12346000),
    ('auipc_x5_m1', 0xFFFFF297, 0x00001000, 5, 0x00000000),
    ('auipc_x6_maxneg', 0x80000317, 0x00000000, 6, 0x80000000),
)


def encode(mnemonic):
    fmt, opcode, funct3, funct7 = ENC[mnemonic]
    if fmt == 'R':
        return pack_r(3, 1, 2, funct3, funct7, opcode)
    if funct7 is not None:
        return pack_shift_i(3, 1, 1, funct3, funct7, opcode)
    return pack_i(3, 1, funct3, 1, opcode)


def run_instruction(mnemonic):
    machine = Machine()
    hart = machine.harts[0]
    hart.reg_write(1, 0xFFFFFFFE)
    hart.reg_write(2, 1)
    word = encode(mnemonic)
    hart.mem[0:4] = word.to_bytes(4, 'little')
    retired = machine.step(0)
    return machine, hart, word, retired


def run_word(word, initial):
    machine = Machine(hart_count=1)
    hart = machine.harts[0]
    for register, value in initial.items():
        hart.reg_write(register, value)
    hart.mem[:4] = word.to_bytes(4, 'little')
    return machine, hart, machine.step(0)


def run_vector(word, pc, initial):
    machine = Machine(hart_count=1)
    hart = machine.harts[0]
    for register, value in initial.items():
        hart.reg_write(register, value)
    hart.pc = pc
    hart.mem[pc:pc + 4] = word.to_bytes(4, 'little')
    return machine, hart, machine.step(0)


def retire_row(pc, word, rd, value):
    return f'0,{pc:08x},{word:08x},{rd},{value:08x},,,,'


def scheduled_machine(schedule, seed=None):
    instructions_per_hart = 5
    total_instructions = 2 * instructions_per_hart
    machine = Machine(max_steps=4 * total_instructions + 64)
    for hart_id, hart in enumerate(machine.harts):
        words = (
            pack_i(1, 0, 0, hart_id + 3),
            pack_i(2, 1, 0, -1),
            pack_i(3, 2, 0b100, 0x55),
            pack_i(4, 3, 0b001, 3),
            0x00100073,
        )
        hart.mem[:4 * len(words)] = b''.join(
            word.to_bytes(4, 'little') for word in words
        )
        hart.mem[0x6000:0x6004] = (0xA0 + hart_id).to_bytes(4, 'little')
    machine.run(schedule, seed=seed)
    state = tuple((tuple(hart.x), bytes(hart.mem), hart.halted)
                  for hart in machine.harts)
    return machine, state


def loop_machine():
    image = b''.join(
        word.to_bytes(4, 'little') for word in (
            0x00400093, 0x00110113, 0xFFF08093, 0xFE009CE3, 0x00100073))
    machine = Machine(max_steps=4 * 26 + 64)
    for hart in machine.harts:
        hart.mem[:len(image)] = image
    return machine


def selftest():
    check('memory size is 32 KiB', RAM_BYTES == 0x8000)
    check('two harts have private RAM', Hart(0).mem is not Hart(1).mem)
    check('halt vocabulary is defined', HALT_REASONS ==
          (None, 'ebreak', 'ecall', 'illegal', 'budget', 'bus'))

    for mnemonic, expected in {**OP_EXPECTED, **OPIMM_EXPECTED}.items():
        machine, hart, word, retired = run_instruction(mnemonic)
        check(f'{mnemonic} result and retirement', retired and
              hart.reg_read(3) == expected and hart.pc == 4 and
              machine.trace == [f'0,00000000,{word:08x},3,{expected:08x},,,,'])

    machine, hart, retired = run_word(0xFFF0F193, {1: 0xFFFFFFFE})
    check('andi sign-extends negative immediate', retired and
          hart.reg_read(3) == 0xFFFFFFFE and machine.trace ==
          ['0,00000000,fff0f193,3,fffffffe,,,,'])

    machine, hart, retired = run_word(0xFFF0B193, {1: 0xFFFFFFFE})
    check('sltiu compares against sign-extended immediate as unsigned', retired and
          hart.reg_read(3) == 1 and machine.trace ==
          ['0,00000000,fff0b193,3,00000001,,,,'])

    machine, hart, retired = run_word(0x004091B3, {1: 1, 4: 33})
    check('register shift masks high shift-amount bits', retired and
          hart.reg_read(3) == 2 and machine.trace ==
          ['0,00000000,004091b3,3,00000002,,,,'])

    check('SLLI with nonzero imm[11:5] is illegal',
          decode_instruction(0x02109193) is None)
    machine, hart, retired = run_word(0x02109193, {})
    check('illegal SLLI records halt row', not retired and
          hart.halted == 'illegal' and machine.trace ==
          ['0,00000000,02109193,,,halt:illegal,,,'])

    machine, hart, retired = run_word(0x00700013, {})
    check('rd=x0 write is ignored and traced as zero', retired and
            hart.reg_read(0) == 0 and hart.x[0] == 0 and machine.trace ==
          ['0,00000000,00700013,0,00000000,,,,'])

    machine, hart, retired = run_word(0x002081B3, {1: 0xFFFFFFFF, 2: 1})
    check('ADD wraps to exactly zero', retired and hart.reg_read(3) == 0 and
          machine.trace == ['0,00000000,002081b3,3,00000000,,,,'])

    load_cases = (
        ('lb', 0, 1, 0xFFFFFF80, 0x00000080),
        ('lbu', 4, 1, 0x00000080, 0x00000080),
        ('lh', 1, 2, 0xFFFFFF80, 0x0000FF80),
        ('lhu', 5, 2, 0x0000FF80, 0x0000FF80),
        ('lw', 2, 4, 0x1234FF80, 0x1234FF80),
    )
    machine = Machine(hart_count=1)
    hart = machine.harts[0]
    hart.reg_write(1, 0x6000)
    hart.mem[0x6000:0x6004] = bytes.fromhex('80ff3412')
    load_words = [
        pack_i(3, 1, funct3, 0, 0x03)
        for _, funct3, _, _, _ in load_cases
    ]
    hart.mem[:4 * len(load_words)] = b''.join(
        word.to_bytes(4, 'little') for word in load_words
    )
    for index, (mnemonic, _, size, expected, raw) in enumerate(load_cases):
        word = load_words[index]
        retired = machine.step(0)
        expected_row = (
            f'0,{4 * index:08x},{word:08x},3,{expected:08x},'
            f'{mnemonic},00006000,{size},{raw:08x}'
        )
        check(f'{mnemonic} sign extension and memory trace',
              retired and hart.reg_read(3) == expected and
              machine.trace[-1] == expected_row)

    machine = Machine(hart_count=1)
    hart = machine.harts[0]
    hart.reg_write(1, 0x6000)
    hart.mem[0x6000:0x6004] = bytes.fromhex('80ff3412')
    word = pack_i(3, 1, 4, 1, 0x03)
    hart.mem[:4] = word.to_bytes(4, 'little')
    retired = machine.step(0)
    check('RAM byte load selects addressed lane',
          retired and hart.reg_read(3) == 0xFF and machine.trace == [
              f'0,00000000,{word:08x},3,000000ff,lbu,00006001,1,000000ff'
          ])

    device_reads = []

    def read_device(hart_id, address, is_write, value, size):
        device_reads.append((hart_id, address, is_write, value, size))
        return 0x12345678

    machine = Machine(hart_count=1, device_dispatch=read_device)
    hart = machine.harts[0]
    hart.reg_write(1, DEVICE_BASE + 1)
    word = pack_i(0, 1, 0, 0, 0x03)
    hart.mem[:4] = word.to_bytes(4, 'little')
    retired = machine.step(0)
    check('lb to x0 still performs device read side effect',
          retired and hart.reg_read(0) == 0 and
          device_reads == [(0, DEVICE_BASE + 1, False, 0, 1)] and
          machine.trace == [
              f'0,00000000,{word:08x},0,00000000,lb,40000001,1,00000056'
          ])

    machine = Machine(hart_count=1, device_dispatch=read_device)
    hart = machine.harts[0]
    hart.reg_write(1, DEVICE_BASE)
    word = pack_i(0, 1, 1, 1, 0x03)
    hart.mem[:4] = word.to_bytes(4, 'little')
    reads_before = len(device_reads)
    retired = machine.step(0)
    check('misaligned lh to x0 traps before device access',
          not retired and hart.halted == 'illegal' and
          len(device_reads) == reads_before and machine.trace == [
              f'0,00000000,{word:08x},,,halt:illegal,,,'
          ])

    store_cases = (
        ('sb', 0, 1, 1, 0x0000DD00, b'\xdd'),
        ('sh', 1, 2, 2, 0xCCDD0000, b'\xdd\xcc'),
        ('sw', 2, 4, 0, 0xAABBCCDD, b'\xdd\xcc\xbb\xaa'),
    )
    for mnemonic, funct3, size, offset, lanes, stored_bytes in store_cases:
        machine = Machine(hart_count=1)
        hart = machine.harts[0]
        hart.reg_write(1, 0x6000)
        hart.reg_write(2, 0xAABBCCDD)
        word = pack_s(1, 2, funct3, offset, 0x23)
        hart.mem[:4] = word.to_bytes(4, 'little')
        retired = machine.step(0)
        address = 0x6000 + offset
        expected_row = (
            f'0,00000000,{word:08x},,,{mnemonic},{address:08x},'
            f'{size},{lanes:08x}'
        )
        check(f'{mnemonic} writes data lanes and memory trace',
              retired and hart.mem[address:address + size] == stored_bytes and
              machine.trace == [expected_row])

    machine = Machine(max_steps=4)
    for hart_id, hart in enumerate(machine.harts):
        word = pack_i(1, 0, 0, hart_id + 1)
        hart.mem[:8] = word.to_bytes(4, 'little') * 2
    machine.run([1, 0, 1, 0])
    check('scripted schedule controls retirement trace order',
            [line.split(',')[0] for line in machine.trace[:4]] ==
            ['1', '0', '1', '0'])
    check('global step budget halts all active harts',
          machine.steps == 4 and all(h.halted == 'budget' for h in machine.harts) and
          machine.trace[4:] == [
              '0,00000008,,,,halt:budget,,,',
              '1,00000008,,,,halt:budget,,,',
          ])

    machine = Machine(max_steps=2)
    for hart in machine.harts:
        hart.mem[:4] = pack_i(1, 0, 0, 1).to_bytes(4, 'little')
    machine.run()
    check('round-robin run interleaves harts',
            [line.split(',')[0] for line in machine.trace[:2]] == ['0', '1'])

    invariant_runs = [scheduled_machine('rr')]
    invariant_runs.extend(scheduled_machine('random', seed=seed)
                          for seed in range(8))
    scripted_schedule = [0] * 10 + [1] * 10
    invariant_runs.append(scheduled_machine(scripted_schedule))
    invariant_state = invariant_runs[0][1]
    check('final registers and private memories ignore schedule',
          all(state == invariant_state for _, state in invariant_runs) and
          all(halted == 'ebreak' for _, _, halted in invariant_state) and
          all(machine.steps == 8 for machine, _ in invariant_runs))
    repeated_random_run = scheduled_machine('random', seed=37)[0]
    check('same random seed reproduces trace order',
          repeated_random_run.trace == scheduled_machine('random', seed=37)[0].trace)

    for word, reason in ((0x00000073, 'ecall'), (0x00100073, 'ebreak'),
                         (0, 'illegal')):
        machine = Machine()
        machine.harts[0].mem[:4] = word.to_bytes(4, 'little')
        check(f'{reason} halt reason', not machine.step(0) and
              machine.harts[0].halted == reason and machine.trace == [
                f'0,00000000,{word:08x},,,halt:{reason},,,'])

    machine = Machine()
    machine.harts[0].pc = 2
    check('misaligned fetch halts illegal', not machine.step(0) and
            machine.harts[0].halted == 'illegal' and machine.trace ==
            ['0,00000002,,,,halt:illegal,,,'])
    machine = Machine()
    machine.harts[0].pc = RAM_BYTES
    check('out-of-range fetch halts bus', not machine.step(0) and
            machine.harts[0].halted == 'bus' and machine.trace ==
            ['0,00008000,,,,halt:bus,,,'])

    device_calls = []

    def device_dispatch(hart_id, address, is_write, value, size):
        device_calls.append((hart_id, address, is_write, value, size))
        return True if is_write else 0x12345678

    machine = Machine(device_dispatch=device_dispatch)
    read_value = machine.dispatch_device(1, DEVICE_BASE, value=0)
    write_result = machine.dispatch_device(0, DEVICE_BASE + 4, True, -1)
    check('device dispatch forwards and masks access values',
          read_value == 0x12345678 and write_result is True and
          device_calls == [(1, DEVICE_BASE, False, 0, 4),
                           (0, DEVICE_BASE + 4, True, 0xFFFFFFFF, 4)])
    device_calls.clear()
    read_value = machine.mem_read(0, DEVICE_BASE + 1, 1, 0x00000003)
    check('device byte load extracts addressed lane',
          read_value == 0x56 and
          device_calls == [(0, DEVICE_BASE + 1, False, 0, 1)])
    device_calls.clear()
    write_result = machine.mem_write(
        0, DEVICE_BASE + 2, 2, 0xBEEF, 0x12345678
    )
    check('device halfword store forwards raw value and access size',
          write_result and machine.harts[0].halted is None and
          device_calls == [(0, DEVICE_BASE + 2, True, 0xBEEF, 2)])
    device_calls.clear()
    write_result = machine.mem_write(
        0, DEVICE_BASE + 1, 1, 0xAABBCCDD, 0x12345678
    )
    check('device byte store right-justifies dirty rs2',
          write_result and machine.harts[0].halted is None and
          device_calls == [(0, DEVICE_BASE + 1, True, 0xDD, 1)])
    machine = Machine()
    check('unmapped device access halts bus',
          machine.dispatch_device(0, DEVICE_BASE) is None and
          machine.harts[0].halted == 'bus' and machine.trace ==
          ['0,00000000,,,,halt:bus,,,'])
    machine = Machine()
    check('unmapped device store halts bus once',
          not machine.mem_write(0, DEVICE_BASE, 4, 0x12345678, 0x00000023) and
          machine.harts[0].halted == 'bus' and machine.trace ==
            ['0,00000000,,,,halt:bus,,,'])

    for name, word, pc, initial, pc_after, rd, rd_value in JUMP_VECTORS:
        machine, hart, retired = run_vector(word, pc, initial)
        check(f'{name} retires and traces', retired and
              hart.pc == pc_after and hart.reg_read(rd) == rd_value and
              machine.trace == [retire_row(pc, word, rd, rd_value)])

    machine, hart, retired = run_vector(0x000100E7, 0x00001000,
                                        {2: 0x00002002})
    retired_ok = (retired and hart.pc == 0x00002002 and
                  hart.reg_read(1) == 0x00001004)
    second = machine.step(0) if retired_ok else False
    check('jalr lands 2 mod 4 then fetch halts illegal', retired_ok and
          not second and hart.halted == 'illegal' and
          machine.trace == [
              retire_row(0x00001000, 0x000100E7, 1, 0x00001004),
              '0,00002002,,,,halt:illegal,,,',
          ])

    for name, word, initial, pc_after in BRANCH_VECTORS:
        machine, hart, retired = run_vector(word, 0x00001000, initial)
        check(f'{name} retires with rd-zero row', retired and
              hart.pc == pc_after and
              machine.trace == [retire_row(0x00001000, word, 0, 0)])

    fence_calls = []

    def fence_device(hart_id, address, is_write, value, size):
        fence_calls.append((hart_id, address, is_write, value, size))
        return True

    machine = Machine(hart_count=1, device_dispatch=fence_device)
    hart = machine.harts[0]
    hart.pc = 0x00001000
    hart.mem[0x1000:0x1004] = (0x0330000F).to_bytes(4, 'little')
    hart.mem[0x1004:0x1008] = (0x00100073).to_bytes(4, 'little')
    mem_before = bytes(hart.mem)
    first = machine.step(0)
    check('fence rw,rw retires as NOP, memory and devices untouched', first and
          hart.pc == 0x00001004 and bytes(hart.mem) == mem_before and
          fence_calls == [] and
          machine.trace == [retire_row(0x1000, 0x0330000F, 0, 0)])
    second = machine.step(0) if first else False
    check('fence ebreak halt row follows', not second and
          hart.halted == 'ebreak' and
          machine.trace[1:] == ['0,00001004,00100073,,,halt:ebreak,,,'])

    machine, hart, retired = run_vector(0x0000100F, 0x00001000, {})
    check('fence.i reserved encoding halts illegal with word', not retired and
          hart.halted == 'illegal' and
          machine.trace == ['0,00001000,0000100f,,,halt:illegal,,,'])

    for name, word, pc, rd, value in U_VECTORS:
        machine, hart, retired = run_vector(word, pc, {})
        check(f'{name} writes and retires', retired and
              hart.pc == pc + 4 and hart.reg_read(rd) == value and
              machine.trace == [retire_row(pc, word, rd, value)])

    machine = loop_machine()
    machine.run('rr')
    rr_state = [(tuple(hart.x), bytes(hart.mem), hart.halted)
                 for hart in machine.harts]
    invariant = (machine.steps == 26 and
                 all(halted == 'ebreak' for _, _, halted in rr_state) and
                 machine.harts[0].x[1] == 0 and machine.harts[0].x[2] == 4)
    for seed in range(8):
        random_run = loop_machine()
        random_run.run('random', seed=seed)
        invariant = invariant and random_run.steps == 26 and [
            (tuple(hart.x), bytes(hart.mem), hart.halted)
            for hart in random_run.harts] == rr_state
    scripted = loop_machine()
    scripted.run([0] * 15 + [1] * 15)
    invariant = invariant and scripted.steps == 26 and [
        (tuple(hart.x), bytes(hart.mem), hart.halted)
        for hart in scripted.harts] == rr_state
    check('looping bne program is schedule-invariant, 26 retires', invariant)

    print(f'\nSummary: {FAILS} failed out of {CHECKS} checks')
    return FAILS


if __name__ == '__main__':
    sys.exit(selftest())
