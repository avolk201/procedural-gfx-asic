# rv32-apu-tapeout

Framebuffer-less procedural graphics accelerator for an RV32IMAC SoC.
Pixels are computed during active scanout instead of stored in SRAM.

Work in progress. VGA timing and SMPTE colorbars verified in Verilator:

![verilator sim output](docs/frame.png)