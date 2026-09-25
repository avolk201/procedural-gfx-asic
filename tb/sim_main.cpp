// tb/sim_main.cpp
// Verilator testbench for apu_top: measures HSync width, VSync line count,
// frame period and DE-during-HSync overlap against VESA 640x480@60, and
// captures frame 1 to sim/frame.ppm (RGB332 expanded to RGB888 by bit
// replication).
// Exit code is the interface: 0 only if every measurement matched (D6).
// Build and run: make sim

#include "Vapu_top.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);

    auto *tb = new Vapu_top;
    int fails = 0;

    // Reset: active-low, held for 10 full clock cycles
    tb->clk_pix_i = 0;
    tb->rst_n_i = 0;
    for (int i = 0; i < 20; i++) {
        tb->clk_pix_i = 1; tb->eval();
        tb->clk_pix_i = 0; tb->eval();
    }
    tb->rst_n_i = 1;

    unsigned long long de_count = 0;        // DE cycles across the whole run
    unsigned long long hsync_width = 0;     // current HSync low-pulse counter
    unsigned long long vsync_lines = 0;     // line starts seen while VSync low
    unsigned long long bad_hsync_pulses = 0;
    unsigned long long bad_vsync_widths = 0;
    unsigned long long frame_cycles = 0;    // cycles since last SOF
    unsigned long long sof_count = 0;
    unsigned long long pixels_written = 0;
    unsigned long long de_during_sync = 0;  // de_o cycles while hsync is low
    bool prev_sof = false;
    bool prev_sol = false;
    bool prev_hsync = true;
    bool prev_vsync = true;

    FILE *ppm_fp = fopen("sim/frame.ppm", "wb");
    if (!ppm_fp) {
        perror("sim/frame.ppm");
        delete tb;
        return 1;
    }
    fprintf(ppm_fp, "P6\n640 480\n255\n");

    // Two full frames: 2 * H_TOTAL * V_TOTAL = 2 * 800 * 525
    const unsigned long long TOTAL_CYCLES = 840000;

    for (unsigned long long cycle = 0; cycle < TOTAL_CYCLES; cycle++) {
        tb->clk_pix_i = 1;
        tb->eval();

        bool de_o    = tb->de_o;
        bool hsync_o = tb->hsync_o;
        bool vsync_o = tb->vsync_o;
        bool sof_o   = tb->sof_o;
        bool sol_o   = tb->sol_o;

        if (de_o) de_count++;
        if (de_o && !hsync_o) de_during_sync++;

        // SOF detection runs before the capture gate so sof_count already
        // marks the frame boundary this cycle.
        if (sof_o && !prev_sof) {
            sof_count++;
            printf("Frame %llu: %llu px clocks\n", sof_count, frame_cycles);
            // The first interval is measured from loop start, not a real
            // frame boundary; only intervals between SOFs are checkable.
            if (sof_count >= 2 && frame_cycles != 420000) {
                printf("Frame period: FAIL (%llu, expected 420000)\n", frame_cycles);
                fails++;
            }
            frame_cycles = 0;
        }
        prev_sof = sof_o;

        // Capture exactly one frame (B7): between SOF 1 and SOF 2. Frame 0 is
        // skipped so reset debris can never reach the PPM, and the file holds
        // one 640x480 frame under its header.
        if (de_o && sof_count == 1) {
            uint8_t rgb = tb->rgb_o;
            uint8_t r3 = (rgb >> 5) & 0x7;
            uint8_t g3 = (rgb >> 2) & 0x7;
            uint8_t b2 =  rgb       & 0x3;
            uint8_t r8 = (r3 << 5) | (r3 << 2) | (r3 >> 1);
            uint8_t g8 = (g3 << 5) | (g3 << 2) | (g3 >> 1);
            uint8_t b8 = (b2 << 6) | (b2 << 4) | (b2 << 2) | b2;

            fputc(r8, ppm_fp);
            fputc(g8, ppm_fp);
            fputc(b8, ppm_fp);
            pixels_written++;
        }

        // HSync: count the low pulse, judge it at the rising edge
        if (!hsync_o) hsync_width++;
        if (hsync_o && !prev_hsync) {
            if (hsync_width != 96) bad_hsync_pulses++;
            hsync_width = 0;
        }
        prev_hsync = hsync_o;

        // VSync width in lines (B6): count line starts while vsync is low,
        // between its falling and rising edges. The old counter sampled only
        // at SOF, where vsync is high, so it could never leave zero.
        if (sol_o && !prev_sol && !vsync_o) vsync_lines++;
        prev_sol = sol_o;
        if (vsync_o && !prev_vsync) {
            printf("VSync lines: %llu\n", vsync_lines);
            if (vsync_lines != 2) bad_vsync_widths++;
            vsync_lines = 0;
        }
        prev_vsync = vsync_o;

        frame_cycles++;

        tb->clk_pix_i = 0;
        tb->eval();
    }

    fclose(ppm_fp);

    printf("Total DE cycles: %llu (expected 614400)\n", de_count);
    if (de_count != 614400) {
        printf("DE count: FAIL\n");
        fails++;
    } else {
        printf("DE count: PASS\n");
    }

    if (de_during_sync) {
        printf("DE during HSync: FAIL (%llu cycles, expected 0)\n", de_during_sync);
        fails++;
    } else {
        printf("DE during HSync: PASS (0 cycles)\n");
    }

    if (bad_hsync_pulses) {
        printf("HSync width: FAIL (%llu pulses != 96 px)\n", bad_hsync_pulses);
        fails++;
    } else {
        printf("HSync width: PASS (all pulses 96 px)\n");
    }

    if (bad_vsync_widths) {
        printf("VSync width: FAIL (%llu frames != 2 lines)\n", bad_vsync_widths);
        fails++;
    } else {
        printf("VSync width: PASS (2 lines per frame)\n");
    }

    if (pixels_written != 640ull * 480ull) {
        printf("Capture: FAIL (%llu px, expected 307200)\n", pixels_written);
        fails++;
    } else {
        printf("Capture: PASS (307200 px, one frame)\n");
    }

    printf("%s\n", fails ? "FAIL" : "SUCCESS");
    delete tb;
    return fails ? 1 : 0;
}
