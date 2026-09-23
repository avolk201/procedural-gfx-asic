# Verification

How this repo proves its claims. Everything here is reproducible with make.

## Scope and current stance

Everything is simulated in Verilator 5.050 on my M2 MacBook. Synthesis and
flashing run on a Bazzite box with Quartus Prime Standard 25.1 (Pro does not
support Cyclone V). First bring-up happened 2026-09-23: colorbars on a real
monitor, logged in docs/devlog.md along with the flash commands.

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

## Inventory

| Target | Proves | Run | Key numbers |
|---|---|---|---|
| apu_top via colorbars | VGA timing + pixel pipeline | `make sim` | HSync 96 px, VSync 2 lines (measured while low), frame = 420,000 cycles, one-frame PPM capture = 307,200 px |
| i2c_controller, closed loop vs C++ target model | full I2C write protocol | `make sim_i2c` (`-v` = bus trace) | 21 checks over T1/T2: busy latency <= CLK_DIV+1, hold-until-busy, one START before first data rise, 27 data rises, wire bytes {72,41,00} and {70,41,00}, ACK levels, one STOP, done width measured 250, ack_err sticky in T2; ~14,998 cycles/transaction |
| all RTL | zero-warning lint gate | `make lint`, `make lint_i2c` | runs before anything else |
| de10nano_top on DE10-Nano | first hardware bring-up | `quartus_sh --flow compile de10nano_top`, then `quartus_pgm -c "DE-SoC" -m jtag -o "p;output_files/de10nano_top.sof@2"` | lock LED instant on KEY0 release, blink ~1 Hz, real ADV7513 ACKed all 13 writes, colorbars on a 640x480 monitor |

## Method

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
- Timing evidence exists (Quartus 25.1, fitter meets the pixel clock) but the
  design is not fully constrained: the pixel-to-50 MHz toggle synchronizer
  has no false-path, so STA reports one benign setup failure (B15). Closing
  that is the next constraint commit.
- The pinout is now verified by hardware, not the manual: real video through
  every HDMI pin, 2026-09-23. The hdmi_tx_int assignment still references a
  port that does not exist in the design.
- No coverage metric beyond this inventory.
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
