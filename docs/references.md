# Reference documents

Source specs this design depends on. PDFs are copyrighted and NOT committed;
they live locally in docs/specs/ (gitignored). Each entry lists the exact
revision used and the sections the RTL/tb relies on, so any claim in the code
can be traced to a page.

## I2C-bus specification (NXP UM10204)
- Where: nxp.com, document UM10204 "The I2C-bus specification"
- Revision: Rev. 7.0, 1 October 2021. Local copy: docs/specs/12c-docs.pdf
  (revision read from the title page, 2026-09-25).
- Relied on: START/STOP definitions (SDA transitions while SCL high), data
  validity rule (SDA stable while SCL high), 9th-clock ACK/NACK behavior,
  open-drain/wired-AND electrical model, controller-target terminology.
- Used by: rtl/i2c_controller.sv contract header, tb/sim_i2c.cpp BFM rules.

## VESA Display Monitor Timing (DMT) standard
- Where: vesa.org (free download of the DMT spec)
- Revision / accessed: VESA and Industry Standards and Guidelines for
  Computer Display Monitor Timing (DMT), Version 1.0, Rev. 13 (title page,
  downloaded 2026-09-25). Local copy: docs/specs/VESA-DMT-1.0-rev13.pdf.
- Relied on: the "640 x 480 @ 60Hz" timing entry: pixel clock 25.175 MHz
  +/-0.5%, 59.940 Hz, H total 800, H sync start 656, H sync 96, V total
  525, V sync start 490, V sync 2, both sync polarities negative. Rev 13
  splits blanking into borders plus porches (H: right border 8, front porch
  8, back porch 40, left border 8; V: bottom border 8, front porch 2, back
  porch 25, top border 8); apu_pkg's constants are the lumped equivalents
  (H_FP 16 = 8+8, H_BP 48 = 40+8, V_FP 10 = 8+2, V_BP 33 = 25+8), and the
  sync positions are identical at the signal level.
- Used by: rtl/apu_pkg.sv constants, apu_vga_timing.sv, D18's H_BP=48 depth
  bound.
- Relied on: 640x480@60Hz row: 25.175 MHz pixel clock, H 16/96/48, V 10/2/33
  porches/syncs, negative sync polarity.
- Used by: rtl/apu_pkg.sv constants, apu_vga_timing.sv.

## Terasic DE10-Nano user manual + schematic
- Where: terasic.com.tw, DE10-Nano product page (manual and CD/schematic zip)
- Revision: User Manual title page dated February 1, 2018; local copy
  docs/specs/DE10-Nano-Manual.pdf (date read from the PDF, 2026-09-25).
  Schematic: de10-nano-schematic-711128.pdf (local).
- Relied on: Table 3-13 HDMI pin assignments (transcribed into
  constraints/de10nano_pinout.qsf 2026-09-20), Table 3-19 microSD socket
  (HPS-only pins, drove decision D15: SPI module on GPIO instead), FPGA pin
  tables (50 MHz clock, HDMI I2C, HDMI TX bus), ADV7513
  connection details incl. shared HPS I2C caveat, pushbutton/LED pins.
- Used by: the DE10-Nano pinout constraints and de10nano_top.sv (both
  drafted locally, untracked until verified against this manual before
  the first Quartus run).

## Analog Devices ADV7513 Programming Guide + Hardware User's Guide
- Where: analog.com ADV7513 product page; PDFs kept in docs/specs/ (local)
- Revision / accessed: Programming Guide Rev B, Hardware User's Guide Rev 0;
  accessed 2026-09-23
- Relied on: sec 3 Quick Start + Table 14 (fixed registers after power-up),
  Table 16 (RGB 4:4:4 pin map: D[23:16]=R), Table 4 (HDMI/DVI select),
  sec 4.1 (200 ms wait after supplies; PD/AD strap selects 0x72/0x7A),
  sec 4.7 (power down bit 0x41[6]), sec 4.3.6 (DE/HS/VS generation: the
  separate-syncs method passes the provided timing through when 0x17[0] DE
  generator and 0x41[1] sync adjustment are off; basis for B17/D18).
- Used by: rtl/adv7513_config.sv ROM (per-entry citations) and its tb golden
  table, POR length in rtl/de10nano_top.sv, tb constants (DEV_ADDR_OK).
- RESOLVED via board schematic (de10-nano-schematic-711128.pdf, local):
  U34 pin 22 (PD/AD) strapped low, silkscreen note "Default: I2C Address
  0x72/0x73" = 7-bit 0x39. Also: HDMI_HPD net runs to connector pin 19
  (monitor-driven, R249 10K), so the ADV7513 will not power up without a
  cabled monitor; and the FPGA ballmap independently confirms FPGA_CLK1_50
  on V11 and HDMI_TX_CLK on AG5.

## RISC-V ISA Manual (riscv-isa-manual)
- Where: github.com/riscv/riscv-isa-manual, release tag 20250508
- Revision: Version 20250508; both title pages read "This document is in
  ratified state" (read 2026-09-25). Repo license CC-BY-4.0 (GitHub license
  metadata, not printed on the read pages). Local copies:
  docs/specs/riscv-unprivileged-20250508.pdf (727 pp) and
  docs/specs/riscv-privileged-20250508.pdf (221 pp). A combined snapshot,
  riscv-spec-20260924-intermediate.pdf ("Intermediate Release"), is also
  local and non-normative.
- Relied on: RV32I base encodings (unprivileged vol., ch. 2.1) for the
  assembler golden tests; mhartid and machine-mode reset behavior
  (privileged vol.) for the dual-hart contract.
- Used by: docs/cpu-contract.md; the planned assembler (tools/) and rv32 tbs.

## Intel Cyclone V Device Handbook
- Where: intel.com docs portal, literature number CV-5V2, "Cyclone V Device
  Handbook, Volume 1: Device Interfaces and Integration", 2023.10.18. Intel
  consolidated the former two-volume split; a separate volume 2 is no longer
  published (owner checked online 2026-09-25), and the memory chapter this
  repo needs is in this file. Local copy: docs/specs/Cyclone-Handbook.pdf.
- Relied on: ch. 2 "Embedded Memory Blocks in Cyclone V Devices":
  "Guideline: Consider Power-Up State and Memory Initialization" (2-7,
  Table 2-4: Quartus initializes Cyclone V RAM cells to zero by default;
  every memory block supports .mif initialization), "Guideline: Implement
  External Conflict Resolution" (2-3: true dual-port mode has no internal
  write-conflict circuitry), the read-during-write guidelines (2-3 onward:
  registered input and output paths, same-port and mixed-port behavior),
  M10K configurations incl. true dual-port (2-9).
- Used by: docs/cpu-contract.md sections 4-6 (two-stage core rationale,
  per-hart TDP RAMs, boot initialization, the Phase 8 loader arbiter as
  external conflict resolution).
