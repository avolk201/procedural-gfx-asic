# CORDIC math core

Pipelined CORDIC in rotation mode, computing sine and cosine of an unsigned
16-bit phase (turns, so the value wraps mod 1). It exists so the pixel pipeline
can produce a sine-driven scene without a sine table. This file records the
convergence argument and the bit-width choices; every error figure here is
measured from `tb/cordic_golden.py` (24 self-checks) or `tb/sim_cordic.cpp`
(14 checks), not asserted.

The three-file split, and which is the oracle:

- `tb/cordic_golden.py` is the reference. Unbounded-precision Python, plus an
  exact fixed-point model. It self-tests against `math.sin`/`math.cos` and
  re-derives every hardcoded constant on each run, so a stale constant fails the
  model before it can mislead the RTL.
- `rtl/apu_cordic.sv` is the pipelined hardware.
- `tb/sim_cordic.cpp` drives all 2**16 phases through the RTL and compares to
  the model's generated table. A mismatch is an RTL bug by construction.

## Convergence and why the angle folds

Rotation mode iterates

    x' = x -/+ d * (y >>> i)
    y' = y +/- d * (x >>> i)
    z' = z -/+ d * atan(2**-i),   d = +1 while z >= 0

Each step's magnitude grows by sqrt(1 + 2**-2i); the running product converges
to K = 1.646760258. The input is pre-scaled by 1/K so the outputs land in the
unit range and no gain multiply is needed at the top.

The step angles only sum to 99.88 degrees (i = 0..15), so a full 360-degree
input is outside the plain rotation range. The fix is the fold, not extra
stages: map any phase to the nearest quadrant, run the pipe on the residual,
then negate/swap by quadrant at the output. Fold and select are combinational.

The exact iteration angles, `round(atan(2**-i) / (2*pi) * 2**24)` for i = 0..15:

    2097152 1238021 654136 332050 166669 83416 41718 20860
      10430    5215   2608   1304    652    326   163    81

Rounded, never truncated: truncation moves entries 3, 5, 10 to 14 by one count,
and the RTL must carry the identical integers or bit-exactness is impossible.
The last entry (81) also sets a floor on the accumulator width: with only 16
fractional angle bits that entry rounds to zero and the stage becomes dead
wiring that every tool still reports as clean.

## Bit widths, chosen by measurement

Values are scaled so that 1.0 is `2**22 = 4194304`, with two integer bits (one
sign, one unit) rather than one. One unit bit is the tempting choice and fails
by a hair: the value `+1.0` is exactly the code `4194304`, and the measured peak
intermediate is `4194306`, which is two counts past it. In a one-unit-bit format
that wraps negative. The exhaustive run records the real peaks:

    max |x|, |y| over all phases and stages = 4194306   (needs 2**23 range)
    max |z| including the folded z0         = 2097152   (angle accumulator, Q1.24)

Two integer bits therefore cover the datapath with margin, and the model needs
no saturation logic. It masks every stage anyway: masking is a no-op at this
width, but it is what keeps the model bit-exact if the width is ever narrowed,
rather than silently depending on "it never got big enough."

## Measurements > Derivation

The datapath is a fold/load register, then N = 16 iteration registers, then the
quadrant select pipelined out through `cos_mid`/`sin_mid`. That structure is
*roughly* 18 cycles and is easy to miscount by one (the fold itself is
combinational, so it adds no stage; there are two output registers, not one).
The repo does not trust that sum: `sim_cordic` check E drives the pipeline,
watches when `vld_o` first rises behind `vld_i`, and asserts the measured fill
equals the declared 18. If a stage is added or removed, E fails and forces the
number and the header comment to be reconciled. Throughput is one sample per
clock once filled; check T asserts the `vld_o` train is contiguous.

Convention (B18, 2026-09-25): E's fill of 18 counts tb iterations, from the
iteration `vld_i` is presented to the iteration `vld_o` is read after that
iteration's posedge. In system clocks the delay from registered input to
registered output is 19 (1 + 16 + 2 stages, the sum the structure above
spells out). Alignment consumers use the system number: apu_top sets
DEPTH=19 for the plasma prefetch (D18).

## Error budget

Measured over all 2**16 phases against `math.sin`/`math.cos` (2026-09-24), then
reproduced independently:

    max |error vs libm| = 3.171820e-05

(The worst phase is a near-tie between the sine and cosine arms and shifts with
comparison order, so the magnitude is the stable figure to quote, not a phase.)

The dominant term is the algorithm's residual angle, `atan(2**-15) =
3.052e-05`; the assertion bound `2**-14 = 6.104e-05` is exactly twice that, so
it catches a dropped iteration or a starved width (both measured to degrade to
~5e-04, far outside) while staying clear of honest rounding noise.

A model-free net: max `|cos^2 + sin^2 - 1| = 4.541e-06` over all phases, a
property of the table alone, independent of any oracle.

Two symmetry results worth recording because they tell you what "exact" means
here. Phase shifts of +90 and +180 degrees are *bit-exact* (zero counts): they
change only the output quadrant, an exact negate/swap of the same x, y. Negation
is not exact (worst 255 counts, bounded 266): `f(-t)` folds to a different
remainder and runs a different decision sequence, so it carries its own
residual. A harness that asserted `sin(-t) == -sin(t)` to zero is asserting
something CORDIC does not promise.

The cardinals are hand-written in the tb as a tripwire: `cos(0)` is
`2**22 - 1 = 4194303`, not `2**22`, and `sin(0)` is `-70`, not `0`. At
theta = 0 the tie-break rotates positive on every stage and the sum of fifteen
remaining steps cannot return exactly to zero, so a naive `cos(0) == 1` assert
fails on correct hardware.

## Not yet done

Nothing at the core itself, as of 2026-09-25. This section used to say the
CORDIC had never driven a pixel on the board; the plasma scene made that
stale. Three `apu_cordic` instances feed rtl/apu_plasma.sv, the module is in
the Quartus file list, and the build ran on hardware 2026-09-25 (.sof
0x00E40517): divclk Fmax 72.14 MHz against the 25.175 required, worst setup
slack +14.032 ns, full-width image on one OLED (B17). The open items around
it are integration-level, not math-core defects: DE alignment to the VESA
window (D18) and the demo GIF pipeline (phase 4.5).
