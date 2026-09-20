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

Observed: `make sim` prints `VSync lines: 0` every frame. The claim that VSync = 2 lines had never actually been measured.

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
