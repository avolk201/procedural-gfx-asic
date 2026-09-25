# RV32 SoC contract

DRAFT 2026-09-25. Agent-written skeleton for the owner to rewrite; nothing
here is decided until the OPEN markers are resolved. Grounded only in facts
already measured or cited in this repo. Per the repo method (contract doc,
then golden model, then a self-checking tb seen to fail once, then RTL),
this document must be complete before any rtl/rv32* file exists.

## 1. Scope

RV32I core, simple bus, register interface (regif) for the pixel pipeline,
boot RAM. M extension after I passes; A and C stay roadmap-name-only until
something needs them (roadmap Phase 9 rule: do not build speculatively).

## 2. Clock and reset domains (measured facts)

- clk_50m: system/input clock, 20 ns period (constraints/timing.sdc).
- clk_pix: 25.175 MHz fractional-PLL output, 39.718 ns period; divclk Fmax
  on the D18 build is 72.79 MHz (sta.rpt, 2026-09-25), so a CPU at
  25.175 MHz or 50 MHz has measured headroom on this fabric.
- CPU clock domain: OPEN. Same 50 MHz as sys (fewest crossings) or a second
  PLL output. Any new domain adds a clock group and its own reset source.
- Reset: POR is 2^24 cycles at 50 MHz (335 ms, de10nano_top.sv:18-34).
  Known gap (B16): the 50 MHz to pixel reset assertion is unmeasured by STA
  because set_clock_groups ignores recovery/removal between groups. A CPU
  domain must not inherit that gap: OPEN, pixel-domain reset source vs
  targeted constraints.
- CPU reset release must come after boot RAM initialization (section 5).

## 3. Crossing rules

- Every crossing: two-flop synchronizer minimum, with Quartus
  SYNCHRONIZER_IDENTIFICATION assignments so report_metastability computes
  MTBF (done 2026-09-25: the specified pixel-to-50 MHz chain measures
  > 1e9 years worst-case; the reset crossing is detected but not
  calculated, B16). The syncthreads attribute is Synplify's; Quartus
  ignores it.
- Scene control registers written by the CPU live in the pixel domain or
  cross via handshake; camera/scene inputs are sampled at SOF by the scenes
  (apu_plasma.sv frame counters), so the regif may double-buffer freely
  between SOFs.
- Scene pipeline depth bound: DEPTH <= H_BP = 48 (D18). Any CPU-fed per-
  pixel parameter must respect the same alignment rule: values are consumed
  through the prefetch window, not the beam window.

## 4. Memory map (first draft, all addresses OPEN)

| Region | Size | Backing | Notes |
|---|---|---|---|
| 0x0000_0000 code+data | TBD | M10K | single RAM to start; Harvard split only if a real need appears |
| regif | 16-64 B | fabric registers | scene select, pipeline enable, camera x/y/angle, frame counter (read), status |

Budget (measured): M10K total 5,662,720 bits = 707,840 bytes; the plasma
build uses 0 bits of it, 2,058 of 41,910 ALMs (5%), 3 of 112 DSP blocks.
The running budget table (roadmap Phase 8 note) starts here: code+data+
stack+textures must fit 707,840 bytes with the scene ROMs.

## 5. Boot and RAM initialization

M10K contents at power-up are not a documented guarantee; 2-state
simulation zero-fills and hides the difference (verification.md known gap:
no four-state sim). Contract: the CPU comes out of reset only after every
byte of its RAM holds defined content. Paths:
1. Bring-up: compile-time RAM init (.hex/.mif through the qsf), reset
   release immediate. Simplest; ships with the first core tb.
2. Cartridge (Phase 8): container loader writes RAM, then releases CPU
   reset; loader-holds-CPU-in-reset is a checkable claim in the loader tb.

## 6. Bus

OPEN: simple valid/ready handshake (fewest signals, easiest tb) vs
wishbone-class (D16 mentions "regif wishbone/simple bus"). Whatever is
chosen: single master (CPU), no burst, no pipelining, byte/half/word
access widths defined here, and the golden model implements the same
handshake so the tb scoreboard is the contract executed (D11 pattern).

## 7. Verification ladder (order is mandatory)

1. This contract, OPEN markers resolved.
2. Assembler (tools/, Python) with golden tests against hand-encoded
   instructions (roadmap Phase 9: this unblocks the CPU tb).
3. Instruction-level golden model (Python ISS or instruction-by-instruction
   expected state) covering every RV32I instruction the assembler emits.
4. Self-checking tb: ISA sweep from assembler output, each check seen to
   fail once against a deliberately broken core (rule 4), IPC measured on a
   kernel loop.
5. RTL, single-cycle or 2-stage to start (roadmap), lint -Wall clean.
6. Integration tb: CPU writes scene-select, frame renders differently;
   camera registers move the image; SOF-sampling claim measured.

## 8. OPEN decisions (owner, before step 2)

- CPU clock domain and frequency.
- Reset architecture for the new domain (closes or inherits the B16 gap).
- Bus protocol.
- Address map and regif register definitions.
- Assembler syntax and directive set.
- RAM init mechanism for bring-up (qsf .hex vs loader stub).
- Module naming: keep apu_* (add rv32_* alongside) or do the rename sweep
  first, while the tree is still small.
