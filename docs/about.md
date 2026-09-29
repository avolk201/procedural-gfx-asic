---
layout: default
title: About
permalink: /about/
---

This site archives technical post-mortems for the [procedural-gfx-fpga](https://github.com/avolk201/procedural-gfx-fpga) repository.

It documents architectural decisions, static timing analysis (STA), and verification methodology for a framebuffer-less graphics pipeline, and for an RV32I_Zicsr core in progress (contract, assembler, and ISS done; core RTL not started), targeting the Terasic DE10-Nano (Cyclone V 5CSEBA6U23I7).

The focus is strictly on RTL design, SystemVerilog verification against golden models, and hardware bring-up.

## Evidentiary Standard

Entries on this site are not theoretical summaries. Every architectural claim, timing closure result, and bug fix is tied to:

1. A specific commit hash in the repository.
2. Exact shell commands used to reproduce the simulation or synthesis result.
3. Raw output data, such as Quartus STA reports, Verilator logs, or SHA-256 hashes of frame captures.

## Toolchain

The designs and verification environments documented here rely on the following tools:

- **RTL and Simulation:** SystemVerilog, Verilator 5.050
- **Synthesis and STA:** Quartus Prime Standard 25.1
- **Golden Models and Tooling:** Python3, C++
- **Target Hardware:** Terasic DE10-Nano (Cyclone V SoC)

## Author

Alana Volkov  
Penultimate-year engineering student, University of Sydney.  
Targeting FPGA verification and RTL design roles.

- [GitHub](https://github.com/avolk201)
- [LinkedIn](https://www.linkedin.com/in/alana-volkov-1054792a8)
- [Repository](https://github.com/avolk201/procedural-gfx-fpga)
