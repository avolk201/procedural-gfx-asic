# Devlog / bug graveyard

Each bug gets an entry: observed behavior, initial suspicion, actual fault, fix, and note. Wrong turns remain. Entries are written after diagnosis and updated when the fix lands, with the commit hash.

Status: OPEN means diagnosed, fix pending. FIXED means a commit hash is recorded.

## B1: `start_i` pulse swallowed by tick-gated FSM

2026-09-19. `rtl/i2c_controller.sv` and `tb/sim_i2c.cpp`. Status: FIXED. Fix: D1 contract and checker.

Observed: `sim_i2c` prints one SCL edge at cycle 0, then nothing. The loop runs the full 100k-cycle watchdog and exits with SUCCESS.

Initial suspicion: the tb clocking loop was wrong, or `done_o` was not wired up. Both checked out.

Fault: the FSM samples inputs only when `tick` fires, every 250 clk cycles. The tb asserted `start_i` for one cycle. The chance of that pulse coinciding with a tick was 1/250. The observed drop was deterministic, not a random miss.

Note: a pulse entering a slower sampling domain must be held until acknowledged, or latched by the receiver. The pattern matches a CDC problem even though one clock is used. Decision D1.

Update 2026-09-20: closed. RTL contract committed in 156179b; the harness now holds `start_i` until `busy_o` and scores a contract violation as a tb failure (dc71272).

## B2: tb reports SUCCESS for a transaction that never ran

2026-09-19. `tb/sim_i2c.cpp`. Status: FIXED. Fix: D6 rules.

Observed: after the 100k timeout, the exit message read "SUCCESS: Transaction completed without errors". `make` returned 0.

Fault: the while loop exits on `done_o` or the watchdog. The code after the loop checks only `ack_err_o`. No transfer occurred, so no error flag was set. `main` returned 0 unconditionally.

Note: a watchdog timeout is a failure path. `make` and CI read only the exit code. If the harness cannot return nonzero on timeout, it does not test completion. Decision D6.

Update 2026-09-20: closed. Watchdog expiry prints FAIL and exits nonzero in both harnesses (dc71272 for i2c, e3f3409 for vga).

## B3: Verilator top-level inout is not observable from C++

2026-09-19. `tb/sim_i2c.cpp` reading `sda_io`/`scl_io`. Status: FIXED. Fix: D4/D5 restructure.

Observed: the bus monitor saw one edge at cycle 0 regardless of internal FSM activity.

Fault: Verilator is two-state. At the top boundary, an `inout` port behaves as an input pin. The internal assignment `assign sda_io = sda_oe ? 0 : z` does not produce a resolved bus value at the port read by C++. The monitor watched a dead pin while the FSM, had it started, toggled `sda_oe` internally.

Note: open-drain buses need an explicit bus model in a two-state simulator. Move the tristate logic to the pad wrapper, give the core `oe` and `in` ports, and let the tb compute the wired-AND resolution. Decisions D4 and D5.

Update 2026-09-20: closed. Ports restructured in 156179b. The tb resolves the wired-AND bus in C++, seeded from DUT outputs after reset, and classifies edges on the resolved lines (dc71272).

## B4: `bit_cnt` never reloaded after first ACK

2026-09-19. `rtl/i2c_controller.sv`, SEND_BYTE/ACK states. Status: FIXED (67e237b).

Fault: START loads `bit_cnt` with 7. After each ACK, the FSM returns to SEND_BYTE, but nothing reloads `bit_cnt`. Bytes 2 and 3 (register address and data) send one bit each instead of eight.

Evidence: the captured bus trace showed 13 SCL rising edges (9 + 2 + 2) and a 7498-cycle transaction. After the fix: 27 rises, ~15k cycles. The scoreboard's edge-count and byte-reconstruction checks (dc71272) fail if this regresses; reintroducing the fault as a mutation failed 9 of 21 checks with nonzero exit.

Fix: ACK state reloads `bit_cnt <= 7` on the way to SEND_BYTE (67e237b).

## B5: STOP state never generates a STOP condition

2026-09-19. `rtl/i2c_controller.sv`, STOP state. Status: FIXED (67e237b).

Fault: the STOP sequence walks `bit_cnt` 2 -> 1 -> 0 to create the pattern: SDA low, then SCL high, then SDA rises. `bit_cnt` is 0 on entry (see B4), so the state takes the final branch on the first tick: it releases both lines and moves to DONE. SDA never makes the low-to-high transition while SCL is high, so no STOP appears on the wire. A real ADV7513 would be left mid-transaction.

Fix: same commit as B4 (67e237b); both faults concern the `bit_cnt` lifecycle. ACK now primes `bit_cnt <= 2` on the way to STOP, and the scoreboard requires exactly one STOP after the last ACK clock.

## B6: VSync width measurement always prints 0

2026-09-19. `tb/sim_main.cpp`. Status: FIXED (e3f3409).

Observed: `make sim` prints `VSync lines: 0` every frame. The claim that VSync = 2 lines had never been measured.

Fault: the tb increments `vsync_lines` only at SOF when `vsync` is low. SOF fires at line 0, the start of frame, where `vsync` is high. The counter cannot increment.

Fix: count line starts (`sol_o`) while `vsync` is low, between its falling and rising edges, and judge at the rising edge. Measures 2 lines per frame, asserted every frame.

Note: a counter that never leaves zero is not measuring the pulse width. The tb must be able to fail before its pass is trusted.

## B7: PPM capture writes two frames under a one-frame header

2026-09-19. `tb/sim_main.cpp`. Status: FIXED (e3f3409).

Observed: `sim/frame.ppm` is 1,843,215 bytes. The header declares 640x480: 307,200 pixels, or 921,615 bytes including the header. The file holds 614,400 pixels, or 960 rows.

Fault: the capture condition is `de_o && sof_count <= 1`, which spans frame 0 and frame 1. `docs/frame.png` looked correct because image readers display the first 480 rows and ignore trailing data.

Fix: capture exactly one frame, between SOF 1 and SOF 2, which also skips reset junk in frame 0. The file is now 921,615 bytes and the harness asserts the captured pixel count. The reconverted PNG is byte-identical to the committed `docs/frame.png`, the scene being static.

Note: the file size should have been checked. A 1.84 MB file against a 0.92 MB expectation would have failed loudly.

## B8: `apu_pkg` constants used before declaration

2026-09-19. `rtl/apu_pkg.sv`. Status: FIXED (2b08cdc).

Observed: none at the time. `H_TOTAL` and `V_TOTAL` referenced `ACTIVE_W`, `H_FP`, and related constants declared below them. Verilator accepts the file, and lint was clean.

Fault/risk: the LRM expects declare-before-use in a package. Quartus parses more strictly than Verilator. A latent portability defect that would surface at the first Quartus run, on the machine where iteration is slowest.

Fix: base constants before derived totals (2b08cdc). Lint clean, sim output identical.

## B9: `check()` lambda kept a private counter, exit code ignored it

2026-09-19. `tb/sim_i2c.cpp`. Status: FIXED pre-commit; only the fixed version was ever committed (dc71272).

Observed: no observable failure; caught in review. The first version of the `check()` helper declared `static int fail_count` inside the lambda, while a separate `fail_count` variable drove the exit code. Any `check(false, ...)` would print FAIL and still permit exit 0.

Fault: two counters tracked the same question. The lambda counter was never read, and the exit path saw only manual increments.

Note: this repeats the old tb defect at a higher level: printing failure while returning success. The harness exists to prevent that. A fail counter needs one owner and one path into the exit code. Test helpers that keep unread state deserve scrutiny.

## B10: watchdog set to expected duration, zero margin

2026-09-19. `tb/sim_i2c.cpp`. Status: FIXED pre-commit; only the fixed version was ever committed (dc71272).

Observed: no failure; caught in review. The first watchdog value was `WATCHDOG = 251 + 59*250 = 15001` cycles. `done_o` becomes observable one cycle after the DONE tick edge, so a healthy transaction would hit the watchdog near cycle 15002.

Fault: the value mixed expected duration, a scoreboard quantity, with a hang-detector bound, which needs margin. The tick derivation was correct: 1 START + 3*18 bytes + 3 STOP + 1 DONE = 59 ticks.

Fix: the watchdog is twice the expected duration. Expected duration stays an informational print, not a bound.

Note: without margin, the watchdog fails healthy runs and becomes a source of flakes.

## B11: `std::strcmp` without `<cstring>`

2026-09-19. `tb/sim_i2c.cpp`. Status: FIXED; the include is in the current harness (dc71272).

Observed: none. The file compiled because `verilated.h` transitively includes `string.h`.

Note: include what you use. This belongs with B8: Verilator accepts constructs that stricter tools reject. Acceptance by one tool is not compliance with the standard.

## B13: HDMI qsf written from memory, 39 of 40 pins wrong

2026-09-20. constraints/de10nano_pinout.qsf. Status: FIXED in this commit.

Symptom: none on hardware (no board yet). Caught by transcribing Terasic
manual Table 3-13 during audio feasibility research.

Findings vs the official table:
- hdmi_hsync was AD12, which is video data D0; real HS is T8
- hdmi_pclk was AE11, which is video data D6; real pixel clock is AG5
- I2C was AH10/AG11; real pins are U10/AA4
- DE, VS wrong (real: AD19, V13)
- all 24 data-bus assignments fabricated; two collided with audio pins
  (T12 = I2S SCLK, U11 = MCLK)
- only clk_50m_i = V11 survived, and it is not covered by Table 3-13

Cause: the original file was generated, never transcribed from the manual,
and carried into the rebuild during cleanup. It was flagged "untested" in
the roadmap, but flagging a landmine is not defusing it.

Fix: full rewrite from Table 3-13 with official signal names, audio pins
commented as Phase 6 reservations, TODOs for the three items Table 3-13
does not answer (clock pin section, IO_STANDARD string, ADV7513 channel
order). references.md now cites the table.

Lesson: constraints files are code. Every pin is a claim with a source, and
the source is the manual, not memory. The cheapest diff against the manual
is always the one done before the hardware arrives; the same file flashed on
a real board would have driven pixel clock onto a data pin and produced a
black screen with no obvious cause.

## B14: walker tb passed 7/7 on a ROM that cannot work on hardware

2026-09-23. rtl/adv7513_config.sv, rtl/de10nano_top.sv. Status: FIXED.

Symptom: none. Simulation stayed green throughout. Found by transcribing
the ROM against ADV7513 Programming Guide Rev B the way the qsf was
transcribed against Table 3-13 (B13).

Findings:
- 0x41 written as 0x10: only bit [6] is documented (power up); bit 4 was
  cargo cult. Now 0x00.
- 0xAF written as 0x04: bit [1]=0 is the DVI select and was correct, bit 2
  has no documented purpose anywhere in the guide. Now 0x00.
- 0x16 comment claimed "Style 1 pinout". Table 16: for RGB 4:4:4 the Input
  Style bits are don't-care; the pin map comes from the table directly.
  Value harmless, comment lied. Rewritten.
- 0x15 comment claimed "rising edge clock", unsupported. Rewritten.
- POR counter: Programming Guide 4.1 requires 200 ms before first I2C
  contact; the POR was 0.65 ms. First attempt at fixing it widened the
  counter declaration but left both index uses at bit [15]: a no-op, caught
  by grep on the symbol (the partial-refactor bug class, my own, this week).
  Counter now completes at 2^24 = 335 ms.
- The 8 fixed trim registers all match Table 14 bit-for-bit, and the
  ADV7511-era 0xC0 bank-select folklore does not apply to this part.

Lesson: protocol-verified is not content-verified. The tb proves the
controller puts the ROM on the wire with correct framing; it is blind, by
design, to whether the ROM is worth putting on the wire. Data entries are
claims about a $2 chip's datasheet, and like every other claim here they
need a citation or a diff against the spec table. The audit is the test.

## Bring-up: 2026-09-23 (first hardware)

Colorbars on a real monitor at 21:50, one word away from the committed
design (B15). Night log, because half the failures were the toolchain and
not the RTL:

- Quartus Prime Pro does not support Cyclone V. The family is
  absent from the device picker. Standard Edition 25.1 works, no license.
- The B8 landmine fired exactly the way B8 said it would: sync_reset.sv
  missing from the qsf, caught before the first compile (e6d1b63).
- Host is Bazzite (Fedora Atomic). Quartus into $HOME, udev rule on vendor
  09fb, done. One self-inflicted detour: exporting the Quartus PATH
  without the trailing :$PATH wipes /usr/bin from the shell, and the
  symptom is "bash: sed: command not found" in a terminal that looks
  perfectly healthy. hash -r after fixing PATH; bash caches lookups.
- The Nano's Blaster enumerates as 09fb:6010 "Altera DE-SoC", and
  quartus_pgm names the cable "DE-SoC", not "USB-Blaster II".
- JTAG chain is SOCVHPS at position 1, FPGA at position 2. From the CLI,
  targeting the fabric needs the @2 suffix:
  quartus_pgm -c "DE-SoC" -m jtag -o "p;output_files/de10nano_top.sof@2"
  A hand-written .cdf was ignored entirely; @2 is the idiom.
- .sof is volatile. Unplugging wipes it, and an unconfigured Nano
  ghost-glows all eight user LEDs, which reads as "something is on" if
  you don't know what the blank state looks like.
- The LED dashboard earned its pins. The board's user LEDs are unlabeled,
  so identity came from timing instead: lock asserts within ms of KEY0
  release, done/error after the 335 ms POR. That is what localized the
  failure to the PLL without a scope.
- Proven by hardware, no longer by simulation alone: every HDMI pin in
  Table 3-13 (real video through all of them), the I2C pins (the real
  ADV7513 ACKed all 13 writes), the RGB332-to-24-bit channel map, the POR
  length. The TV took 640x480 without complaint.
- Still open: the toggle-sync false path (B15), the hdmi_tx_int pin
  assignment with no matching port, four-state sim.

## B15: PLL never locks; STA does not check VCO legality

2026-09-23. rtl/pll_25m.sv. Status: FIXED (a0dd504).

Observed: first flash runs, LED0 (cfg_done) lights ~0.4 s after KEY0
release, but no lock LED, no blink, no video.

Initial suspicion: the -7.255 ns setup failure on clk_50m from the first
compile. A 7 ns miss looks like a real bug in the 50 MHz domain. Wrong
turn: worst slack and End Point TNS are equal, so exactly one endpoint
fails. The only single pixel-to-50 MHz path is pix_alive_tgl into
tgl_sync[0], a toggle synchronizer input that is meant to be false-pathed.
Benign.

Second wrong turn: blamed ADV7513 power-up (cfg_error, HPD). Unplugged the
HDMI cable and re-ran; the same LED lit at the same delay. The test could
not discriminate: the chip's main rails do not drop when you unplug the
cable, so the config completes either way. The lit LED was cfg_done all
along; the real chip had ACKed everything.

Fault: nothing lit instantly on KEY0 release, so pll_locked never
asserted. The compile log had already printed the reason and I had not
read it. The SDC derivation lines show the VCO: 50 MHz * 1839/64 =
1436.7 MHz, then /57 to the 25.2 MHz output. The Cyclone V general PLL VCO
tops out at 1300 MHz. The silicon cannot lock to an out-of-range VCO.
derive_pll_clocks does the arithmetic and reports a clean generated clock
either way; TimeQuest never checks VCO legality. Verilator can't see it
either: the behavioral branch in pll_25m.sv ties locked high by
construction.

Fix: fractional_vco_multiplier("true") in the hand-instantiated
altera_pll (a0dd504). Quartus re-solves the divider set with a legal VCO.
Lock LED lights instantly, blink at ~1 Hz, colorbars on the monitor.
Verified on hardware before committing.

Lesson: simulation-clean is not silicon-legal, and B14's rule extends to
megafunction parameters. Every value typed into an altera_pll instance is
a claim about the part, and no harness in this repo can check it. The
Quartus log can: the create_generated_clock lines print the derived VCO.
Read them after every PLL edit, same duty as diffing the qsf against
Table 3-13.

## B16: Two false reads in the STA re-run, and what set_clock_groups hides

2026-09-23. constraints/timing.sdc. Status: FIXED (8911f72), on hardware
2026-09-24.

Observed: B15's fix looked verified twice before it was. Both times the
evidence could not have failed.

Wrong turn one: grepped the STA report for an 85C corner. The -I7 part reports
Slow and Fast models at 100C and -40C, no 85C model. The grep printed nothing,
and nothing looks exactly like a clean report.

Wrong turn two: read output_files/de10nano_top.sta.rpt and reported slack
without checking which compile wrote it. A stale sta.rpt is indistinguishable
from a fresh one by content. Plausible numbers, wrong build.

Fault: both were me taking a result that could not be wrong as one that had
passed. Same shape as B2.

Fix, now procedure: rm the sta.rpt before compiling, check exit code, check
the report mtime, then read numbers. Grep the corners the part reports, not
the one I remembered from another family.

The real cost is what the constraint hides. set_clock_groups -asynchronous
ignores setup, hold, recovery and removal between the groups. So
the -5.249 ns cross-domain recovery failure vanished with no targeted
set_false_path. And nothing now times the 50 MHz to pixel reset assertion:
sys_rst_n && pll_locked into u_sync_rst_pix (de10nano_top.sv:108). sync_reset
aligns deassertion only, so assertion crosses raw. Justified by construction,
not STA. A pixel-domain reset source would make it measurable again.

One flow, provenance pinned: started 22:51 from b2eb094 plus the constraints
patch; fit.rpt, sta.rpt and the .sof all written 23:00, sta.rpt 197416 bytes,
so the slack below and the flashed .sof are the same run. Exit 0, no Critical
Warning, no Error lines. Worst-case slack, Slow 1100mV 100C:

    before (332148)     after
    -12.564  setup      +14.875
     -0.070  hold        +0.163
     -5.249  recovery   +17.747
     +0.453  removal     +0.358
     +1.241  min pw      +1.241

  End Point TNS 0.000 on both clocks. Setup per clock: clk_50m +14.875,
  divclk +33.326. Recovery per clock: clk_50m +17.747, divclk +37.864. Hold
  was failing as well as setup, which the headline setup slack hides.

Flash 23:09:49: device index 2, JTAG ID 0x02D020DD, .sof checksum 0x00B31381,
0 errors, 0 warnings.

Board 2026-09-24, after KEY0 press and release: LED2 instant, LED1 off, LED3
about 1 Hz, LED0 after a delay I eyeballed at roughly half a second, not
timed. The design figure is 339 ms: the 2^24-cycle POR (de10nano_top.sv:20,
335.5 ms at 50 MHz) plus 13 writes at 14,998 cycles each (3.9 ms). An untimed
eye over-reads short intervals, so I record both numbers and claim neither a
stopwatch match nor a discrepancy. Eight colorbars at 640x480 on the monitor.

Lesson: deleting a failing path hides it rather than fixing it. The test of
the fix is whether anything still measures the path. Check the mtime before
the numbers, same as rule 5.

## B17: plasma is perfect on the OLED, and the DE window is 18 clocks off

2026-09-25. rtl/apu_plasma.sv and the scene contract. Status: OPEN. D18
records the fix; no RTL has changed.

Observed: the plasma build ran on hardware. Provenance: box synced to 145a1ec
(36 files, digest match), sta.rpt deleted before compile, compile started
01:16:54, Flow Status "Successful - Fri Sep 25 01:25:09", quartus_pgm at
01:25:35, .sof checksum 0x00E40517, JTAG ID 0x02D020DD, device index 2,
0 errors, 0 warnings. Worst-case slack, Slow 1100mV 100C: setup +14.032,
hold +0.271, recovery +16.882, removal +0.943, min pulse width +1.241, End
Point TNS 0.000; divclk Fmax 72.14 MHz against the 25.175 needed. Resources:
2058 of 41910 ALMs, 3 DSP blocks, zero block memory bits. On the OLED in
original-aspect mode: boiling plasma, full width, no band, no shift. Video
committed as docs/plasma-bring-up.mov (6d1e9ab), re-encoded to
docs/plasma-bring-up.mp4 (640x360, 30 fps, 588044 bytes) because GitHub
would not display the 4.8 MB mov inline.

Initial suspicion (the agent session's, written down before the flash per
rule 5): the scene contract delays de_o by the pipeline depth, so at depth 18
the burst spans h_cnt [18, 658) while hsync is low over [656, 752).
Predicted: an 18 px blank band at the left edge, the right 18 columns
clipped, and 2 clocks of DE inside the sync pulse per line. The board showed
none of it.

Wrong turn inside the wrong turn: the re-check put the TV in original aspect
and still saw nothing, but on an OLED the predicted band is pixels-off black
against a black bezel. That observation could not have come out wrong
either. Rule 5 applies to the choice of instrument as much as to the
experiment itself.

Fault: the prediction named the wrong device as the one hiding the
misalignment. The ADV7513 does not realign anything: PG Rev B 4.3.6 says of
the separate HS/VS/DE method that "all necessary signals are provided so
neither Sync generation or DE generation is required", and the shipped ROM
leaves the DE generator off (0x17[0]=0) and sync adjustment off (0x41[1]=0).
The TMDS stream carries the shifted burst and the 2-clock overlap. The OLED
absorbs it, most plausibly by starting each line's active data at the first
DE-high pixel. The defect is real and now sink-dependent: DE does not match
the VESA active window, one TV tolerates it, and no sim could see it because
both captures write pixels sequentially and reconstruct the intended image
whatever the screen position.

Fix: implemented the same day (19e6272): back-porch prefetch per D18, de_o
aligned to [0, 640), scene depth bound 48. The enforcing check landed first
(2ad39fc) and failed the pre-fix plasma build at 2880 cycles over the tb's
two frames, which exposed B18. Re-verified on hardware 2026-09-25 15:19:50,
.sof checksum 0x00E4BE7C, image unchanged on the same OLED.

Correction (2026-09-25): the burst arithmetic above used latency 18. The
system-level delay is 19 clk (B18): read [19, 659), 3 clocks of overlap per
line (1440 per frame), HS-to-DE gap 67 px, and a 19 px predicted band. The
lesson's claim that the arithmetic was right no longer holds: the layer
analysis was correct, the clock count was not (B18).

Lesson: when an observation contradicts a prediction, find which layer
contradicted it before retiring the prediction; the arithmetic here was right
and the layer was the TV, not the transmitter. One sink is a sample size of
one. And a capture that reconstructs position from a stream cannot check
position; only the timing signals can.

## B18: the latency everyone wrote as 18 is 19 at system level

2026-09-25. apu_cordic latency convention, D18 numbers. Status: FIXED
(19e6272 uses the measured 19; docs corrected in the same pass).

Observed: the red run of the new DE-during-HSync check (2ad39fc) measured
2880 overlap cycles over the tb's two frames on the pre-fix plasma build.
The prediction from the documented latency was 1920 (2 per line). 2880 over
960 active lines is 3 per line, so the burst starts at h=19, not h=18.

Initial suspicion: an off-by-one in the new check's window. Wrong turn: the
check spans exactly two frames and colorbars reads 0, as predicted; the 2880
is real.

Fault: a convention mismatch that cordic.md had already described without
reconciling. The vld chain is 19 register stages: valid_pipe[0] (1),
valid_pipe[1..16] (16 more), vld_mid (18), vld_o (19). sim_cordic presents
vld_i in iteration 0 and reads vld_o after the posedge of iteration 18, so
check E measures a fill of 18 and LATENCY=18 is self-consistent under that
convention. Any consumer that treats the 18 as a system-clock delay is one
clock off. B17, the D18 context, the D17 consequence, the verification
inventory, cordic.md's own structure paragraph, and both scene comments all
carried the 18.

Fix: DEPTH=19 for plasma in apu_top (19e6272), with the convention written
into the comments at the point of use. Post-fix, measured: overlap 0 in both
scenes, DE count 614400, plasma frame capture byte-identical to the pre-fix
control (sha256 de1ba729...), and v_cnt now resets to V_TOTAL-1 so the first
active line after reset is fully prefetched; no tb expectation was loosened
to get there. Hardware re-verify: Flow Successful 15:19:06 at HEAD 9f5dc7b,
worst slack setup +14.012 / hold +0.168 / recovery +16.599 / removal +0.698 /
min pulse width +1.241, TNS 0.000, divclk Fmax 72.79 MHz, .sof 0x00E4BE7C
flashed 15:19:50, image unchanged on the OLED. sim_cordic keeps its 18 by
design; unifying the contract's wording is open.

Lesson: a latency number without its measuring convention will be consumed
under a different one. cordic.md said "roughly 18, easy to miscount by one"
next to a structure that sums to 19, and every document that repeated the 18
inherited the miscount. The check that caught it was expected to fail and
failed at a number nobody had predicted; the surprise was the point.
