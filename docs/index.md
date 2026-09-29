---
layout: default
title: FPGA Notes
description: Engineering post-mortems tied to the procedural-gfx-fpga repository.
---

Project repository: [avolk201/procedural-gfx-fpga](https://github.com/avolk201/procedural-gfx-fpga)

## Post-mortems

<ul>
{% for post in site.posts %}
  <li>
    <a href="{{ post.url | relative_url }}">{{ post.date | date: "%Y-%m-%d" }}, {{ post.title }}</a>
  </li>
{% endfor %}
</ul>

## Build artifacts

Quartus reports from the 2026-09-29 compile on the Bazzite box (Quartus Prime
Standard 25.1, part 5CSEBA6U23I7). Source state: working tree at 84bca86 plus
the uncommitted concurrent-assertion blocks in rtl/apu_vga_timing.sv and
rtl/i2c_controller.sv; recompile after that commit for a tag-pinned set.

- [sta.rpt](artifacts/d18/sta.rpt): Slow 1100mV 100C, TNS 0.000; worst setup
  +13.868 ns on clk_50m and +24.117 ns on divclk; hold +0.232/+0.365;
  divclk Fmax 64.1 MHz against the 25.175 required (72.79 before the
  assertion monitor counters landed), clk_50m Fmax 163.08 MHz.
- [metastability.rpt](artifacts/d18/metastability.rpt): both synchronizer
  chains specified by name (tgl_sync[1], sync_reset:u_sync_rst_pix|d[1]);
  worst-case MTBF 1e9 years; fraction of chains uncalculated 0.000; worst-case
  available settling 17.761 ns.
- [report_cdc_attempt.log](artifacts/d18/report_cdc_attempt.log): report_cdc
  is not a command in Quartus Prime Standard 25.1; the log is the evidence,
  kept so the absence stays cited rather than rediscovered.
- [fit.summary](artifacts/d18/fit.summary): 2,068/41,910 ALMs, 3/112 DSP,
  0 M10K bits, 1/6 PLL.
- [quartus_compile.log](artifacts/d18/quartus_compile.log), console capture,
  and [sha256sums.txt](artifacts/d18/sha256sums.txt) for the set above.

## Primary project documentation

- [README](https://github.com/avolk201/procedural-gfx-fpga/blob/main/README.md)
- [devlog.md](https://github.com/avolk201/procedural-gfx-fpga/blob/main/docs/devlog.md)
- [verification.md](https://github.com/avolk201/procedural-gfx-fpga/blob/main/docs/verification.md)
- [cordic.md](https://github.com/avolk201/procedural-gfx-fpga/blob/main/docs/cordic.md)
- [deploy.md](https://github.com/avolk201/procedural-gfx-fpga/blob/main/docs/deploy.md)
- [decisions.md](https://github.com/avolk201/procedural-gfx-fpga/blob/main/docs/decisions.md)
- [references.md](https://github.com/avolk201/procedural-gfx-fpga/blob/main/docs/references.md)