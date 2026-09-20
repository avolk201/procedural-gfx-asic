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
2. Assert positive expectations, not just absence of error flags. Expected
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
