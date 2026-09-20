# Reference documents

Source specs this design depends on. PDFs are copyrighted and NOT committed;
they live locally in docs/specs/ (gitignored). Each entry lists the exact
revision used and the sections the RTL/tb relies on, so any claim in the code
can be traced to a page.

## I2C-bus specification (NXP UM10204)
- Where: nxp.com, document UM10204 "The I2C-bus specification"
- Revision / accessed: (fill in)
- Relied on: START/STOP definitions (SDA transitions while SCL high), data
  validity rule (SDA stable while SCL high), 9th-clock ACK/NACK behavior,
  open-drain/wired-AND electrical model, controller-target terminology.
- Used by: rtl/i2c_controller.sv contract header, tb/sim_i2c.cpp BFM rules.

## VESA Display Monitor Timing (DMT) standard
- Where: vesa.org (free download of the DMT spec)
- Revision / accessed: (fill in)
- Relied on: 640x480@60Hz row: 25.175 MHz pixel clock, H 16/96/48, V 10/2/33
  porches/syncs, negative sync polarity.
- Used by: rtl/apu_pkg.sv constants, apu_vga_timing.sv.

## Terasic DE10-Nano user manual + schematic
- Where: terasic.com.tw, DE10-Nano product page (manual and CD/schematic zip)
- Revision / accessed: (fill in)
- Relied on: Table 3-13 HDMI pin assignments (transcribed into
  constraints/de10nano_pinout.qsf 2026-09-20), Table 3-19 microSD socket
  (HPS-only pins, drove decision D15: SPI module on GPIO instead), FPGA pin
  tables (50 MHz clock, HDMI I2C, HDMI TX bus), ADV7513
  connection details incl. shared HPS I2C caveat, pushbutton/LED pins.
- Used by: the DE10-Nano pinout constraints and de10nano_top.sv (both
  drafted locally, untracked until verified against this manual before
  the first Quartus run).

## Analog Devices ADV7513 datasheet
- Where: analog.com, ADV7513 product page
- Revision / accessed: (fill in)
- Relied on: I2C device address (0x39), power-up register sequence for
  640x480 RGB input, register map for the planned config walker.
- Used by: tb constants (DEV_ADDR_OK), future rtl/adv7513_config.sv.
