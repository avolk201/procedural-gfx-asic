// tb/sim_adv7513_config.cpp
// Integration testbench for adv7513_config + i2c_controller (D5, D8, D10).
// Builds the physical bus and ADV7513 target in C++ to verify closed-loop
// sequencing, bit-exact ROM output, and error latching.

#include "Vtb_adv7513_config.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
#include <vector>
#include <cstring>

static constexpr int CLK_DIV = 250;
static constexpr int NUM_REGS = 13;
static constexpr int WATCHDOG_CYCLES = 500000; // ~2.5x expected 13-tx duration

struct RegPair {
    uint8_t addr;
    uint8_t data;
};

static const RegPair EXPECTED_ROM[NUM_REGS] = {
    {0x41, 0x00},
    {0x98, 0x03},
    {0x9A, 0xE0},
    {0x9C, 0x30},
    {0x9D, 0x61},
    {0xA2, 0xA4},
    {0xA3, 0xA4},
    {0xE0, 0xD0},
    {0xF9, 0x00},
    {0x15, 0x00},
    {0x16, 0x00},
    {0x17, 0x00},
    {0xAF, 0x00}
};

static bool g_verbose = false;
static int g_fail_count = 0;
static int g_checks_run = 0;

static bool check(bool ok, const char *msg) {
    ++g_checks_run;
    std::printf("%s: %s\n", ok ? "PASS" : "FAIL", msg);
    if (!ok) ++g_fail_count;
    return ok;
}

struct CapturedTx {
    uint8_t dev_addr;
    uint8_t reg_addr;
    uint8_t data;
};

struct TargetModel {
    bool in_frame = false;
    bool pull_low = false;
    uint8_t buf = 0;
    int bitpos = 0;
    int byte_index = 0;
    uint8_t rx_bytes[3] = {0};

    int tx_count = 0;
    int nack_tx_idx = -1;

    std::vector<CapturedTx> history;

    void on_start() {
        in_frame = true;
        pull_low = false;
        buf = 0;
        bitpos = 0;
        byte_index = 0;
    }

    void on_stop() {
        if (in_frame && byte_index == 3) {
            history.push_back({rx_bytes[0], rx_bytes[1], rx_bytes[2]});
            ++tx_count;
        }
        in_frame = false;
        pull_low = false;
    }

    void on_scl_rise(bool sda) {
        if (!in_frame || byte_index >= 3) return;
        if (bitpos < 8) {
            buf = (uint8_t)((buf << 1) | (sda ? 1 : 0));
            ++bitpos;
        } else if (bitpos == 8) {
            bitpos = 9;
        }
    }

    void on_scl_fall() {
        if (!in_frame || byte_index >= 3) return;
        if (bitpos == 8) {
            pull_low = (nack_tx_idx != tx_count);
        } else if (bitpos == 9) {
            rx_bytes[byte_index] = buf;
            ++byte_index;
            pull_low = false;
            buf = 0;
            bitpos = 0;
        }
    }
};

struct TestSpec {
    const char *label;
    int nack_tx_idx;
};

static void run_test(const TestSpec &spec) {
    std::printf("\n=== %s ===\n", spec.label);

    Vtb_adv7513_config dut;
    TargetModel target;
    target.nack_tx_idx = spec.nack_tx_idx;

    bool dut_sda_oe = false, dut_scl_oe = false;
    bool sda_line = true, scl_line = true;
    bool prev_sda = true, prev_scl = true;

    auto resolve = [&]() {
        sda_line = !(dut_sda_oe || target.pull_low);
        scl_line = !dut_scl_oe;
    };

    dut.clk_i = 0;
    dut.rst_n_i = 0;
    dut.sda_i = 1;
    dut.scl_i = 1;
    for (int i = 0; i < 10; ++i) {
        dut.clk_i = 1; dut.eval();
        dut.clk_i = 0; dut.eval();
    }
    dut.rst_n_i = 1;
    dut.clk_i = 1; dut.eval();
    dut.clk_i = 0; dut.eval();

    dut_sda_oe = (dut.sda_oe_o != 0);
    dut_scl_oe = (dut.scl_oe_o != 0);
    resolve();
    prev_sda = sda_line;
    prev_scl = scl_line;

    int cycles = 0;
    while (!dut.done_o && !dut.error_o && cycles < WATCHDOG_CYCLES) {
        resolve();
        dut.sda_i = sda_line ? 1 : 0;
        dut.scl_i = scl_line ? 1 : 0;

        dut.clk_i = 1; dut.eval();
        dut.clk_i = 0; dut.eval();

        dut_sda_oe = (dut.sda_oe_o != 0);
        dut_scl_oe = (dut.scl_oe_o != 0);
        resolve();

        bool scl_rose = (scl_line && !prev_scl);
        bool scl_fell = (!scl_line && prev_scl);
        bool sda_rose = (sda_line && !prev_sda);
        bool sda_fell = (!sda_line && prev_sda);

        if (sda_fell && scl_line) target.on_start();
        if (sda_rose && scl_line) target.on_stop();
        if (scl_rose)             target.on_scl_rise(sda_line);
        if (scl_fell)             target.on_scl_fall();

        prev_sda = sda_line;
        prev_scl = scl_line;
        ++cycles;
    }

    if (cycles >= WATCHDOG_CYCLES) {
        check(false, "watchdog expired - sequence hung");
        return;
    }

    if (spec.nack_tx_idx < 0) {
        check(dut.done_o == 1, "done_o asserted on completion");
        check(dut.error_o == 0, "error_o stayed low");
        check(target.history.size() == NUM_REGS, "captured exactly 13 I2C transactions");

        bool match = (target.history.size() == NUM_REGS);
        for (size_t i = 0; i < target.history.size() && i < NUM_REGS; ++i) {
            if (target.history[i].dev_addr != 0x72 ||
                target.history[i].reg_addr != EXPECTED_ROM[i].addr ||
                target.history[i].data     != EXPECTED_ROM[i].data) {
                match = false;
                break;
            }
        }
        check(match, "wire packets match ROM {0x72, reg, data} bit-exact");
    } else {
        check(dut.error_o == 1, "error_o latched on target NACK");
        check(dut.done_o == 0, "done_o stayed low");
        check(target.tx_count <= spec.nack_tx_idx + 1, "walker halted after error");
    }

    if (g_verbose) {
        std::printf("info: completed in %d cycles\n", cycles);
    }
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    for (int i = 1; i < argc; ++i)
        if (std::strcmp(argv[i], "-v") == 0) g_verbose = true;

    run_test({"T1 happy path: ACK all 13 configuration writes", -1});
    run_test({"T2 error injection: NACK transaction 1", 1});

    std::printf("\nSummary: %d failed out of %d checks\n", g_fail_count, g_checks_run);
    return g_fail_count ? 1 : 0;
}
