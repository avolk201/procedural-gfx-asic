# Deploy: DE10-Nano bring-up and flashing

How this design gets from source to colorbars on a monitor. The night this
was first done is logged in docs/devlog.md ("Bring-up: 2026-09-23"); this
file is the procedure, that file is the story including the wrong turns.

## What you need

- DE10-Nano (Cyclone V SE 5CSEBA6U23I7)
- A Windows or Linux machine. Quartus does not run on macOS.
- Quartus Prime Standard Edition. Pro Edition does not support Cyclone V
  at all; the family is absent from its device picker. Standard needs no
  license for this part.
- mini-USB cable for the port silkscreened USB Blaster (not the HPS USB
  port), an HDMI cable and a monitor, and nothing in the microSD slot.

## Host setup

Install Quartus with Cyclone V device support checked, into a path without
spaces. On immutable Fedora spins (Bazzite, Silverblue) install into $HOME;
the toolchain is self-contained and needs no layered packages.

The onboard programmer enumerates as 09fb:6010 "Altera DE-SoC", not
"USB-Blaster II", and quartus_pgm names the cable "DE-SoC". Linux needs a
udev rule or the device node stays root-only:

    # /etc/udev/rules.d/51-usbblaster.rules
    SUBSYSTEM=="usb", ATTR{idVendor}=="09fb", MODE="0666"

then `sudo udevadm control --reload-rules && sudo udevadm trigger` and
replug. `quartus_pgm -l` should list one cable named "DE-SoC".

Add quartus/bin to PATH by appending, never replacing:
`export PATH="<install>/quartus/bin:$PATH"`. Omitting the trailing `:$PATH`
produces a shell where even `sed` is "command not found"; bash also caches
lookups, so run `hash -r` after fixing it.

## Build

    quartus_sh --flow compile de10nano_top

After any PLL edit, read the create_generated_clock lines in the compile
log: they print the derived VCO. A VCO outside 600-1300 MHz means the PLL
will never lock on silicon while every tool reports success (B15).

Output: output_files/de10nano_top.sof. Volatile; a power cycle erases it.

## Flash

The JTAG chain is SOCVHPS (the HPS ARM) at position 1 and the FPGA at
position 2, so targeting the fabric needs the @2 suffix:

    quartus_pgm -c "DE-SoC" -m jtag -o "p;output_files/de10nano_top.sof@2"

A hand-written .cdf is ignored by this command; @2 is the idiom. Expect
"Configuration succeeded -- 1 device(s) configured".

## Before power-up

- Connect the HDMI monitor first. The ADV7513 latches its power-up state
  against HPD, which the monitor drives; a chip that powered up without a
  monitor will not ACK I2C.
- Keep the microSD out. The factory HPS image can drive the same I2C bus
  and reconfigure the FPGA from the HPS side.

## What good looks like

| LED  | Signal      | Expect                                    |
|------|-------------|-------------------------------------------|
| LED0 | cfg_done    | on, ~340 ms after reset release           |
| LED1 | cfg_error   | off (on means the ADV7513 NACKed a write) |
| LED2 | pll_locked  | on within milliseconds of reset release   |
| LED3 | alive blink | ~1 Hz, one toggle per 30 frames           |

then eight colorbars on the monitor at 640x480@60.

The user LEDs carry no per-LED silkscreen; identify them by behavior.
Reset is KEY0: hold it and everything goes dark, release and watch the
order (lock first, done or error after the 335 ms POR).

## When it misbehaves

- All eight user LEDs faintly lit: the FPGA is unconfigured. That glow is
  the blank state, not a fault. Flash again; the .sof did not survive the
  power cycle.
- LED1 on: ADV7513 NACKed. The monitor was not cabled at power-up, or the
  HPS is fighting the bus. Power cycle with the monitor connected, SD out.
- LED2 never on: PLL did not lock. Read the derived VCO out of the compile
  log (B15).
- LEDs good, monitor says no signal: the design is fine and the display may
  simply refuse 640x480@60, a monitor timing rather than a TV one. Try a
  PC monitor before suspecting RTL.
- quartus_pgm sees no cable: udev rule, wrong USB port, or charge-only
  cable, in that order of likelihood.

## Persistence (not implemented yet)

The .sof lives in FPGA SRAM. Permanent boot needs a .jic for the QSPI or
an .rbf the HPS loads from SD; neither exists in this repo yet.
