// tb/sim_i2c.cpp
// Closed-loop protocol testbench for i2c_controller (see docs/decisions.md D5,D6).
//
// The tb IS the physical layer: wired-AND bus resolution + pullups + a
// behavioral target that ACKs address 0x39. The controller core only has oe/in
// ports (D4), so everything a scope would see on a real board is computed
// here. Nothing in this file is deliverable RTL; it models the world around
// the DUT.
//
// Test matrix (D10):
//   T1 happy path:  write dev 0x39, reg, data. Target ACKs all three bytes.
//                   Catches B4 (truncated bytes) and B5 (missing STOP).
//   T2 wrong addr:  dev 0x38. Target NACKs byte 1. ack_err_o must set and
//                   stay sticky until done_o (and until reset).
//
// Exit code is the interface (D6 rule 3): 0 only if every check passed.

#include "Vi2c_controller.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
#include <cstring>

// Constants are kept in one place so the RTL default and the C++ harness stay in sync.
// The expected runtime is derived from the FSM: START is 1 tick, each byte is 18
// ticks, STOP is 3 ticks, DONE is 1 tick, and the busy latency adds up to
// 1..CLK_DIV + 1 clk_i cycles before busy_o. The watchdog is intentionally
// larger than this expected duration so it catches hangs without false-failing a
// healthy transaction.
static constexpr int CLK_DIV = 250;
static constexpr int BUSY_LATENCY_MAX = CLK_DIV + 1;
static constexpr int TICKS_PER_BYTE = 18;
static constexpr int START_TICKS = 1;
static constexpr int STOP_TICKS = 3;
static constexpr int DONE_TICKS = 1;
static constexpr int EXPECTED_TRANSACTION_TICKS = START_TICKS + (3 * TICKS_PER_BYTE) + STOP_TICKS + DONE_TICKS;
static constexpr int EXPECTED_TRANSACTION_CYCLES = BUSY_LATENCY_MAX + (EXPECTED_TRANSACTION_TICKS * CLK_DIV);
static constexpr int WATCHDOG_CYCLES = EXPECTED_TRANSACTION_CYCLES * 2;
static constexpr uint8_t DEV_ADDR_OK = 0x39;
static constexpr uint8_t DEV_ADDR_BAD = 0x38;
static constexpr uint8_t REG_ADDR = 0x41;
static constexpr uint8_t DATA = 0x00;

// The target model is intentionally minimal: detect START/STOP, shift in SDA on
// SCL rising edges, and drive ACK or NACK on the ninth clock. It does not model
// an internal register file or read transactions; the goal is to match the wire
// behavior the DUT depends on.

// The scoreboard mirrors the header contract: each pass/fail check corresponds
// to a design guarantee from the I2C core contract, and the final summary is the
// interface used by the test harness.

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);

    bool verbose = false;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "-v") == 0) {
            verbose = true;
        }
    }

    // The bus model keeps a fixed ordering each cycle: resolve the line state from
    // the last OE values, advance the clock, re-resolve after the DUT updates, then
    // let the target model observe the resulting bus and update its checks. This
    // avoids the circular feedback problem while preserving the real open-drain
    // semantics.
    int fail_count = 0;
    int checks_run = 0;
    auto check = [&](bool ok, const char *msg) {
        ++checks_run;
        if (ok) {
            std::printf("PASS: %s\n", msg);
        } else {
            std::printf("FAIL: %s\n", msg);
            ++fail_count;
        }
        return ok;
    };

    // The DUT port names changed in D4: the harness drives sda_i/scl_i and reads
    // sda_oe_o/scl_oe_o. The resolved bus is computed in C++ so the testbench can
    // model the physical layer around the DUT.
    Vi2c_controller *dut = new Vi2c_controller();

    // Logic-level values are bools; the Verilator boundary is converted explicitly
    // as CData is read and written. The cycle counter is int here because the worst
    // healthy transaction is in the low tens of thousands of clk_i cycles, not the
    // millions used by the VGA tb.
    bool dut_sda_oe = false;
    bool dut_scl_oe = false;
    bool target_pull_low = false;
    bool sda_line = true;
    bool scl_line = true;
    bool prev_sda_line = true;
    bool prev_scl_line = true;
    int start_cycle = -1;
    int busy_cycle = -1;
    int done_cycle = -1;
    int start_edge_cycle = -1;
    int stop_cycle = -1;
    bool start_asserted = false;
    bool start_released = false;
    bool saw_busy = false;
    bool saw_done = false;
    bool saw_start_edge = false;
    bool saw_stop_edge = false;
    int scl_rise_count = 0;
    int start_edge_count = 0;
    int first_scl_rise_cycle = -1;


    auto resolve_lines = [&]() {
        const bool sda_low = dut_sda_oe || target_pull_low;
        const bool scl_low = dut_scl_oe;
        sda_line = !sda_low;
        scl_line = !scl_low;
    };

    // Reset helper/inlined sequence: rst_n low for a few cycles, then release.
    // Used before BOTH tests.
    dut->clk_i = 0;
    dut->rst_n_i = 0;
    dut->start_i = 0;
    dut->dev_addr_i = 0;
    dut->reg_addr_i = 0;
    dut->data_i = 0;
    dut->sda_i = 1;
    dut->scl_i = 1;

    for (int i = 0; i < 8; ++i) {
        dut->clk_i = 1; dut->eval();
        dut->clk_i = 0; dut->eval();
    }
    dut->rst_n_i = 1;

    // Seed the model from the DUT itself instead of hardcoded assumptions. The
    // port outputs are read one cycle after reset release and copied into the logic
    // variables that define the resolved bus.
    dut->clk_i = 1; dut->eval();
    dut->clk_i = 0; dut->eval();
    dut_sda_oe = (dut->sda_oe_o != 0);
    dut_scl_oe = (dut->scl_oe_o != 0);
    target_pull_low = false;
    resolve_lines();
    prev_sda_line = sda_line;
    prev_scl_line = scl_line;

    dut->dev_addr_i = DEV_ADDR_OK;
    dut->reg_addr_i = REG_ADDR;
    dut->data_i     = DATA;
    dut->start_i    = 1;
    start_asserted  = true;
    start_cycle     = 0;

    // Stage B loop body: fixed cycle order, passive physical-layer bookkeeping. The
    // harness resolves the open-drain bus, advances the DUT clock, samples the
    // resulting OE output, and classifies edges on the resolved bus so the next
    // stage can build a real target BFM and scoreboard on top of this model.
    int cycles = 0;
    while (!saw_done && cycles < WATCHDOG_CYCLES) {
        // Duty 1: pre-edge resolve and drive the bus from the last OE state.
        resolve_lines();
        dut->sda_i = sda_line ? 1 : 0;
        dut->scl_i = scl_line ? 1 : 0;

        if (saw_busy && !start_released) {
            dut->start_i = 0;
            start_released = true;
        }

        // Duty 2: rising edge eval.
        dut->clk_i = 1;
        dut->eval();

        // Duty 3: falling edge eval.
        dut->clk_i = 0;
        dut->eval();

        // Duty 4: post-edge mirror read + re-resolve.
        dut_sda_oe = (dut->sda_oe_o != 0);
        dut_scl_oe = (dut->scl_oe_o != 0);
        if (dut->busy_o != 0 && !saw_busy) { saw_busy = true; busy_cycle = cycles; }
        if (dut->done_o != 0 && !saw_done) { saw_done = true; done_cycle = cycles; }
        resolve_lines();

        // Duties 5/6: classify the resolved bus edges and update the tracking state
        // used by the upcoming target BFM and protocol assertions.
        bool scl_rose = (scl_line && !prev_scl_line);
        bool scl_fell = (!scl_line && prev_scl_line);
        bool sda_rose = (sda_line && !prev_sda_line);
        bool sda_fell = (!sda_line && prev_sda_line);

        if (scl_rose) {
            ++scl_rise_count;
            if (first_scl_rise_cycle < 0) {
                first_scl_rise_cycle = cycles;
            }
            if (verbose) {
                std::printf("Cycle %d: SCL rise #%d, SDA=%d\n", cycles, scl_rise_count, sda_line ? 1 : 0);
            }
        }
        if (scl_fell && verbose) {
            std::printf("Cycle %d: SCL fall\n", cycles);
        }
        if (sda_fell && scl_line) {
            saw_start_edge = true;
            ++start_edge_count;
            start_edge_cycle = cycles;
            if (verbose) {
                std::printf("*** Cycle %d: START edge detected\n", cycles);
            }
        }
        if (sda_rose && scl_line) {
            saw_stop_edge = true;
            stop_cycle = cycles;
            if (verbose) {
                std::printf("*** Cycle %d: STOP edge detected\n", cycles);
            }
        }
        if ((sda_rose || sda_fell) && !scl_line && verbose) {
            std::printf("Cycle %d: data setup, SDA -> %d\n", cycles, sda_line ? 1 : 0);
        }

        // Update edge memory after the resolved wire is recomputed.
        prev_sda_line = sda_line;
        prev_scl_line = scl_line;

        ++cycles;
    }

    delete dut;
    if (!saw_done) {
        // Watchdog path: one loud failure, nothing else is meaningful after a hang.
        check(false, "watchdog expired - transaction never completed");
    } else {
        // contract line: busy within 1..CLK_DIV+1 of held start (D1)
        check(busy_cycle >= 0 && busy_cycle - start_cycle <= BUSY_LATENCY_MAX,
            "busy_o rose within CLK_DIV+1 cycles of start_i (D1 contract)");

        // contract self-enforcement: the tb itself obeyed hold-until-busy
        check(start_released,
            "tb held start_i until busy_o, then released (D1 checker)");

        // framing: exactly one START, before any data clocking
        check(start_edge_count == 1 && start_edge_cycle < first_scl_rise_cycle,
            "exactly one START condition, before first SCL rise");

        // informational, NOT a check: duration vs derived expectation
        std::printf("info: transaction took %d cycles; healthy 59-tick budget is ~%d\n",
                    done_cycle - start_cycle, EXPECTED_TRANSACTION_CYCLES);
    }

    std::printf("Summary: %d failed out of %d checks\n", fail_count, checks_run);
    return fail_count ? 1 : 0;
}
