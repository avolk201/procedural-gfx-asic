// tb/sim_i2c.cpp
// Closed-loop protocol testbench for i2c_controller (docs/decisions.md D5, D8-D11).
//
// The tb IS the physical layer. The core only has oe/in ports (D4), so the
// wired-AND resolution, the pull-ups, and a write-only behavioral ADV7513 all
// live here: a line reads low if the controller or the target pulls it, high
// otherwise (the high is the pull-up resistor, expressed as logic). Everything
// a scope would see on a real board is computed in this file; none of it is
// deliverable RTL.
//
// Test matrix (D10), each test on a fresh model with its own reset:
//   T1 happy path:  write dev 0x39, reg, data. Target ACKs all three bytes.
//                   Full framing checks; catches bit-count truncation (B4)
//                   and a missing STOP (B5) if either ever regresses.
//   T2 wrong addr:  dev 0x38. Target NACKs the address byte, ACKs the rest.
//                   ack_err_o must set by the end of that ACK phase and stay
//                   sticky through done_o. The controller completes the
//                   transaction either way: no-abort contract (D10).
//
// Exit code is the interface (D6 rule 3): 0 only if every check passed.
// Watchdog expiry is a failure, not an exit condition (D6 rule 1).
// Bus edge trace: -v.

#include "Vi2c_controller.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
#include <cstring>

// Timing constants mirror the RTL defaults so harness and DUT stay in sync.
// Expected duration is derived from the FSM (1 START + 3*18 byte + 3 STOP +
// 1 DONE ticks, plus up to CLK_DIV+1 for busy latency), then doubled for the
// watchdog: the watchdog is a hang detector, not a scoreboard bound (D11).
static constexpr int CLK_DIV = 250;
static constexpr int BUSY_LATENCY_MAX = CLK_DIV + 1;
static constexpr int TICKS_PER_BYTE = 18;   // 8 data bits * 2 phases + ACK * 2
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
static constexpr int N_BYTES = 3;

// Target ACK behavior (D9): ACK everything, or NACK a mismatching address
// byte and ACK the rest.
enum TargetMode { ACK_ALL, NACK_ADDR };

struct TestSpec {
    const char *label;
    uint8_t dev_addr;
    TargetMode mode;
    bool expect_addr_nack;
};

static bool g_verbose = false;
static int g_fail_count = 0;
static int g_checks_run = 0;

// One fail counter, one path into it (B9): every verdict goes through here,
// and main() turns the count into the exit code.
static bool check(bool ok, const char *msg) {
    ++g_checks_run;
    std::printf("%s: %s\n", ok ? "PASS" : "FAIL", msg);
    if (!ok) ++g_fail_count;
    return ok;
}

// Write-only behavioral ADV7513 (D9). Watches START/STOP on the resolved bus,
// shifts in bits on SCL rising edges MSB-first, pulls SDA low on the ninth
// clock when it would ACK. No register file, no reads, no clock stretching:
// it models the wire behavior the DUT depends on, nothing more.
struct TargetModel {
    bool in_frame = false;
    bool pull_low = false;      // 1 = drive SDA low (open-drain ACK)
    uint8_t buf = 0;
    int bitpos = 0;             // 0..8 data bits shifted in, 9 = ACK clock seen
    int byte_index = 0;         // also the count of completed bytes

    uint8_t rx_bytes[N_BYTES] = {0};
    bool ack_low[N_BYTES] = {false};    // line level observed on the ninth clock

    void on_start() {
        in_frame = true;
        pull_low = false;
        buf = 0;
        bitpos = 0;
        byte_index = 0;
    }
    void on_stop() {
        in_frame = false;
        pull_low = false;
    }
    void on_scl_rise(bool sda) {
        if (!in_frame || byte_index >= N_BYTES) return;
        if (bitpos < 8) {
            buf = (uint8_t)((buf << 1) | (sda ? 1 : 0));
            ++bitpos;
        } else if (bitpos == 8) {
            ack_low[byte_index] = !sda;
            bitpos = 9;
        }
    }
    void on_scl_fall() {
        if (!in_frame || byte_index >= N_BYTES) return;
        if (bitpos == 8) {
            // eight data bits in: choose the level to hold during the ninth
            // clock. Held through SCL-high, released on the following fall.
            bool ack = true;
            if (mode == NACK_ADDR && byte_index == 0)
                ack = (buf == (uint8_t)(DEV_ADDR_OK << 1));
            pull_low = ack;
        } else if (bitpos == 9) {
            rx_bytes[byte_index] = buf;
            ++byte_index;
            pull_low = false;
            buf = 0;
            bitpos = 0;
        }
    }
    TargetMode mode = ACK_ALL;
};

static void run_test(const TestSpec &spec) {
    std::printf("\n=== %s ===\n", spec.label);

    Vi2c_controller dut;    // fresh model per test: its own reset (D10)

    // Resolved-bus state. One-cycle staleness in the pre-edge resolve is safe:
    // lines only move on ticks, 250 clk cycles apart (D8).
    bool dut_sda_oe = false, dut_scl_oe = false;
    bool sda_line = true, scl_line = true;
    bool prev_sda = true, prev_scl = true;
    TargetModel target;
    target.mode = spec.mode;

    // Recorded events, all on the resolved bus or the DUT status outputs
    int cycles = 0;
    const int start_cycle = 0;
    int busy_cycle = -1;
    int done_cycle = -1, done_end_cycle = -1;
    int start_edge_count = 0, start_edge_cycle = -1;
    int stop_count = 0, stop_cycle = -1;
    int data_rise_count = 0, first_data_rise_cycle = -1;
    int first_ack_rise_cycle = -1, last_ack_rise_cycle = -1;
    int ack_err_cycle = -1;
    bool start_released = false;
    bool saw_done = false, done_fell = false;
    bool ack_err_at_done = false;

    auto resolve = [&]() {
        sda_line = !(dut_sda_oe || target.pull_low);
        scl_line = !dut_scl_oe;
    };

    // Reset, then seed the resolver from the DUT itself instead of hardcoded
    // assumptions about its outputs.
    dut.clk_i = 0;
    dut.rst_n_i = 0;
    dut.start_i = 0;
    dut.dev_addr_i = 0;
    dut.reg_addr_i = 0;
    dut.data_i = 0;
    dut.sda_i = 1;
    dut.scl_i = 1;
    for (int i = 0; i < 8; ++i) {
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

    // Stimulus per the D1 contract: start_i held until busy_o rises; payload
    // stable until done_o.
    dut.dev_addr_i = spec.dev_addr;
    dut.reg_addr_i = REG_ADDR;
    dut.data_i     = DATA;
    dut.start_i    = 1;

    while (!(saw_done && done_fell) && cycles < WATCHDOG_CYCLES) {
        // Pre-edge: drive the bus from the last resolved state, plus stimulus.
        resolve();
        dut.sda_i = sda_line ? 1 : 0;
        dut.scl_i = scl_line ? 1 : 0;
        if (busy_cycle >= 0 && !start_released) {
            dut.start_i = 0;
            start_released = true;
        }

        dut.clk_i = 1; dut.eval();
        dut.clk_i = 0; dut.eval();

        // Post-edge: mirror outputs, re-resolve, classify edges on the
        // resolved bus, step the target model.
        dut_sda_oe = (dut.sda_oe_o != 0);
        dut_scl_oe = (dut.scl_oe_o != 0);
        if (dut.busy_o != 0 && busy_cycle < 0) busy_cycle = cycles;
        if (dut.ack_err_o != 0 && ack_err_cycle < 0) ack_err_cycle = cycles;
        if (dut.done_o != 0) {
            if (!saw_done) {
                saw_done = true;
                done_cycle = cycles;
                ack_err_at_done = (dut.ack_err_o != 0);
            }
        } else if (saw_done) {
            done_fell = true;
            done_end_cycle = cycles;
        }
        resolve();

        bool scl_rose = (scl_line && !prev_scl);
        bool scl_fell = (!scl_line && prev_scl);
        bool sda_rose = (sda_line && !prev_sda);
        bool sda_fell = (!sda_line && prev_sda);

        if (sda_fell && scl_line) {
            ++start_edge_count;
            start_edge_cycle = cycles;
            target.on_start();
            if (g_verbose) std::printf("*** Cycle %d: START edge detected\n", cycles);
        }
        if (sda_rose && scl_line) {
            ++stop_count;
            stop_cycle = cycles;
            target.on_stop();
            if (g_verbose) std::printf("*** Cycle %d: STOP edge detected\n", cycles);
        }
        if (scl_rose) {
            // Data clocks only. The STOP sequence re-raises SCL before the
            // final SDA rise; that rise is not a data clock and must not
            // inflate the count (9 per byte, 27 total).
            if (target.in_frame && target.byte_index < N_BYTES) {
                ++data_rise_count;
                if (first_data_rise_cycle < 0) first_data_rise_cycle = cycles;
                if (target.bitpos == 8) {
                    last_ack_rise_cycle = cycles;
                    if (target.byte_index == 0 && first_ack_rise_cycle < 0)
                        first_ack_rise_cycle = cycles;
                }
            }
            target.on_scl_rise(sda_line);
            if (g_verbose)
                std::printf("Cycle %d: SCL rise #%d, SDA=%d\n", cycles, data_rise_count, sda_line ? 1 : 0);
        }
        if (scl_fell) {
            target.on_scl_fall();
            if (g_verbose) std::printf("Cycle %d: SCL fall\n", cycles);
        }
        if ((sda_rose || sda_fell) && !scl_line && g_verbose) {
            std::printf("Cycle %d: data setup, SDA -> %d\n", cycles, sda_line ? 1 : 0);
        }

        prev_sda = sda_line;
        prev_scl = scl_line;
        ++cycles;
    }

    char msg[160];

    if (!(saw_done && done_fell)) {
        // One loud failure; after a hang nothing else is meaningful (D6).
        check(false, "watchdog expired - transaction never completed");
        return;
    }

    check(busy_cycle >= 0 && busy_cycle - start_cycle <= BUSY_LATENCY_MAX,
          "busy_o rose within CLK_DIV+1 cycles of start_i (D1 contract)");
    check(start_released,
          "tb held start_i until busy_o, then released (D1 checker)");
    check(start_edge_count == 1 && start_edge_cycle >= 0 && start_edge_cycle < first_data_rise_cycle,
          "exactly one START condition, before first SCL data rise");

    std::snprintf(msg, sizeof msg, "SCL data rises == %d (9 per byte x %d bytes)", 9 * N_BYTES, N_BYTES);
    check(data_rise_count == 9 * N_BYTES, msg);

    std::snprintf(msg, sizeof msg, "target received %d complete bytes", N_BYTES);
    check(target.byte_index == N_BYTES, msg);

    const uint8_t expect[N_BYTES] = { (uint8_t)(spec.dev_addr << 1), REG_ADDR, DATA };
    bool bytes_ok = (target.byte_index == N_BYTES);
    for (int i = 0; i < N_BYTES && bytes_ok; ++i)
        if (target.rx_bytes[i] != expect[i]) bytes_ok = false;
    std::snprintf(msg, sizeof msg, "wire bytes reconstruct to {%02X, %02X, %02X} = dev<<1|0, reg, data",
                  expect[0], expect[1], expect[2]);
    check(bytes_ok, msg);

    bool acks_ok = (target.byte_index == N_BYTES);
    for (int i = 0; i < N_BYTES && acks_ok; ++i) {
        bool want_low = spec.expect_addr_nack ? (i != 0) : true;
        if (target.ack_low[i] != want_low) acks_ok = false;
    }
    check(acks_ok, spec.expect_addr_nack ? "address byte NACKed on the wire, bytes 2-3 ACKed"
                                         : "ACK driven low on every ninth clock");

    check(stop_count == 1 && stop_cycle > last_ack_rise_cycle,
          "exactly one STOP condition, after the last ACK clock");

    int done_width = done_end_cycle - done_cycle;
    std::snprintf(msg, sizeof msg, "done_o width measured at %d cycles (one tick = %d)", done_width, CLK_DIV);
    check(done_width >= 1 && done_width <= 2 * CLK_DIV, msg);

    if (spec.expect_addr_nack) {
        check(ack_err_cycle >= 0 && first_ack_rise_cycle >= 0 && ack_err_cycle <= first_ack_rise_cycle + 2,
              "ack_err_o set by the end of the address ACK phase");
        check(ack_err_at_done, "ack_err_o sticky through done_o");
    } else {
        check(ack_err_at_done == false && ack_err_cycle < 0,
              "ack_err_o stayed 0 for an all-ACK transaction");
    }

    // Informational, NOT a check (D11): expected duration is a scoreboard
    // quantity, the watchdog is the bound. Conflating them false-fails
    // healthy runs by off-by-one.
    std::printf("info: transaction took %d cycles; healthy %d-tick budget is ~%d\n",
                done_cycle - start_cycle, EXPECTED_TRANSACTION_TICKS, EXPECTED_TRANSACTION_CYCLES);
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    for (int i = 1; i < argc; ++i)
        if (std::strcmp(argv[i], "-v") == 0) g_verbose = true;

    run_test({"T1 happy path: dev 0x39, target ACKs all three bytes", DEV_ADDR_OK, ACK_ALL, false});
    run_test({"T2 wrong address: dev 0x38, target NACKs byte 1", DEV_ADDR_BAD, NACK_ADDR, true});

    std::printf("\nSummary: %d failed out of %d checks\n", g_fail_count, g_checks_run);
    return g_fail_count ? 1 : 0;
}
