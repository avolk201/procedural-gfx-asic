# Decision log

Numbered record of design decisions, in the order they were made. Append only.
If a decision gets reversed later, the new entry supersedes the old one and says
so. Rejected options stay in the entry, since the trade space is the part worth
remembering.

Referenced from commit messages as (Dn).

---

## D1: I2C start handshake, caller holds and checker enforces

2026-09-19. Module: rtl/i2c_controller.sv

Context: the FSM only samples inputs on `tick`, once every CLK_DIV (250) clock
cycles. A single-cycle `start_i` pulse is seen with probability 1/250. My first
tb pulsed it for one cycle and the transaction never started. sim_i2c ran to
its 100k-cycle timeout with one SCL edge printed.

Options:
1. Caller holds `start_i` until `busy_o` rises, contract documented in the
   module header. Zero logic.
2. Latch the request in the fast domain (pending flag, consumed on tick).
   Fire-and-forget for callers, costs a couple flops.

Decision: option 1, with teeth. The contract goes in the module header AND a
protocol checker in the C++ tb fails the sim if `start_i` drops before `busy_o`
rose or pulses while busy. A hold contract with no enforcement is just a
comment; with the checker it is machine-verified at every tb run.

Rationale: I2C here is config-only, with exactly one planned caller (the
ADV7513 ROM walker). A specified req/ack protocol that verification enforces
is a stronger story than hiding the timing inside the peripheral. The config
FSM will implement hold-until-busy as its step state anyway.

Consequence: any future caller must respect the contract or its sim fails.
That is the point.

Related: eaf0f41 (module), 5ea591a (tb that found it).

## D2: start_i while busy: ignore, flag in sim, document

2026-09-19. Module: rtl/i2c_controller.sv

Decision: hardware ignores `start_i` unless IDLE (existing behavior, now
intentional). The tb checker reports a violation during sim. Header comment
states it.

Deferred: a sticky violation-status bit readable by software, to land with the
register interface whenever that exists. Noted here so the deferral is a
decision and not an omission.

## D3: audit every signal that crosses the tick boundary

2026-09-19. Module: rtl/i2c_controller.sv

After finding the start_i drop, swept the rest of the module for the same
pattern. Results, all to be stated in the header:

- `done_o`: asserted in tick domain, so it is 250 fast-clocks wide. Slow to
  fast crossing, always seen. Fine.
- `ack_err_o`: sticky until reset. Intentional: a latched error beats one you
  can miss. Caller clears by reset (or later via regif, see D2).
- `dev_addr_i` / `reg_addr_i` / `data_i`: read combinationally during the
  transaction, so caller must hold them stable until `done_o`. Part of the
  contract, checker can enforce address stability too if it ever bites.

## D4: tristate lives at the pad wrapper, core uses oe/in ports

2026-09-19. Modules: rtl/i2c_controller.sv, future de10nano_top.sv

Decision: i2c_controller loses its `inout` ports. Core interface becomes plain
signals: `sda_i`, `sda_oe_o`, `scl_i`, `scl_oe_o`. The only `inout` in the
design lives in the board-level wrapper (de10nano_top), which does the pin
arithmetic.

Rationale: three reasons, in order of how much they hurt this week.
1. Testability. Verilator is 2-state; a top-level inout degenerates to an
   input pin and the internal tristate assign is not observable from C++. My
   "bus monitor" tb watched a dead pin (see devlog). With oe/in ports any tb
   can drive and observe the core directly.
2. Portability. Pad cells and tristates are technology specific. Core logic
   that never says inout ports to any FPGA or process.
3. Lint hygiene. Tristate resolution rules are a classic source of
   tool-specific weirdness. One wrapper isolates all of it.

## D5: target model and bus resolution in C++, not SystemVerilog

2026-09-19. File: tb/sim_i2c.cpp

Decision: the tb implements the physical layer itself. Wired-AND: a line reads
low if controller oe or target oe is asserted, high otherwise (that high is the
pullup resistor, expressed as logic). Plus a minimal behavioral ADV7513:
watches START, shifts in bits on SCL rising edges, ACKs address 0x39, NACKs
anything else. The NACK case is a required test, not optional: it is the only
positive test of the ack_err path.

Rationale: the target models a real chip that exists on the board, so it is tb
infrastructure, not deliverable RTL. Keeping it in C++ puts bus model, target,
checker and scoreboard in one place next to each other, in the same language
as the rest of the verification code.

## D6: tb rules. A test that cannot fail is not a test

2026-09-19. Applies to everything under tb/

Rules for every harness in the repo, to be collected into docs/verification.md
(not written yet):

1. A timeout is a failure, not an exit condition. The tb records why the loop
   ended; watchdog termination prints FAIL and exits nonzero.
2. Assert positive expectations, not the absence of error flags. Expected
   SCL rising edges per byte is 9 (8 data + ACK). That count alone catches
   truncated-byte bugs.
3. Exit code is the interface. make and CI read exit codes, not prose. FAIL
   with return 0 manufactures false confidence, which is the exact failure
   mode this whole rewrite exists to avoid.

Origin: sim_i2c printed SUCCESS for a transaction that never started, because
the only thing it checked was ack_err_o, which is 0 when nothing happens.

## D7: documentation layout

2026-09-19.

- docs/decisions.md (this file): why. ADR style, append only.
- docs/devlog.md: bug graveyard. Symptom, diagnosis, cause, fix, lesson.
- Module header comments: what a caller must do. Contracts live with the RTL.
- docs/verification.md (planned): methodology, the D6 rules, tb inventory.
- README: short pointer section only, no logs inline.
- Commit messages reference (Dn) and devlog entries, so git log, decisions and
  bugs cross-reference each other.

## D8: tb cycle recipe for the closed-loop I2C bus

2026-09-19. File: tb/sim_i2c.cpp

Context: controller oe outputs + target pull -> resolved lines -> controller sda_i/
scl_i is circular within one cycle. Need a fixed evaluation order.

Decision, per clk_i cycle:
1. pre-edge: resolve both lines from the oe values read at the END of the
   previous cycle, plus the target's current pull. line = low if controller oe OR
   target pulls, high otherwise (the high is the pullup, as logic). Drive
   sda_i/scl_i and test stimulus.
2. clk_i = 1, eval. DUT samples inputs, FSM updates on ticks.
3. clk_i = 0, eval.
4. post-edge: read fresh oe/status, re-resolve, detect edges on the RESOLVED
   bus, step the target, run checker, optional trace.

The one-cycle staleness in step 1 is safe: lines only move on ticks (250
cycles apart), the DUT only samples on ticks, and the target settles its pull
on SCL-falling, ~half an SCL period before the controller samples on SCL-rising.
Everything has ~250 cycles of slack.

## D9: target BFM scope

2026-09-19. File: tb/sim_i2c.cpp

Decision: minimal behavioral ADV7513, write-only. Detects START (SDA falls
while SCL high) and STOP (SDA rises while SCL high), shifts in bits on SCL
rising edges MSB-first, drives ACK (pull low) on the ninth clock when the
address matches, two modes: ACK_ALL for T1, NACK_ADDR for T2. No register
file, no reads, no clock stretching. It models wire behavior the DUT depends
on, nothing more (D5).

## D10: test matrix, and no-abort-on-NACK is the contract

2026-09-19. Module: rtl/i2c_controller.sv + tb

Decision: two tests, each with its own reset.
- T1 happy path: write 0x39/reg/data, target ACKs everything. This is the
  test that formally catches B4 (byte 2-3 truncated) and B5 (missing STOP).
- T2 wrong address 0x38: target NACKs byte 1. ack_err_o must set by the end
  of that ACK phase and stay sticky through done_o.

Sub-decision: the controller does NOT abort a transaction on NACK. It completes
all three bytes, generates STOP, and reports via sticky ack_err_o. Real I2C
controllers often abort on address NACK; considered and rejected for now because
the only caller will be the ADV7513 ROM walker, which checks ack_err_o after
each done_o and halts anyway, and the bus ends cleanly STOPped either way. Add
a header contract line stating no-abort behavior. Revisit only if a future
caller needs mid-transaction abort.

## D11: scoreboard = the header contract, executed

2026-09-19. File: tb/sim_i2c.cpp

Every contract line in the i2c_controller header becomes an assertion:
busy within BUSY_LATENCY_MAX of held start; start held until busy (tb bug if
violated); exactly one START; 9 SCL rising edges per byte, 27 total; on-wire
bytes reconstruct bit-exact to {dev,0}/reg/data; ACK low on every ninth
clock; exactly one STOP after the last ACK; done_o observed and its width
measured, not assumed; ack_err_o == 0 in T1; watchdog termination is FAIL.
One fail counter, one path into it, summary printed, exit code = interface.

The derived numbers are the tb's own homework: expected transaction =
1 START + 3*18 byte + 3 STOP + 1 DONE = 59 ticks, so ~15k cycles. Watchdog
is 2x expected (a hang detector), expected-duration is a separate
informational check. Expected != bound; conflating them false-fails healthy
runs by off-by-one.

## D12: verbose bus trace behind -v

2026-09-19. File: tb/sim_i2c.cpp

Decision: argv flag -v prints every resolved-bus edge with cycle number and
START/STOP classification. Default output is the per-check PASS/FAIL list
plus summary. Rationale: devlog entries for B4/B5 need captured evidence
quoted from real runs, and debug printing that lives behind a flag gets
committed instead of deleted.

## D13: commit granularity for the tb rewrite

2026-09-19.

Decision: daily work checkpoints on a wip branch, squash-merged to main at
milestones. Public history stays milestone-only. A checkpoint is allowed to be
RED, because red-for-a-diagnosed-reason (B4/B5 evidence in the output and
commit message) tells the reader something true about the design; the follow-up
fixes the RTL and flips it green. Red-by-accident or red-because-unfinished
never enters main.

## D14: controller/target terminology, main branch

2026-09-20. Repo-wide.

Decision: adopt current I2C-spec terminology. The core module is now
i2c_controller (rtl/i2c_controller.sv, was i2c_master.sv); the modeled
counterpart on the bus is the "target" (was "slave"); identifiers renamed
to match (slave_drive_low -> target_pull_low). Default branch renamed
master -> main.

Rationale: matches the language of the modern spec (NXP UM10204) and of
current datasheets; the repo reads consistently to any reviewer. Pure
rename: lint clean and tb output byte-identical before and after, which
is the required evidence that a terminology refactor changed no behavior.

Note on append-only policy: this file and the devlog had terminology
updated in place rather than keeping stale names inside historical
entries. The entries keep their dates and commit references, and the
rename itself is recorded here, so provenance survives.

Consequence: the board wrapper (de10nano_top) instantiates i2c_controller;
future modules and docs use controller/target from the start.

## D15: storage path is an SPI microSD module on GPIO, not the onboard slot

2026-09-20. Phase 8 architecture.

Context: DE10-Nano manual Table 3-19 shows the microSD socket wired to
HPS_SD_CLK/CMD/DATA[3:0] on pins B8, D14, C13, B6, B11, B9. HPS-dedicated
pins are not reachable from FPGA fabric, so RTL cannot drive the onboard
slot.

Options:
1. SPI-mode microSD module on the GPIO header, driven by fabric RTL.
2. HPS bare-metal SD driver, handed to fabric over the H2F bridge.
3. HPS Linux with assets on a filesystem.

Decision: option 1.

Rationale: fabric-native, so the whole storage path (SPI controller, card
init sequence, container loader) is RTL verified in Verilator against a C++
card model, same closed-loop method as the I2C work (D5, D8). No ARM
dependency, no bootloader story, no bridge arbitration. SPI mode is slow
(~1-10 Mbit/s), which is fine: the workload is bulk asset/code load at boot,
not streaming. Cost: an external module (~$3), a few GPIO pins, 3.3V levels
both sides so no translation needed.

Consequences: the onboard slot stays dark for RTL purposes; if a future use
case wants it, that is an HPS bare-metal project of its own. Pin assignment
for the SPI bus (4-6 wires: SCK, MOSI, MISO, CS, optional detect) is
deferred to Phase 8 and gets the same manual-citation treatment as the HDMI
pins. Container format work (Phase 8) is unaffected by this choice; only the
byte source changes.

Evidence: Table 3-19, cited in docs/references.md.

## D16: monorepo until split triggers; project renamed rv32-apu

2026-09-20. Repo architecture.

Decision 1, repo layout: stay one repo. Components split out only when they
acquire their own users, release cadence, or CI story. Concrete triggers:
- CPU core spins out when it passes an ISA test suite and its tb references
  nothing outside rtl/cpu.
- Toolchain (assembler, packer, png2tex) spins out when a game build uses it
  without touching the FPGA tree.
Splits use git filter-repo so subtree history (including devlog-relevant
commits) travels with the code. Directory discipline until then: rtl/ for
fabric, tools/<name>/ for Python, docs/ stays a single ledger.

Rejected: splitting now into gpu/cpu/compiler/toolchain repos. Boundaries
would be guesses (no container format, no ISA tests, no CPU), the ADR and
devlog ledgers would fracture, and the end-to-end integration story is the
point of the project. The original AI-era repo consumed rv32-toolchain as a
submodule; the symmetry of publishing my own version of it at Phase 10 and
consuming it back is deliberate, not accidental.

Decision 2, name: rv32-apu-tapeout -> rv32-apu. "tapeout" claimed GDSII/
foundry work that does not exist and is not scheduled (the old README
disclaimed it itself). "apu" is true at both ends of the roadmap: a pixel
accelerator today, and once Phase 6 lands, literally an audio+video
processing unit, CPU-directed over the register interface, audio embedded
in HDMI via the ADV7513 I2S pins already reserved in the qsf. GitHub repo
takes the name when the remote is created (none exists yet; this repo is
local-only). README title updated in the same commit as this entry.

## D17: ordered dithering for computed-color scenes, not a global output stage

2026-09-24. Phase 4 rendering. Contract-first: written before the RTL.

Context: the plasma reduces a continuous 25-bit color sum to RGB332 (3/3/2
bits) by keeping the top bits. Eight levels per channel is coarse enough that
smooth gradients poster into visible terraces. The board has no framebuffer to
dither into, so the reduction happens live, per pixel, at scanout.

Options:
1. Ordered (Bayer) dither: add a fixed threshold from a matrix indexed by the
   pixel's low x/y bits, before truncating. Stateless, one add, one constant.
2. Error-diffusion (Floyd-Steinberg): push quantization error to neighbors.
3. Temporal dither: vary the threshold per frame. Grainy, and it interacts with
   whatever dithering the panel itself applies on refresh.
4. One dither stage after the apu_top scene mux, applied to every scene.

Decision: option 1, as a shared primitive that computed-color scenes opt into.
Not option 4.

Rationale: ordered dither is the only option that fits a framebuffer-less
scanout. Option 2 needs the not-yet-computed pixels or a line buffer, which is
the very storage this design exists to avoid. A single apu_pkg function keeps
one source of truth reused by the plasma now and the gradient/raycaster later;
that is what "global" should mean here, not an unconditional filter.

The boundary is the palette. Colorbars emit fixed RGB332 codes (0xFF, 0x1C,
...) that are the known-good bring-up reference and feed the RGB332-to-24-bit
map in de10nano_top unchanged. Dithering them would speckle solid bars and
break the reference, so the dither is opt-in at each scene's own output stage.
The RGB332-to-24-bit bit-replication in de10nano_top is a fixed expansion, not
a quantization, and is left alone.

Consequences:
- The dither index must use the pixel the color belongs to. apu_plasma's color
  comes from the CORDIC, whose result corresponds to x,y fed 18 clocks earlier,
  so the Bayer lookup needs x,y delayed by the same 18, not the live x_i,y_i.
  Same alignment trap as de_o; a wrong index shifts the grain by a line edge.
- The tb measures the effect rather than asserting it: count distinct output
  levels along a monotonic input gradient before and after dithering. Dithering
  must raise the count (break a terrace into more codes) and must leave
  colorbars byte-identical, since they bypass the path. A dither that only
  "looks nicer" is not verified.
- Ordering: moot; see Evaluation (dither not adopted).

Evaluation (2026-09-24): ordered Bayer dither was implemented twice against the
hue-wheel plasma and rejected. At RGB332 (3/3/2) the hue wheel uses ~28 of the
256 codes; dithering turned hard terraces into visible contour bands (measured:
baseline distinct=28 longest-run=514px; dithered distinct=29 longest-run=380px,
i.e. terraces survived and only shifted). The banding is a color-depth limit,
not a quantization-edge problem dither can hide at this depth. Decision: no
dither for computed-color scenes at 3-bit; keep the clean posterized output.
Revisit only if color depth increases or a value-modulation mapping (more codes
via brightness) is adopted instead.

Evidence: the before/after distinct/longest-run measurements above, from
make sim_plasma frame captures. docs/verification.md records the accepted
banding as a known gap.
