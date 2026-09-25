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
| de10nano_top on DE10-Nano | hardware bring-up: colorbars 2026-09-23, plasma 2026-09-25 | `quartus_sh --flow compile de10nano_top`, then `quartus_pgm -c "DE-SoC" -m jtag -o "p;output_files/de10nano_top.sof@2"` | lock LED instant on KEY0 release, blink ~1 Hz, real ADV7513 ACKed all 13 writes, colorbars on a 640x480 monitor; worst slack +14.875/+0.163/+17.747/+0.358/+1.241, TNS 0.000, Slow 1100mV 100C (B16). Plasma build 2026-09-25 (.sof 0x00E40517): worst slack +14.032/+0.271/+16.882/+0.943/+1.241, TNS 0.000, divclk Fmax 72.14 MHz, 2058 ALMs / 3 DSP / 0 M10K bits, boiling plasma full-width on one OLED (B17). D18 build 2026-09-25 (.sof 0x00E4BE7C): worst slack +14.012/+0.168/+16.599/+0.698/+1.241, TNS 0.000, divclk Fmax 72.79 MHz, 2067 ALMs / 3 DSP / 0 M10K bits, DE aligned to the active window, image unchanged on the same OLED (B18) |
| apu_cordic + golden model | CORDIC vs Python model | `python3 tb/cordic_golden.py` (24 checks) then `make sim_cordic` (14) | RTL bit-exact to model over all 65536 phases; max |err| vs libm 3.172e-05 <= 2**-14; latency: fill 18 per sim_cordic's iteration convention = 19 system clocks (B18), 1/clk |


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
  structure. The second, auto-detected chain is the 50 MHz to pixel reset
  crossing (source rst_cnt[24], node u_sync_rst_pix|d[0]): detected, MTBF
  not calculated, still justified by construction (B16). The DE alignment
  gap closed with D18 (19e6272); the enforcing check runs in make sim.
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
