# procedural-gfx-fpga

[![CI](https://img.shields.io/github/actions/workflow/status/avolk201/procedural-gfx-fpga/ci.yml?branch=main)](https://github.com/avolk201/procedural-gfx-fpga/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Framebuffer-less procedural graphics accelerator for a future two-hart RV32I_Zicsr SoC (docs/cpu-contract.md).
Pixels are computed during active scanout instead of stored in SRAM.

Status, 2026-09-25: phases 1 through 3 are done and phase 4 has its first
scene. VGA timing, SMPTE colorbars and the ADV7513 HDMI config walker are
verified in Verilator, and the whole chain has run on real hardware: colorbars
on a monitor off a DE10-Nano, 2026-09-23. The math core, a pipelined CORDIC,
is cross-checked against a Python golden model for all 65536 phases and now
drives a three-grating plasma scene; the current build (D18 DE alignment)
closed timing at worst setup slack +14.012 ns, Slow 1100mV 100C, and ran on
the board 2026-09-25. There is still no RV32 core.

### Proof table

| Claim | Command | Numbers | Artifact |
|---|---|---|---|
| Zero-warning lint, all RTL | `make lint_top` | Verilator 5.050, -Wall, clean | console |
| VGA timing + pixel pipeline | `make sim` | HSync 96 px, VSync 2 lines, frame 420,000 cycles, DE during HSync 0, capture 307,200 px | docs/frame.png, sha256 124deeaa... |
| CORDIC math core | `python3 tb/cordic_golden.py`, `make sim_cordic` | bit-exact vs model over all 65,536 phases; max \|err\| vs libm 3.172e-05; 24 + 14 checks | console |
| Plasma scene, D18 latency | `make sim_plasma` | frame re-captured 2026-09-28 byte-identical to the B18 control, sha256 de1ba729... | docs/plasma.gif, sha256 5633f894... |
| I2C controller | `make sim_i2c` | 21 checks, wire bytes {72,41,00}/{70,41,00} bit-exact, 14,998 cycles/transaction | console |
| ADV7513 config walker | `make sim_config` | 7 checks, halted-on-error path included | console |
| Timing closure (D18 build, 9f5dc7b) | `quartus_sh --flow compile` on Quartus 25.1 | worst setup +14.012 / hold +0.168 / recovery +16.599 / removal +0.698 / mpw +1.241 ns, TNS 0.000, Slow 1100mV 100C; divclk Fmax 72.79 MHz; 2,067/41,910 ALMs, 3/112 DSP, 0 M10K, 1/6 PLL | sta.rpt |
| Runs on hardware | `quartus_pgm -c "DE-SoC" -m jtag -o "p;output_files/de10nano_top.sof@2"` | colorbars 2026-09-23; plasma on OLED 2026-09-25, .sof 0x00E4BE7C, unchanged after D18 | v0.1.0 photo; docs/plasma-bring-up.mp4, sha256 995ec06c... |
| CPU tooling, no core | `python3 tools/tests/test_rv32asm.py`, `python3 tools/tests/test_rv32enc.py` | 101 + 246 checks vs spec-derived vectors (unpriv vol. 20250508 ch. 35) | console |

Not done: no RV32 core (contract and ladder in docs/cpu-contract.md), no
interactive demo, no I2S, no SD.

Toolchain (what results are reproduced with):

- Verilator 5.050 for every `make sim*` and `make lint*` target. The CI runner
  uses Ubuntu's apt Verilator, so its exact patch may differ; the numbers quoted
  in the README and docs are measured on 5.050. The sim flow is Verilator-only:
  no Icarus Verilog or Yosys step exists in this repo.
- python3 for the CORDIC golden model (`tb/cordic_golden.py`), which the C++
  testbench reads as its oracle, and for the RV32 assembler and its shared
  encoding tables (`tools/`, with their own golden suites).
- Quartus Prime Standard 25.1 for synthesis, Linux or Windows only. Quartus Pro
  drops the Cyclone V family, so it cannot build this design; Standard needs no
  license for this part.
- A Terasic DE10-Nano (Cyclone V SoC, 5CSEBA6U23I7) to run it on hardware.
  Flashing is optional and covered in [docs/deploy.md](docs/deploy.md).

Reproducing the simulations needs only Verilator and python3: `make sim`,
`sim_i2c`, `sim_config`, `sim_cordic` and `sim_plasma` all run without Quartus
or the board.

## Architecture

<img src="docs/block_diagram.png" alt="Block diagram: board oscillator at 50 MHz into a clock generator whose PLL emits a 25.175 MHz pixel clock, then a timing and prefetch generator feeding a plasma scene built from three parallel CORDIC gratings, through an output mux and pads to the ADV7513 HDMI transmitter and monitor; a config walker on the 50 MHz domain drives an I2C master into the transmitter; a planned 50 MHz CPU path shows an RV32I Zicsr core with hart0 I/D RAM, scene registers crossing by write-then-toggle, an SD loader and a host-side assembler" width="849">

*Solid blue is implemented fabric, dashed is planned per
[docs/cpu-contract.md](docs/cpu-contract.md), green is host tooling. The scene
consumes the prefetch window DEPTH clocks ahead of the beam (plasma 19,
colorbars 1) and its de_o lands on the active window; syncs run from the
timing block to the pads without passing through pixel logic. No framebuffer
exists: a pixel lives for one clock, and scene state is x, y and a frame
counter. Budget: 307,200 active of 420,000 pixel clocks per frame at
25.175 MHz, 18.432 Mpx/s, and the three parallel CORDICs retire one sample
per clock.*

Diagram source is [docs/block_diagram.tex](docs/block_diagram.tex), a
standalone TikZ figure; render it with `tectonic docs/block_diagram.tex` then
`pdftoppm -png -r 200 -singlefile docs/block_diagram.pdf docs/block_diagram`.

## How to read this repo

Start with the status line and the two images below: that is the whole result,
verified in simulation and on the board. For the verification detail, read
[docs/verification.md](docs/verification.md); it lists what each make target
checks and the rules the harnesses follow. For how bugs are found and closed,
read [docs/devlog.md](docs/devlog.md), entries B13 through B19.

<img src="docs/plasma.gif" alt="A boiling plasma pattern in saturated red, green and blue hues, computed per pixel at 640x480" width="640">

*Simulated output: the plasma scene, 60 frames at 640x480 captured from
Verilator (`./obj_dir/sim_plasma +frame=1..60`) and encoded at 20 fps against
a generated 256-color palette with dithering off. The scene uses 29 of the 256
RGB332 codes; all 60 GIF frames are byte-identical to the captures. One frame:
`make sim_plasma` (writes `sim/plasma_frame.ppm`).*

<img src="docs/frame.png" alt="Eight vertical SMPTE colorbars, white through black, rendered at 640x480" width="640">

*Simulated output: eight bars at 640x480@60, captured from Verilator to PPM
and converted to PNG (`make sim`). The known-good bring-up reference.*

First bring-up on silicon, 2026-09-23: the same bars on a TV off the
DE10-Nano, through the onboard ADV7513. The phone photo is in the
[v0.1.0 release](https://github.com/avolk201/procedural-gfx-fpga/releases/tag/v0.1.0).

Plasma on the OLED, 2026-09-25: [docs/plasma-bring-up.mp4](docs/plasma-bring-up.mp4),
phone video re-encoded to 640x360 H.264 at 30 fps, metadata stripped.

## Quick start

    make lint_top    zero-warning lint of the full top level
    make sim         pixel pipeline, measured timing, one-frame capture
    make sim_i2c     I2C controller against a C++ ADV7513 model, 21 checks
    make sim_config  config walker closed loop, 7 checks
    make sim_cordic  pipelined CORDIC vs the golden model, all 65536 phases
    make sim_plasma  plasma scene look check, one frame to sim/plasma_frame.ppm

Board bring-up, flashing and the LED debug dashboard:
[docs/deploy.md](docs/deploy.md).

## Evidence and provenance

| Artifact | sha256 | Size (bytes) | Origin |
|---|---|---|---|
| docs/frame.png | 124deeaa3182627197bb532f89333020d5d2192bcecb2faf1958bef5357fccc3 | 5,007 | `make sim` capture, converted with `python3 tb/ppm2png.py` |
| docs/plasma.gif | 5633f894fbd061a484360c5da1cdfe8dfcd3fecccd6b525abaded5128fc6e5f0 | 1,329,888 | 60 Verilator captures (`+frame=1..60`), palette-encoded 20 fps; every frame byte-identical on round-trip (v0.2.0 notes) |
| docs/plasma-bring-up.mp4 | 995ec06c98bd33a7c509af5f57c5f3fe7c85f9d64badaa1a0880501b8da226c9 | 588,044 | phone video, re-encoded 640x360 H.264 30 fps, metadata stripped |
| sim/plasma_frame.ppm | de1ba72984e9b53ca14021e719c7b1a81c3d6a4b5813e31659753a3fa8e775b7 | 921,615 | `make sim_plasma` one-frame capture; the B18 control hash, re-run 2026-09-28 and equal |

The media metadata was stripped on purpose (privacy), which also removes
capture time and device. The hashes above plus the dated devlog entries are
what carry provenance; the v0.1.0 phone photo lives in the release assets,
its EXIF stripped too.

What was not measured, stated as absence:
- Monitor model (2026-09-23) and OLED model (2026-09-25) are unrecorded.
- No oscilloscope capture of pixel clock or syncs; timing evidence is the
  counter measurements in `make sim` plus a picture on a live display.
- No logic-analyzer capture of the physical I2C bus; wire-level claims come
  from sim_i2c's closed-loop model, and the hardware evidence is the
  ADV7513 ACKing all 13 writes (devlog bring-up, 2026-09-23).
- No ADV7513 register readback; the walker is write-only by design.
- Endurance unmeasured; longest continuous run is not logged.
- Hot-plug after configuration untested; only the power-up HPD ordering
  claim is established (B15).

## Where this is going

1. Math core: pipelined CORDIC against a Python golden model. Done and
   cross-checked ([docs/cordic.md](docs/cordic.md) has the convergence and
   bit-width argument); it now drives the plasma scene at the top.
2. Real scenes: the plasma is in; next is a DDA raycaster with textures.
3. The namesake: own RV32 core and assembler, memory-mapped scene registers.
   The assembler, its encoding tables and their golden suites are in
   (`tools/`); the two-hart core is next, contract first
   ([docs/cpu-contract.md](docs/cpu-contract.md)).
4. Storage: SPI SD card with a flat container format, the cartridge.
5. Games: an interactive raycaster demo, then small original games.

Every phase ships a contract doc, a golden model and a self-checking
testbench that has been seen fail at least once. Nothing lands on vibes.

## Docs

Design decisions: [docs/decisions.md](docs/decisions.md).
Bug graveyard: [docs/devlog.md](docs/devlog.md).
Spec references: [docs/references.md](docs/references.md).
Verification methodology and harness inventory: [docs/verification.md](docs/verification.md).
CORDIC math core: [docs/cordic.md](docs/cordic.md).
Board bring-up and flashing: [docs/deploy.md](docs/deploy.md).
Rendered engineering notes and sha256-pinned build artifacts (GitHub Pages):
[avolk201.github.io/procedural-gfx-fpga](https://avolk201.github.io/procedural-gfx-fpga/).

## License

MIT. See [LICENSE](LICENSE).
