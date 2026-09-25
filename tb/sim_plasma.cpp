// tb/sim_plasma.cpp
// Verilator testbench for apu_top elaborated with SCENE=PLASMA: renders one
// frame of the scene to sim/plasma_frame.ppm (RGB332 expanded to RGB888 by
// bit replication) for a look check against the anim/render.py prototype.
// +frame=N picks the capture window (default 1); window N shows the frame
// offsets after N SOF advances. Timing itself is sim_main's job, not this
// one. Exit code is the interface: 0 only if the capture held a full frame
// (D6). Build and run: make sim_plasma

#include "Vapu_top.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);

    unsigned long long want_frame = 1;
    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "+frame=", 7) == 0)
            want_frame = strtoull(argv[i] + 7, nullptr, 10);
    }

    auto *tb = new Vapu_top;

    // Reset: active-low, held for 10 full clock cycles
    tb->clk_pix_i = 0;
    tb->rst_n_i = 0;
    for (int i = 0; i < 20; i++) {
        tb->clk_pix_i = 1; tb->eval();
        tb->clk_pix_i = 0; tb->eval();
    }
    tb->rst_n_i = 1;

    FILE *ppm_fp = fopen("sim/plasma_frame.ppm", "wb");
    if (!ppm_fp) {
        perror("sim/plasma_frame.ppm");
        delete tb;
        return 1;
    }
    fprintf(ppm_fp, "P6\n640 480\n255\n");

    unsigned long long sof_count = 0;
    unsigned long long pixels_written = 0;
    bool prev_sof = false;

    // Window N holds exactly frame N's 307200 px at their true raster
    // positions: with the D18 prefetch, de_o is aligned to the active
    // window, and frame N's last pixel lands well before the next SOF.
    const unsigned long long TOTAL_CYCLES = (want_frame + 2) * 420000ull;

    for (unsigned long long cycle = 0; cycle < TOTAL_CYCLES; cycle++) {
        tb->clk_pix_i = 1;
        tb->eval();

        if (tb->sof_o && !prev_sof) {
            sof_count++;
            if (sof_count > want_frame && pixels_written > 0) break;
        }
        prev_sof = tb->sof_o;

        if (tb->de_o && sof_count == want_frame) {
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

        tb->clk_pix_i = 0;
        tb->eval();
    }

    fclose(ppm_fp);

    int fails = 0;
    if (pixels_written != 640ull * 480ull) {
        printf("Capture: FAIL (%llu px, expected 307200)\n", pixels_written);
        fails++;
    } else {
        printf("Capture: PASS (307200 px, frame window %llu)\n", want_frame);
    }

    printf("%s\n", fails ? "FAIL" : "SUCCESS");
    delete tb;
    return fails ? 1 : 0;
}
