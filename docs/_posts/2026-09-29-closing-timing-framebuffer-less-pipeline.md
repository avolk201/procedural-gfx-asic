---
layout: default
title: "Closing Timing on a Framebuffer-less Pipeline at the Slow 100C Corner"
date: 2026-09-29
description: "Timing closure notes for a framebuffer-less VGA/HDMI pipeline on Cyclone V, including prefetch alignment, PLL clock-group constraints, and STA results."
---

This post records the changes and evidence for the D18 build of the framebuffer-less graphics pipeline. The design computes pixels during active scanout. It does not use a framebuffer or block RAM. The pixel clock is 25.175 MHz for 640x480@60.

## Constraint

The pixel pipeline must produce active video inside the VESA active window. The scene logic runs ahead of the beam by a prefetch window. If `de_o` from the scene is not aligned to the timing generator, the active window shifts or the display rejects the frame.

## Changes

### 1. Back-porch prefetch alignment

The scene `de_o` signal is now aligned to the VESA active window. This change is recorded in the devlog as the D18 alignment fix.

The relevant simulation target is:

```sh
make sim_plasma
```

The D18 frame capture was re-run and compared against the earlier B18 control hash. The captures are byte-identical.

### 2. PLL-domain clock groups

The constraint set now declares asynchronous clock groups for PLL-domain crossings and removes the dead `hdmi_tx_int` pin. This corresponds to devlog entry B15.

The relevant constraint files are under:

```text
constraints/
de10nano_top.qsf
```

### 3. Reset synchronizer chain

The `u_sync_rst_pix` chain is specified for MTBF, and the Synplify-origin
`syncthreads` attribute, which Quartus never implemented, was removed from
both files. This reduces reliance on tool defaults and makes the reset path
explicit.

The 2026-09-29 report_metastability run names both specified chains
(tgl_sync[1] and sync_reset:u_sync_rst_pix|d[1]) and computes both:
worst-case MTBF 1e9 years, fraction of chains uncalculated 0.000, worst-case
available settling 17.761 ns (docs/artifacts/d18/metastability.rpt). The B16
state, MTBF not calculated, is closed by measurement rather than by
construction.

### 4. Concurrent assertions

Five concurrent assertions now run inside the design: hsync and vsync pulse
width via monitor counters, DE never active during hsync low, SCL low
half-period equal to CLK_DIV, and SDA stable while SCL high outside START
and STOP. Each was seen red under its own design mutation before landing.
Sequence-repetition properties ([*96]) were tried first and rejected with
measurements: Verilator 5.050 parses them but expands to a 32.4 MB C++
translation unit that did not compile in seven minutes, and ##1 requires
--timing. Edge functions ($rose, $fell, $past) were rejected next: Verilator
accepts them, Quartus synthesis does not (B20). The landed form uses explicit
delay registers and boolean antecedents, so both tools check the same
property.

Price, measured on the 2026-09-29 compile: divclk Fmax 72.79 to 64.1 MHz and
worst setup +14.012 to +13.868 ns, from the monitor counters in the pixel
domain. The margin over the 25.175 MHz beam clock is still 2.5x.

## Evidence

Synthesis and timing analysis were performed with Quartus Prime Standard 25.1.

Command:

```sh
quartus_sh --flow compile de10nano_top
```

STA results for the D18 build, the build flashed to hardware as .sof
0x00E4BE7C, Slow 1100mV 100C corner:

| Parameter | Result |
|---|---:|
| Worst setup slack | +14.012 ns |
| Worst hold slack | +0.168 ns |
| Recovery | +16.599 ns |
| Removal | +0.698 ns |
| Minimum pulse width | +1.241 ns |
| TNS | 0.000 ns |
| divclk Fmax | 72.79 MHz |
| ALMs | 2,067 / 41,910 |
| DSP blocks | 3 / 112 |
| M10K | 0 |
| PLL | 1 / 6 |

STA results for the 2026-09-29 compile at HEAD with the assertion blocks,
same corner, not yet flashed:

| Parameter | Result |
|---|---:|
| Worst setup slack | +13.868 ns (clk_50m), +24.117 ns (divclk) |
| Worst hold slack | +0.232 ns (divclk), +0.365 ns (clk_50m) |
| Recovery | +15.994 ns (clk_50m), +36.380 ns (divclk) |
| Removal | +0.729 ns (clk_50m), +1.060 ns (divclk) |
| Minimum pulse width | +9.171 ns (clk_50m), +19.112 ns (divclk) |
| TNS | 0.000 ns |
| divclk Fmax | 64.1 MHz |
| clk_50m Fmax | 163.08 MHz |
| ALMs | 2,068 / 41,910 |
| DSP blocks | 3 / 112 |
| M10K | 0 |
| PLL | 1 / 6 |

At the Slow 1100mV -40C corner the tighter pair is setup +13.756 ns and hold
+0.167 ns. Reports: docs/artifacts/d18/sta.rpt and
docs/artifacts/d18/fit.summary, sha256-pinned in
docs/artifacts/d18/sha256sums.txt. A report_cdc attempt is archived beside
them: the command does not exist in Quartus Prime Standard 25.1.

Simulation evidence:

```sh
make sim
make sim_plasma
```

`make sim` checks HSync width, VSync width, frame length, and DE behaviour,
including the DE-during-HSync overlap count that caught the D18
misalignment. `make sim_plasma` captures one plasma frame to
sim/plasma_frame.ppm; the comparison against the B18 control hash (sha256
de1ba729...) is a shasum step outside the target, re-run 2026-09-28 and
equal.

Hardware evidence:

The D18 build ran on a Terasic DE10-Nano. The plasma output was observed on an OLED display on 2026-09-25. The flashed .sof carries checksum 0x00E4BE7C, as recorded in the README proof table.

The 2026-09-29 compile (assertion blocks plus the specified reset
synchronizer) was flashed the same day and observed on a TV: dashboard
nominal (cfg_done near 340 ms, cfg_error off, pll_locked immediate, alive
blink about 1 Hz) and full-width boiling plasma. Its .sof sha256 is
184215f812b630427e8190fb90cfacdf8f2db570104bcaea90bb626f7c77c646. Display
model unrecorded, as with every earlier session.

## What remains unmeasured

The following items are not established by this build:

- No oscilloscope capture of pixel clock or syncs.
- No logic-analyzer capture of the physical I2C bus.
- No ADV7513 register readback.
- Endurance and hot-plug behaviour remain untested.

These absences are recorded deliberately. They define the next verification tasks.

## Source files

- Devlog: [devlog.md at D18](https://github.com/avolk201/procedural-gfx-fpga/blob/9f5dc7b/docs/devlog.md)
- D18 commit: [9f5dc7b](https://github.com/avolk201/procedural-gfx-fpga/commit/9f5dc7b)
- Constraints: [constraints/](https://github.com/avolk201/procedural-gfx-fpga/tree/main/constraints)
- RTL: [rtl/](https://github.com/avolk201/procedural-gfx-fpga/tree/main/rtl)
- Verification methodology: [docs/verification.md](https://github.com/avolk201/procedural-gfx-fpga/blob/main/docs/verification.md)
- Assertion mutation ledger: docs/devlog.md B20 and docs/verification.md
- Build artifacts, 2026-09-29: [docs/artifacts/d18/](https://github.com/avolk201/procedural-gfx-fpga/tree/main/docs/artifacts/d18)
- Compile source state: rtl commit b87262f, plus the docs commit that carries this post