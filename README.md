# rv32-apu

Framebuffer-less procedural graphics accelerator for an RV32IMAC SoC.
Pixels are computed during active scanout instead of stored in SRAM.

Status, 2026-09-23: phases 1 and 2 are done. VGA timing, SMPTE colorbars
and the ADV7513 HDMI config walker are verified in Verilator, and the whole
chain has run on real hardware: colorbars on a monitor off a DE10-Nano.
There is no RV32 core in this repo yet; that is phase 3 of the plan below.

<img src="docs/frame.png" alt="Eight vertical SMPTE colorbars, white through black, rendered at 640x480" width="640">

*Simulated output: eight bars at 640x480@60, captured from Verilator to PPM
and converted to PNG (`make sim`).*

<img src="docs/First-Bring-up.jpeg" alt="A DE10-Nano board held in front of a TV that displays the same eight colorbars" width="640">

*The same bars from silicon, first bring-up on 2026-09-23: DE10-Nano to TV
through the onboard ADV7513. Phone photo, displayed upscaled to match the
render above.*

## Quick start

    make lint_top    zero-warning lint of the full top level
    make sim         pixel pipeline, measured timing, one-frame capture
    make sim_i2c     I2C controller against a C++ ADV7513 model, 21 checks
    make sim_config  config walker closed loop, 7 checks

Board bring-up, flashing and the LED debug dashboard:
[docs/deploy.md](docs/deploy.md).

## Where this is going

1. Math core: pipelined CORDIC against a Python golden model.
2. Real scenes: gradients and plasma, then a DDA raycaster with textures.
3. The namesake: own RV32 core and assembler, memory-mapped scene registers.
4. Storage: SPI SD card with a flat container format, the cartridge.
5. Games: an interactive raycaster demo, then small original games.

Every phase ships a contract doc, a golden model and a self-checking
testbench that has been seen fail at least once. Nothing lands on vibes.

## Docs

Design decisions: [docs/decisions.md](docs/decisions.md).
Bug graveyard: [docs/devlog.md](docs/devlog.md).
Spec references: [docs/references.md](docs/references.md).
Verification methodology and harness inventory: [docs/verification.md](docs/verification.md).
Board bring-up and flashing: [docs/deploy.md](docs/deploy.md).

## License

MIT. See [LICENSE](LICENSE).
