# Verification

How this repo proves its claims. Everything here is reproducible with make.

## Scope and current stance

Everything is simulated in Verilator 5.050 on my M2 MacBook. Synthesis and
flashing run on a Bazzite box with Quartus Prime Standard 25.1 (Pro does not
support Cyclone V). First bring-up happened 2026-09-23: colorbars on a real
monitor, logged in docs/devlog.md along with the flash commands. The plasma
scene followed on hardware 2026-09-25 (B17): timing closed, full-width image
on one OLED; the D18 DE-aligned build re-verified the same day (B18).

Constants and constraints in the code trace back to the specs listed in
docs/references.md. I can't include the PDFs themselves (copyright), but if
you're messing around in the code, download them. The numbers in apu_pkg.sv
and the I2C timing come straight out of those documents, not out of thin air.

## Rules

1. A timeout is a failure, not an exit condition.
   An early version of tb/sim_i2c.cpp used the watchdog as a loop exit and
   checked nothing else, so a transaction that never started still printed
   SUCCESS and returned 0. That mistake cost me over a full day. Now: the
   watchdog path prints one loud FAIL, skips the remaining checks (after a
   hang they mean nothing), and exits nonzero.

2. Assert positive expectations, not the absence of error flags.
   Same bug, other half: "nothing happened" and "no error" look identical if
   you only check an error flag. Checks say what must happen instead: 27 SCL
   data rises, 9 per byte; wire bytes reconstructing bit-exact to
   {0x72, 0x41, 0x00}; exactly one STOP after the last ACK.

3. The exit code is the interface.
   make and CI read exit codes, not prose. A test that prints FAIL and
   returns 0 is worse than no test, because it manufactures confidence. Every
   verdict goes through one check() helper with a single fail counter, and
   main returns nonzero if that counter is nonzero.

4. A check must fail at least once before it is trusted (mutation testing).
   Break what the check watches, confirm red, restore, confirm green. Real
   example, from dc71272: removing the bit_cnt reload in the controller
   (bug B4) fails 9 of 21 checks with nonzero exit. You don't trust a teacher
   until you've seen them grade a wrong answer.

5. Name the observable difference before touching the board.
   If a test cannot come out wrong, it is not a test. B15: I unplugged the
   HDMI cable to check the ADV7513, re-ran, and saw the same LED at the same
   delay. The chip's rails do not drop when the cable comes out, so the config
   walker finishes either way. Before you touch the board, write down what
   changes if you are wrong. The monitor is not the only instrument: LED2
   failing to light on KEY0 release is what localized B15 (docs/deploy.md).

## Inventory

| Target | Proves | Run | Key numbers |
|---|---|---|---|
| apu_top via colorbars | VGA timing + pixel pipeline | `make sim` | HSync 96 px, VSync 2 lines (measured while low), frame = 420,000 cycles, one-frame PPM capture = 307,200 px, DE during HSync = 0 cycles (check added with D18) |
| apu_top via plasma | scene contract at depth 19 (B18), look check | `make sim_plasma` (`+frame=N` window) | 307,200 px captured in frame window 1; 29 distinct RGB332 codes across 60 frames (D17 baseline: 28); every frame of docs/plasma.gif byte-identical to its capture on round-trip |
| i2c_controller, closed loop vs C++ target model | full I2C write protocol | `make sim_i2c` (`-v` = bus trace) | 21 checks over T1/T2: busy latency <= CLK_DIV+1, hold-until-busy, one START before first data rise, 27 data rises, wire bytes {72,41,00} and {70,41,00}, ACK levels, one STOP, done width measured 250, ack_err sticky in T2; ~14,998 cycles/transaction |
| all RTL | zero-warning lint gate | `make lint`, `make lint_i2c` | runs before anything else |
| de10nano_top on DE10-Nano | hardware bring-up: colorbars 2026-09-23, plasma 2026-09-25 | `quartus_sh --flow compile de10nano_top`, then `quartus_pgm -c "DE-SoC" -m jtag -o "p;output_files/de10nano_top.sof@2"` | lock LED instant on KEY0 release, blink ~1 Hz, real ADV7513 ACKed all 13 writes, colorbars on a 640x480 monitor; worst slack +14.875/+0.163/+17.747/+0.358/+1.241, TNS 0.000, Slow 1100mV 100C (B16). Plasma build 2026-09-25 (.sof 0x00E40517): worst slack +14.032/+0.271/+16.882/+0.943/+1.241, TNS 0.000, divclk Fmax 72.14 MHz, 2058 ALMs / 3 DSP / 0 M10K bits, boiling plasma full-width on one OLED (B17). D18 build 2026-09-25 (.sof 0x00E4BE7C): worst slack +14.012/+0.168/+16.599/+0.698/+1.241, TNS 0.000, divclk Fmax 72.79 MHz, 2067 ALMs / 3 DSP / 0 M10K bits, DE aligned to the active window, image unchanged on the same OLED (B18). 2026-09-29 flash of the assertion build at a5b8fde: .sof sha256 184215f8..., plasma full-width on a TV, dashboard nominal, same-day observation |
| apu_cordic + golden model | CORDIC vs Python model | `python3 tb/cordic_golden.py` (24 checks) then `make sim_cordic` (14) | RTL bit-exact to model over all 65536 phases; max |err| vs libm 3.172e-05 <= 2**-14; latency: fill 18 per sim_cordic's iteration convention = 19 system clocks (B18), 1/clk |
| rv32asm + rv32enc (tools/) | RV32I_Zicsr encoding fidelity, CPU ladder step 2 | `python3 tools/tests/test_rv32asm.py`, `python3 tools/tests/test_rv32enc.py` | 101 + 246 checks, exit code = fail count; 46-row encode/decode round trip; spec-derived scramble anchors; la is pc-relative AUIPC+ADDI (B19); suites seen to fail under three mutations: SLTIU funct3, LA pc, one unpack_b bit |
| rv32iss (tools/) | OP/OP-IMM, load/store, branch, jump, U-type and FENCE semantics, private memory, CSV retirement/halt trace, schedule-invariant completion | `python3 tools/tests/test_rv32iss.py` (also `make tools-tests`) | 101 checks; rr + scripted + 8 seeded schedules reach ebreak with identical registers and private RAM, straight-line program and looping-bne program (26 retires per run) |
| make coverage, all five harnesses | merged line/toggle/branch/expr coverage with enforced floors | `make coverage`, also a CI step | 2026-09-29 baseline: line 88.7% (133/150), toggle 87.3% (2465/2824), branch 98.1% (102/104), expr 95.7% (154/161); floors line >= 85 and toggle >= 84, baseline minus margin per B10; per-harness dats merged with verilator_coverage |


## Method

### ISS mutation predictions (written before mutation)

1. Replace I-immediate sign extension with zero extension: `andi sign-extends
  negative immediate` and `sltiu compares against sign-extended immediate
  as unsigned` must fail. Observed: 2 red checks.
2. Remove the 5-bit mask from register shift amounts: `register shift masks
  high shift-amount bits` must fail. Accepting an SLLI with nonzero
  `imm[11:5]` must fail both `SLLI with nonzero imm[11:5] is illegal` and
  `illegal SLLI records halt row`. Observed: 1 and 2 red checks respectively.
3. Allow a write into register slot zero: `rd=x0 write is ignored and traced
  as zero` must fail because the backing x0 slot becomes nonzero. Observed:
  1 red check.
4. Remove 32-bit masking on register writeback: `ADD wraps to exactly zero`
  must fail. Observed: 5 red checks, including left/right-shift results that
  also require 32-bit truncation.
5. Suppress or mislabel halt records: `ecall halt reason`, `ebreak halt
  reason`, and `illegal halt reason` must fail on their exact CSV rows.
  Observed: 7 red checks, including illegal-SLLI, misaligned-fetch, and bus
  halt rows. Each mutation was restored before the next was applied.

### ISS memory mutations (isolated `/tmp` copies)

Each mutation below was applied alone to a fresh copy of `tools/` and run
against the 56-check ISS suite of that time; step 3 grew the suite to 101.
All returned nonzero and were restored by discarding the temporary copy.

1. M1, return raw data instead of sign-extending signed loads: 2 red checks
  (`lb sign extension and memory trace`, `lh sign extension and memory
  trace`).
2. M2, sign-extend every load, including unsigned loads: 3 red checks
  (`lbu sign extension and memory trace`, `lhu sign extension and memory
  trace`, `RAM byte load selects addressed lane`).
3. M3, decode store offsets from the I-type immediate instead of the split
  S-type fields: 2 red checks (`sb writes data lanes and memory trace`,
  `sw writes data lanes and memory trace`).
4. M4, align RAM load addresses down to a word boundary: 1 red check
  (`RAM byte load selects addressed lane`).
5. M5, omit the address-derived lane shift for RAM stores: 2 red checks
  (`sb writes data lanes and memory trace`, `sh writes data lanes and memory
  trace`).
6. M6, skip load alignment validation: 1 red check (`misaligned lh to x0
  traps before device access`).
7. M7, ignore the byte offset when extracting device-read lanes: 2 red checks
   (`lb to x0 still performs device read side effect`, `device byte load
   extracts addressed lane`).
8. M8, return early on rd=x0 loads before the memory access: 2 red checks
   (`lb to x0 still performs device read side effect`, `misaligned lh to
   x0 traps before device access`); both vectors route through rd=0, so
   skipping the access kills the side effect and the trap together.
9. M9, remove the write-value right-justify in dispatch_device: 1 red check
   (`device byte store right-justifies dirty rs2`). Entries 8 and 9 were run
   by the agent in isolated /tmp copies on 2026-09-29, predictions written
   before each run, copies discarded afterwards.

### ISS control-transfer mutations (step 3, isolated /tmp copies)

Predictions were written before each run. Each mutation was applied alone to
a fresh copy of `tools/`, landing verified by exact-match grep before
believing the color, and the copy discarded afterwards. Run by the agent
2026-10-03 against the 101-check suite.

- M-A, taken branch target as pc+4+imm: 8 red (7 taken vectors plus the
  looping-bne schedule-invariance check).
- M-B, branch immediate assembled from the contiguous imm12 field (leaks
  rs2[4:0] at 24:20): 8 red, same set; the loop red is a downstream
  consequence.
- M-C1, blt compares unsigned: first run 1 red, predicted 2. The cause was
  the vector set: a not-taken vector at offset +4 is degenerate, a wrongly
  taken branch lands exactly on pc+4, the same observable. The two +4 rows
  were re-encoded at +8 (bne_nt_x1eqx1_p8 0x00109463, blt_nt_p2_p8
  0x0020C463), re-run: 2 red. Vector change, no expectation loosened.
- M-C2, bgeu compares signed: 2 red (bgeu_taken_p1_m4, bgeu_nt_p2_m8).
- M-D, branch retirement row prints fields[rd]: 13 red, every branch row
  (all offsets chosen so bits 11:7 are nonzero).
- M-E, jalr base re-read after the link writeback: 1 red
  (jalr_x2_x2_p4, landing 0x1008 instead of 0x2004). The unprivileged volume
  carries no explicit old-value sentence in this revision; the rule is the
  printed 2.5.1 order plus Table 3.
- M-F, jalr drops the bit-0 clear: 1 red (jalr_x1_x2_odd_imm_clear,
  pc 0x2001).
- M-G, fence halts instead of retiring: 2 red (the retire row and the ebreak
  follower); the fence.i reserved-encoding row stays green.

Three ideas the testbenches are built on. docs/decisions.md carries the full
reasoning behind each.

- Contract in the header, scoreboard executes it (D1, D11). The
  i2c_controller header states caller duties and module guarantees as
  falsifiable claims with numbers in them. The tb checks are those claims,
  running.
- The tb owns the physical layer (D4, D5, D8). Verilator is 2-state and will
  not resolve an open-drain bus for you, so the tb computes the wired-AND
  itself: a line is low if the controller or the target pulls it, high
  otherwise. The high is the pullup resistor, expressed as logic. The target
  is a minimal behavioral ADV7513 in C++: write-only, ninth-clock ACK/NACK,
  no register file.
- Model forgiving, scoreboard strict (D9, D11). The target model never
  assumes correct framing; it counts bits and reports. When B4 truncated
  bytes 2-3, the model reported what it saw (one complete byte, 13 rises, no
  STOP) instead of hanging, and the checks turned that into evidence.

## Known gaps

- No four-state simulation. X-propagation and uninitialized-register classes
  are untested; an Icarus tier may cover this later.
- Timing closed and measured (B16): Quartus 25.1, Slow 1100mV 100C, worst
  slack setup +14.875 / hold +0.163 / recovery +17.747 / removal +0.358 /
  min pulse width +1.241, End Point TNS 0.000 on both clocks. The price:
  set_clock_groups -asynchronous ignores recovery and removal too, so nothing
  times the 50 MHz to pixel reset assertion (sys_rst_n && pll_locked into
  u_sync_rst_pix, de10nano_top.sv:108). sync_reset aligns deassertion only,
  assertion crosses raw. Justified by construction, not STA. A pixel-domain
  reset source would make it measurable again.
- The pinout is now verified by hardware, not the manual: real video through
  every HDMI pin, 2026-09-23. The dead hdmi_tx_int assignment is gone;
  PIN_AF11 (ADV7513 INT) stays unassigned on purpose.
- Computed-color scenes are not dithered. Ordered Bayer dither was evaluated
  against the hue-wheel plasma and rejected as a color-depth limit (D17);
  banding at RGB332 is accepted and measured (distinct=28, longest-run=514px).
- CDC MTBF: the specified pixel-to-50 MHz toggle chain measures > 1e9 years
  worst-case at 17.920 ns available settling (2026-09-25 D18 build);
  Quartus models it as length 1, conservative against the real two-flop
  structure. The second chain is the 50 MHz to pixel reset crossing
  (source rst_cnt[24], node u_sync_rst_pix|d[0]). B16 left it auto-detected
  with MTBF not calculated, justified by construction. Corrected
  2026-09-29: SYNCHRONIZER_IDENTIFICATION FORCED plus CHAIN_LENGTH 2 on
  u_sync_rst_pix|d[1] (6434290) make it a specified chain, and
  report_metastability on the 2026-09-29 compile finds 2 chains, computes
  both (fraction uncalculated 0.000), worst-case MTBF 1e9 years at 17.761 ns
  worst-case settling (docs/artifacts/d18/metastability.rpt). The DE
  alignment gap closed with D18 (19e6272); the enforcing check runs in
  make sim.
- The Python tools suite runs in CI via `make tools-tests`.
- ISS instruction-misaligned reporting deviates from unprivileged volume 2.2
  (p. 25): the spec generates the exception on the taken branch or jump
  itself; the ISS retires the jump and halts at the next fetch, so the halt
  row carries the target pc and an empty inst_word. Open decision before RTL
  M1: move the check onto the jump (contract section 9 trace format allows
  it, pc is the faulting PC and inst_word the fetched word) or keep the
  fetch-stage convention as an acknowledged deviation. RTL and cosim must
  match whichever stands.
- ISS vectors can only retire from a source pc inside the per-hart 32 KiB
  window; an out-of-window fetch halts bus before decode. Two early jump
  rows were amended 2026-10-03 for this (jal_x1_min_m to pc 0x1000, target
  0xFFF01000; jal_x1_wrap_fwd to pc 0x7FFC, link 0x8000, target 0x8004).
  The full 2^32 link wrap is unreachable in the ISS and becomes a live case
  only in RTL cosim against the full address map.
- Coverage is merged line and toggle across the five harnesses with floors
  (make coverage, CI step); branch and expr are reported but not floored.
  The 17 uncovered line points at baseline are not itemized yet; itemize
  them the first time a floor bites, not before, and never raise a floor
  without a new measurement.
- No formal methods. The I2C contract is enforced by simulation only.

## Conventions for new testbenches

Phase 2 modules follow these so the discipline carries forward instead of
being rediscovered:

- Naming: tb/sim_<module>.cpp, make target sim_<module>.
- One check() helper, one fail counter, exit code from that counter.
- Derive the watchdog from FSM arithmetic and give it margin. Expected
  duration is a separate informational number, never the bound (B10).
- -v flag for the verbose trace, default off. Default output is PASS/FAIL
  lines plus a summary.
- Mutation-test at least one check per new assertion class before committing.
- Any bug a tb catches gets a docs/devlog.md entry with measured evidence.
