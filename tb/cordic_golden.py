#!/usr/bin/env python3
"""CORDIC golden reference for the phase-3 math core.

Two models, because they answer different questions. cordic_float is
unbounded precision and exists to show the algorithm converging; it feeds the
error-vs-iterations sweep. cordic_fixed is bit-exact with the RTL: same
widths, same truncating shifts, same masking. That one is the oracle the
testbench scores against, so it models the hardware rather than the maths.

Rotation mode, input pre-scaled by 1/K so the output needs no gain multiply.
Angle input is an unsigned phase in turns, phase/2**16 of a circle, so
wraparound is free. Output is signed Q2.22: value = int / 2**22.

Stdlib only.

    python3 tb/cordic_golden.py            selftest, exit code is the verdict
    python3 tb/cordic_golden.py emit PATH  golden hex for the C++ tb
    python3 tb/cordic_golden.py sweep      error vs iteration count

-v adds trace detail. Default output is PASS/FAIL lines plus a summary.
"""

import math
import sys

# Target configuration. The RTL must be parameterized identically; emit writes
# these into the golden file header and the tb fails loudly on a mismatch,
# because a stale golden file is indistinguishable from a correct one.
N_STAGES              = 16
DATA_WIDTH            = 24    # signed Q2.22
ANGLE_WIDTH           = 25    # signed Q1.24, FRACTIONAL_ANGLE_BITS + 1
FRACTIONAL_ANGLE_BITS = 24
FRACTIONAL_DATA_BITS  = DATA_WIDTH - 2
PHASE_WIDTH           = 16

# CORDIC gain K_n = prod sqrt(1 + 2^-2i) for i = 0..n-1. Written out so the
# model does not depend on float reproducibility across platforms; the
# selftest proves it against a recomputation rather than trusting it.
K_GAIN = 1.6467602578654548

# x0 = round(2**22 / K_16) = round(2547003.414715). Pre-scaling the input by
# 1/K removes the gain multiply on the output. Quantization error 9.888e-08,
# three orders below the algorithmic floor, so it is free.
X0 = 2547003

# atan(2**-i) / 2pi * 2**24, rounded to nearest. Rounded, not truncated:
# truncation differs by one count at i = 3, 5, 10, 11, 12, 13, 14, and the RTL
# must carry these same integers or bit-exactness is impossible. The smallest
# entry also sets a floor on FRACTIONAL_ANGLE_BITS: at 16 bits entry 15 rounds
# to 0 and that stage becomes dead wiring that every tool reports as clean.
ATAN_TABLE = [2097152, 1238021, 654136, 332050, 166669, 83416,
                41718,   20860,  10430,   5215,   2608,   1304,
                  652,     326,    163,     81]

# Measured 2026-09-24 over all 2**16 phases, and reproduced bit-for-bit by a
# second independent implementation. Recorded so a change to the model is a
# visible regression rather than a quiet one. These are informational; the
# asserted bound below is 2**-14, kept separate per B10.
EXPECTED_WORST       = 3.171820053873148e-05
EXPECTED_WORST_PHASE = 49511

# Asserted accuracy bound: 2**-14 = 6.104e-05, exactly twice the analytic
# residual atan(2**-15) = 3.052e-05. Catches both directions of parameter
# regression -- n=12 gives 4.83e-04 and W=16 gives 5.30e-04, both far outside.
ACCURACY_BOUND = 2.0 ** -14

# Negating the phase folds to a different remainder and so runs a different
# decision sequence, each carrying its own residual. Bounded at twice the
# single-angle worst (133 counts), measured 255. Never assert 0 here.
NEGATION_BOUND = 266

VERBOSE = '-v' in sys.argv


def sxt(value, width):
    """Sign-extend a width-bit two's complement value to a Python int."""
    mask = (1 << width) - 1
    value &= mask
    return value - (1 << width) if value >> (width - 1) else value


def validate_constants():
    """Prove every hardcoded constant against a recomputation. Called once by
    the selftest, not per evaluation: inline these used to re-derive 16 atan()
    values on each of 65536 calls, which was half the sweep's runtime."""
    problems = []

    product = 1.0
    for i in range(N_STAGES):
        product *= math.sqrt(1.0 + 2.0 ** (-2 * i))
    if abs(K_GAIN - product) >= 1e-15:
        problems.append(f'K_GAIN {K_GAIN} != recomputed {product!r}')

    if X0 != round((1 << FRACTIONAL_DATA_BITS) / K_GAIN):
        problems.append(f'X0 {X0} != round(2**{FRACTIONAL_DATA_BITS}/K_GAIN)')

    if len(ATAN_TABLE) != N_STAGES:
        problems.append(f'ATAN_TABLE has {len(ATAN_TABLE)} entries, need {N_STAGES}')
    for i, value in enumerate(ATAN_TABLE):
        expected = round(math.atan(2.0 ** -i) / (2.0 * math.pi)
                         * (1 << FRACTIONAL_ANGLE_BITS))
        if value != expected:
            problems.append(f'ATAN_TABLE[{i}] {value} != {expected}')

    return problems


def cordic_float(theta, n):
    """Unbounded-precision rotation mode. theta in radians, n stages.
    Returns (cos, sin). This is the instrument, not the oracle."""
    gain = 1.0
    for i in range(n):
        gain *= math.sqrt(1.0 + 2.0 ** (-2 * i))
    inverse_gain = 1.0 / gain

    # Fold to [-pi/4, pi/4]; the recurrence only converges inside
    # +-sum(atan(2**-i)) = +-99.88 deg, so a full circle needs this.
    turn = theta % (2.0 * math.pi)
    quadrant = int(turn / (math.pi / 2.0))
    folded_theta = turn - quadrant * (math.pi / 2.0)
    if folded_theta >= math.pi / 4.0:
        folded_theta -= math.pi / 2.0
        quadrant = (quadrant + 1) % 4

    x = inverse_gain
    y = 0.0
    z = folded_theta

    for i in range(n):
        # Tie-break at z == 0 is d = +1. Arbitrary, but it fires on the first
        # stage at phase 0 where z is exactly 0, so the RTL must match it.
        if z < 0:
            x_new = x + (y * (2.0 ** (-i)))
            y_new = y - (x * (2.0 ** (-i)))
            z_new = z + math.atan(2.0 ** (-i))
        else:
            x_new = x - (y * (2.0 ** (-i)))
            y_new = y + (x * (2.0 ** (-i)))
            z_new = z - math.atan(2.0 ** (-i))
        x, y, z = x_new, y_new, z_new

    if quadrant == 0:
        cos_theta, sin_theta = x, y
    elif quadrant == 1:
        cos_theta, sin_theta = -y, x
    elif quadrant == 2:
        cos_theta, sin_theta = -x, -y
    else:
        cos_theta, sin_theta = y, -x

    return (cos_theta, sin_theta)


def _rotate(phase):
    """Fold and run N_STAGES iterations. Returns
    (quadrant, x, y, z, peak, zpeak), where peak is the largest |x| or |y|
    produced at any stage and zpeak the largest |z| including the folded z0."""
    phase &= (1 << PHASE_WIDTH) - 1

    # At PHASE_WIDTH=16 these are >>14, &0x3fff, 8192, 16384. Derived rather
    # than literal so the fold cannot drift away from the parameters above.
    quadrant  = phase >> (PHASE_WIDTH - 2)
    remainder = phase & ((1 << (PHASE_WIDTH - 2)) - 1)
    if remainder >= (1 << (PHASE_WIDTH - 3)):
        remainder -= 1 << (PHASE_WIDTH - 2)
        quadrant = (quadrant + 1) & 3

    x = sxt(X0, DATA_WIDTH)
    y = 0
    z = sxt(remainder << (FRACTIONAL_ANGLE_BITS - PHASE_WIDTH), ANGLE_WIDTH)
    peak = max(abs(x), abs(y))
    zpeak = abs(z)

    for i in range(N_STAGES):
        # >> on a negative Python int floors, which is what SystemVerilog >>>
        # does on a signed operand. That agreement is the entire basis for
        # expecting bit-exactness. int() would truncate toward zero and break
        # it; never use int() or / where a shift is meant.
        if z < 0:
            x_new = x + (y >> i)
            y_new = y - (x >> i)
            z_new = z + ATAN_TABLE[i]
        else:
            x_new = x - (y >> i)
            y_new = y + (x >> i)
            z_new = z - ATAN_TABLE[i]

        # Python ints do not wrap; RTL registers do. Masking every stage is
        # what makes this model bit-exact rather than merely more accurate.
        x = sxt(x_new, DATA_WIDTH)
        y = sxt(y_new, DATA_WIDTH)
        z = sxt(z_new, ANGLE_WIDTH)
        peak = max(peak, abs(x), abs(y))
        zpeak = max(zpeak, abs(z))

    return quadrant, x, y, z, peak, zpeak


def cordic_fixed(phase):
    """Bit-exact model of the RTL. phase is an unsigned turn fraction.
    Returns (cos, sin) as signed Q2.22 integers."""
    quadrant, x, y, z, peak, zpeak = _rotate(phase)

    if quadrant == 0:
        cos_theta, sin_theta = x, y
    elif quadrant == 1:
        cos_theta, sin_theta = -y, x
    elif quadrant == 2:
        cos_theta, sin_theta = -x, -y
    else:
        cos_theta, sin_theta = y, -x

    # Re-mask after negating: -(-2**23) is +2**23 in Python but wraps back to
    # -2**23 in a 24-bit RTL register. Unreachable at Q2.22 (measured peak
    # 4194306 against a limit of 8388607), but a model that is only correct
    # while a parameter stays put will not warn anyone when it stops.
    return sxt(cos_theta, DATA_WIDTH), sxt(sin_theta, DATA_WIDTH)


# ---------------------------------------------------------------- selftest

CHECKS = 0
FAILS = 0


def check(name, ok, detail=''):
    """One helper, one fail counter, exit code from that counter."""
    global CHECKS, FAILS
    CHECKS += 1
    if not ok:
        FAILS += 1
    line = ('PASS: ' if ok else 'FAIL: ') + name
    if detail and (not ok or VERBOSE):
        line += '  ' + detail
    print(line)
    return ok


def build_table():
    return [cordic_fixed(p) for p in range(1 << PHASE_WIDTH)]


def selftest():
    print('=== constants ===')
    problems = validate_constants()
    check('K_GAIN, X0 and all %d ATAN_TABLE entries recompute' % N_STAGES,
          not problems, '; '.join(problems))

    print('\n=== known-answer vectors ===')
    kat = {
        0:     (4194303,      -70),
        5461:  (3632473,  2096982),
        8192:  (2965776,  2965867),
        10923: (2096982,  3632472),
        16384: (     70,  4194303),
        24576: (-2965867, 2965776),
        32768: (-4194303,      70),
        49152: (    -70, -4194303),
        65354: (4193669,   -73068),
        65534: (4194303,     -696),
    }
    for phase, expected in sorted(kat.items()):
        got = cordic_fixed(phase)
        # cos(0) is 2**22 - 1, not 2**22. The residual angle is why.
        check(f'phase {phase} -> {expected}', got == expected, f'got {got}')

    print(f'\n=== exhaustive accuracy, all {1 << PHASE_WIDTH} phases ===')
    table = build_table()
    scale = 2.0 ** FRACTIONAL_DATA_BITS
    worst = 0.0
    worst_phase = 0
    for phase, (c, s) in enumerate(table):
        theta = phase / float(1 << PHASE_WIDTH) * 2.0 * math.pi
        e = max(abs(c / scale - math.cos(theta)),
                abs(s / scale - math.sin(theta)))
        if e > worst:
            worst, worst_phase = e, phase
    check(f'max error <= 2**-14 ({ACCURACY_BOUND:.6e})',
          worst <= ACCURACY_BOUND,
          f'measured {worst:.9e} = 2**{-math.log2(worst):.2f} at phase {worst_phase}')
    check('worst case still matches the recorded regression value',
          abs(worst - EXPECTED_WORST) < 1e-15 and worst_phase == EXPECTED_WORST_PHASE,
          f'measured {worst!r} @ {worst_phase}, recorded '
          f'{EXPECTED_WORST!r} @ {EXPECTED_WORST_PHASE}')

    print('\n=== symmetries ===')
    quarter = 1 << (PHASE_WIDTH - 2)
    half = 1 << (PHASE_WIDTH - 1)
    full = 1 << PHASE_WIDTH
    dev = {'sin(t+90)=cos(t)': 0, 'cos(t+90)=-sin(t)': 0,
           'sin(t+180)=-sin(t)': 0, 'cos(t+180)=-cos(t)': 0,
           'sin(-t)=-sin(t)': 0, 'cos(-t)=cos(t)': 0}
    for phase, (c, s) in enumerate(table):
        c9, s9 = table[(phase + quarter) % full]
        c8, s8 = table[(phase + half) % full]
        cn, sn = table[(-phase) % full]
        dev['sin(t+90)=cos(t)']  = max(dev['sin(t+90)=cos(t)'],  abs(s9 - c))
        dev['cos(t+90)=-sin(t)'] = max(dev['cos(t+90)=-sin(t)'], abs(c9 + s))
        dev['sin(t+180)=-sin(t)'] = max(dev['sin(t+180)=-sin(t)'], abs(s8 + s))
        dev['cos(t+180)=-cos(t)'] = max(dev['cos(t+180)=-cos(t)'], abs(c8 + c))
        dev['sin(-t)=-sin(t)'] = max(dev['sin(-t)=-sin(t)'], abs(sn + s))
        dev['cos(-t)=cos(t)']  = max(dev['cos(-t)=cos(t)'],  abs(cn - c))
    # +90 and +180 change only the quadrant, and the output select is an exact
    # negate/swap of the same x,y, so these are exact. A nonzero count here is
    # a fold bug, not rounding.
    for name in ('sin(t+90)=cos(t)', 'cos(t+90)=-sin(t)',
                 'sin(t+180)=-sin(t)', 'cos(t+180)=-cos(t)'):
        check(f'{name} exact over the sweep', dev[name] == 0,
              f'{dev[name]} counts')
    for name in ('sin(-t)=-sin(t)', 'cos(-t)=cos(t)'):
        check(f'{name} within {NEGATION_BOUND} counts', dev[name] <= NEGATION_BOUND,
              f'{dev[name]} counts')

    print('\n=== datapath range (RTL needs no saturation logic) ===')
    limit = (1 << (DATA_WIDTH - 1)) - 1
    zlimit = (1 << (ANGLE_WIDTH - 1)) - 1
    peak = zpeak = 0
    for phase in range(1 << PHASE_WIDTH):
        _, _, _, _, p, zp = _rotate(phase)
        peak = max(peak, p)
        zpeak = max(zpeak, zp)
    check(f'peak |x|,|y| = {peak} within {DATA_WIDTH}-bit signed ({limit})',
          peak <= limit, f'{peak} > {limit}, Q2.{FRACTIONAL_DATA_BITS} overflows')
    check(f'peak |z| incl. folded z0 = {zpeak} within {ANGLE_WIDTH}-bit signed ({zlimit})',
          zpeak <= zlimit)

    print('\n=== cordic_float convergence, one iteration buys one bit ===')
    for n in (8, 12, 16):
        w = 0.0
        for i in range(1024):
            theta = i / 1024.0 * 2.0 * math.pi
            c, s = cordic_float(theta, n)
            w = max(w, abs(c - math.cos(theta)), abs(s - math.sin(theta)))
        bits = -math.log2(w)
        check(f'n={n}: {bits:.2f} bits, within 1.5 of n-1',
              n - 1.5 < bits < n + 0.5, f'max err {w:.4e}')

    print(f'\nSummary: {FAILS} failed out of {CHECKS} checks')
    return FAILS


# -------------------------------------------------------------------- emit

def emit(path):
    """Write the golden hex the C++ tb reads. Signed decimal, not hex: the tb
    gets a uint32_t from Verilator for a 24-bit port and must sign-extend
    anyway, and emitting hex would mean a second sign extension in the parser
    with nothing to catch it."""
    count = 0
    with open(path, 'w') as f:
        f.write(f'# cordic_golden.hex  n={N_STAGES} W={DATA_WIDTH} '
                f'FZ={FRACTIONAL_ANGLE_BITS} NA={PHASE_WIDTH} x0={X0}\n')
        f.write(f'# phase cos sin   (signed decimal, Q2.{FRACTIONAL_DATA_BITS})\n')
        for phase in range(1 << PHASE_WIDTH):
            c, s = cordic_fixed(phase)
            f.write(f'{phase} {c} {s}\n')
            count += 1
    print(f'{path}: {count} vectors, n={N_STAGES} W={DATA_WIDTH} '
          f'FZ={FRACTIONAL_ANGLE_BITS} NA={PHASE_WIDTH}')
    return 0


# ------------------------------------------------------------------- sweep

def sweep():
    """Error vs iteration count, the data behind the roadmap plot."""
    print('cordic_float over a 1024-point sweep; analytic residual for scale')
    print(f"{'n':>3} {'max err':>12} {'bits':>7} {'atan(2^-(n-1))':>16}")
    for n in range(4, 25):
        worst = 0.0
        for i in range(1024):
            theta = i / 1024.0 * 2.0 * math.pi
            c, s = cordic_float(theta, n)
            worst = max(worst, abs(c - math.cos(theta)), abs(s - math.sin(theta)))
        print(f'{n:>3} {worst:>12.4e} {-math.log2(worst):>7.2f} '
              f'{math.atan(2.0 ** -(n - 1)):>16.4e}')
    return 0


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '-v']
    if not args or args[0] == 'selftest':
        sys.exit(selftest())
    elif args[0] == 'emit':
        if len(args) < 2:
            print('emit needs an output path', file=sys.stderr)
            sys.exit(2)
        sys.exit(emit(args[1]))
    elif args[0] == 'sweep':
        sys.exit(sweep())
    else:
        print(f'unknown mode: {args[0]} (selftest | emit | sweep)', file=sys.stderr)
        sys.exit(2)
