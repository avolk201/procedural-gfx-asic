// tb/sim_cordic.cpp
// Exhaustive cross-check of rtl/apu_cordic.sv against tb/cordic_golden.py.
//
// The golden model is the oracle: `python3 tb/cordic_golden.py` self-tests it
// (24 checks) and it was reproduced bit-for-bit by a second independent
// implementation, so a mismatch here is an RTL bug, not a model bug. Every
// one of the 2**16 phases is fed back-to-back, so one run also proves the
// 1-sample/clk throughput and the vld/data alignment, not the values alone.
//
// Test matrix; A/D/E/T are exact (integer identity), B/C/F are bounded:
//   A  bit-exact RTL == golden, all phases. Fails on the negative half alone
//      if the RTL shifts unsigned (a logical >>> where a signed one is due).
//   D  the four cardinal angles against hand integers. cos(0)=2**22-1, NOT
//      2**22: the z residual at theta=0 is not exactly zero (see the model).
//   E  measured input->output fill equals LATENCY, and result 0 is phase 0.
//   T  vld_o contiguous at 1 sample/clk once the pipe is filled.
//   B  |golden - libm| <= 2**-14. This bounds the ALGORITHM, not the RTL.
//   C  |cos^2 + sin^2 - 1| <= 2**-13, a model-free sanity net.
//   F  t+90 / t+180 exact; -t within NEGATION_CAP. Adding 90 or 180 only
//      changes the quadrant (an exact negate/swap), so it is bit-exact; a
//      negation folds to a different remainder and runs its own decision
//      sequence, so it carries its own residual and is bounded, never 0.
//
// The golden header (n/W/FZ/NA/x0) is parsed and compared at run time: a stale
// file from a previous parameter set is otherwise indistinguishable from a
// correct one (the B16 stale-report lesson, applied to a data file).
//
// Exit code is the interface (D6 rule 3): 0 only if every check passed. A
// watchdog is a hang detector, never an exit condition (D6 rule 1, D11).
// -v prints the measured max-error/max-unit detail.
//
// Build and run: make sim_cordic

#include "Vapu_cordic.h"
#include "verilated.h"
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>
#include <fstream>

// Parameter mirrors of rtl/apu_cordic.sv and tb/cordic_golden.py so harness,
// DUT and model stay in sync; load_golden re-checks the model side at run time.
static constexpr int N_STAGES = 16;
static constexpr int DATA_W   = 24;   // cos_o/sin_o bits, signed
static constexpr int FZ_BITS  = 24;   // fractional angle bits (z = FZ+1 bits)
static constexpr int NA_BITS  = 16;   // phase_i bits
static constexpr int X0       = 2547003;
static constexpr int NP       = 1 << NA_BITS; // 65536 phases
static constexpr int FRAC     = DATA_W - 2;   // 22: Q2.22 scaling

// Latency the contract claims; E measures the fill and asserts this equals it.
// Adding or removing a pipeline stage changes the measurement and trips E,
// which forces the number and the module header to be reconciled.
static constexpr int LATENCY  = 18;

// Bounds and caps, each traceable to a measurement of the golden model.
static constexpr double ACC_BOUND    = 0x1p-14;   // 2^-14 = 6.104e-05
static constexpr double UNIT_BOUND   = 0x1p-13;   // 2^-13
static constexpr int    NEGATION_CAP = 266;       // 2x measured single-angle 133

// Watchdog budget: fill + every phase + a full drain, with headroom. It is a
// hang detector only; the real bound is produced==NP. Expected duration is
// informational, never the bound (D11).
static constexpr int WATCHDOG_CYCLES = LATENCY + NP + LATENCY + 1000;

static bool g_verbose = false;
static int  g_fail_count = 0;
static int  g_checks_run = 0;

static bool check(bool ok, const char *msg) {
    ++g_checks_run;
    std::printf("%s: %s\n", ok ? "PASS" : "FAIL", msg);
    if (!ok) ++g_fail_count;
    return ok;
}

// Verilator hands a 24-bit port back as a 32-bit IData (uint32_t); the signed
// bit is bit 23, so extend from there before comparing to the signed model.
static inline int32_t sxt24(uint32_t v) {
    return (int32_t)(v << (32 - DATA_W)) >> (32 - DATA_W);
}

struct Golden {
    std::vector<int32_t> cos_;
    std::vector<int32_t> sin_;
};

// Returns false on any structural fault (missing file, header mismatch, wrong
// row count). Those are fatal: every other check is meaningless without them.
static bool load_golden(const char *path, Golden &g) {
    std::ifstream in(path);
    if (!in) {
        std::printf("FAIL: cannot open golden file %s (run: python3 "
                    "tb/cordic_golden.py emit sim/cordic_golden.hex)\n", path);
        return false;
    }
    std::string line;
    std::getline(in, line);   // # cordic_golden.hex  n=16 W=24 FZ=24 NA=16 x0=...
    int hn, hW, hFZ, hNA, hx0;
    if (std::sscanf(line.c_str(),
                    "# cordic_golden.hex n=%d W=%d FZ=%d NA=%d x0=%d",
                    &hn, &hW, &hFZ, &hNA, &hx0) != 5) {
        std::printf("FAIL: golden header not parseable: %s\n", line.c_str());
        return false;
    }
    if (hn != N_STAGES || hW != DATA_W || hFZ != FZ_BITS ||
        hNA != NA_BITS  || hx0 != X0) {
        std::printf("FAIL: golden header n=%d W=%d FZ=%d NA=%d x0=%d != tb "
                    "n=%d W=%d FZ=%d NA=%d x0=%d (stale file?)\n",
                    hn, hW, hFZ, hNA, hx0, N_STAGES, DATA_W, FZ_BITS, NA_BITS, X0);
        return false;
    }
    std::getline(in, line);   // column labels
    int ph; int32_t c, s;
    g.cos_.clear();
    g.sin_.clear();
    while (in >> ph >> c >> s) {
        g.cos_.push_back(c);
        g.sin_.push_back(s);
    }
    if ((int)g.cos_.size() != NP) {
        std::printf("FAIL: golden has %zu rows, expected %d\n", g.cos_.size(), NP);
        return false;
    }
    return true;
}

// D: cardinal angles against the model. The integers are hand-transcribed from
// the measured model, so this also catches a corrupted golden file.
static void check_cardinals(const Golden &g) {
    struct Card { int phase; int32_t c; int32_t s; const char *label; };
    static const Card cards[] = {
        {0,     4194303,     -70, "D: phase 0, cos=2**22-1 not 2**22"},
        {16384,      70, 4194303, "D: phase 90deg"},
        {32768, -4194303,     70, "D: phase 180deg"},
        {49152,     -70, -4194303, "D: phase 270deg"},
    };
    std::printf("\n=== D: golden cardinal vectors ===\n");
    for (const Card &cd : cards)
        check(g.cos_[cd.phase] == cd.c && g.sin_[cd.phase] == cd.s, cd.label);
}

// A, E, T: drive the full phase set through the pipeline in one pass.
static void check_pipeline(const Golden &g) {
    std::printf("\n=== A / E / T: pipelined sweep of all %d phases ===\n", NP);
    Vapu_cordic dut;

    dut.clk_i = 0;
    dut.rst_n_i = 0;
    dut.vld_i = 0;
    dut.phase_i = 0;
    for (int i = 0; i < 8; ++i) {
        dut.clk_i = 1; dut.eval();
        dut.clk_i = 0; dut.eval();
    }
    dut.rst_n_i = 1;

    int  produced = 0;
    int  first_bad = -1;        // A
    bool align_ok = true;       // E: result 0 is phase 0
    bool contig_ok = true;      // T
    int  vld_i_cyc = -1;        // cycle vld_i first sampled high
    int  vld_o_cyc = -1;        // cycle vld_o first observed high
    int  prev_out = -LATENCY;   // for contiguity

    for (int cyc = 0; cyc < WATCHDOG_CYCLES && produced < NP; ++cyc) {
        bool feeding = (produced < NP);
        // Feed phase = cyc; the pipeline preserves order, so output index
        // `produced` lines up with golden index `produced`.
        dut.vld_i   = feeding ? 1 : 0;
        dut.phase_i = feeding ? (uint16_t)cyc : 0;
        if (feeding && vld_i_cyc < 0) vld_i_cyc = cyc;

        dut.clk_i = 1; dut.eval();
        dut.clk_i = 0; dut.eval();

        if (!dut.vld_o) continue;
        int32_t rc = sxt24(dut.cos_o);
        int32_t rs = sxt24(dut.sin_o);

        if (vld_o_cyc < 0) vld_o_cyc = cyc;
        else if (cyc - prev_out != 1) contig_ok = false;
        prev_out = cyc;

        if (rc != g.cos_[produced] || rs != g.sin_[produced]) {
            if (first_bad < 0) first_bad = produced;
        }
        if (produced == 0 && (rc != g.cos_[0] || rs != g.sin_[0]))
            align_ok = false;
        ++produced;
    }

    char msg[160];
    std::snprintf(msg, sizeof msg, "all %d phases produced (watchdog %d)",
                  NP, WATCHDOG_CYCLES);
    check(produced == NP, msg);
    std::snprintf(msg, sizeof msg,
                  "A: RTL bit-exact to golden over all phases (first bad %d)",
                  first_bad);
    check(first_bad < 0 && produced == NP, msg);
    std::snprintf(msg, sizeof msg,
                  "E: fill == %d (measured %d) and result 0 is phase 0",
                  LATENCY, vld_o_cyc - vld_i_cyc);
    check(vld_o_cyc - vld_i_cyc == LATENCY && align_ok, msg);
    check(contig_ok, "T: vld_o contiguous at 1 sample/clk once filled");
}

// B, C, F: properties of the model's output table. Valid for the RTL too only
// because A already proved the RTL produces that same table.
static void check_invariants(const Golden &g) {
    std::printf("\n=== B / C / F: accuracy and invariants ===\n");
    const double TWO_PI = 6.283185307179586;
    const double scale = (double)(1 << FRAC);
    double max_err = 0.0, max_unit = 0.0;
    int max_err_phase = 0;

    for (int p = 0; p < NP; ++p) {
        double th = (double)p / NP * TWO_PI;
        double gc = g.cos_[p] / scale, gs = g.sin_[p] / scale;
        double e = std::fabs(gc - std::cos(th));
        double f = std::fabs(gs - std::sin(th));
        if (f > e) e = f;
        if (e > max_err) { max_err = e; max_err_phase = p; }
        double mag = (double)g.cos_[p] * g.cos_[p] + (double)g.sin_[p] * g.sin_[p];
        double uerr = std::fabs(mag / (scale * scale) - 1.0);
        if (uerr > max_unit) max_unit = uerr;
    }
    char msg[160];
    std::snprintf(msg, sizeof msg,
                  "B: max |error vs libm| <= 2**-14 (measured %.3e @ %d)",
                  max_err, max_err_phase);
    check(max_err <= ACC_BOUND, msg);
    std::snprintf(msg, sizeof msg,
                  "C: max |cos^2+sin^2-1| <= 2**-13 (measured %.3e)", max_unit);
    check(max_unit <= UNIT_BOUND, msg);

    // F: symmetry over the table. +90 and +180 change only the quadrant (exact
    // negate/swap of the same x,y); -t folds to a different remainder (bounded).
    const int q90 = 1 << (NA_BITS - 2), q180 = 1 << (NA_BITS - 1);
    int d90 = 0, d180 = 0, dneg = 0;
    for (int p = 0; p < NP; ++p) {
        int c = g.cos_[p], s = g.sin_[p];
        int c9 = (p + q90) & (NP - 1), c8 = (p + q180) & (NP - 1), cn = (-p) & (NP - 1);
        int e90 = g.sin_[c9] - c;   if (e90 < 0) e90 = -e90;
        int t90 = g.cos_[c9] + s;   if (t90 < 0) t90 = -t90;
        int e180 = g.sin_[c8] + s;  if (e180 < 0) e180 = -e180;
        int t180 = g.cos_[c8] + c;  if (t180 < 0) t180 = -t180;
        int eneg = g.sin_[cn] + s;  if (eneg < 0) eneg = -eneg;
        int tneg = g.cos_[cn] - c;  if (tneg < 0) tneg = -tneg;
        if (e90  > d90)  d90  = e90;
        if (t90  > d90)  d90  = t90;
        if (e180 > d180) d180 = e180;
        if (t180 > d180) d180 = t180;
        if (eneg > dneg) dneg  = eneg;
        if (tneg > dneg) dneg  = tneg;
    }
    std::snprintf(msg, sizeof msg,
                  "F: sin(t+90)=cos(t), cos(t+90)=-sin(t) exact (%d counts)", d90);
    check(d90 == 0, msg);
    std::snprintf(msg, sizeof msg, "F: t+180 negation exact (%d counts)", d180);
    check(d180 == 0, msg);
    std::snprintf(msg, sizeof msg,
                  "F: sin(-t)=-sin(t), cos(-t)=cos(t) within %d (measured %d)",
                  NEGATION_CAP, dneg);
    check(dneg <= NEGATION_CAP, msg);

    if (g_verbose)
        std::printf("\ninfo: max err %.6e @ phase %d, max unit %.6e\n",
                    max_err, max_err_phase, max_unit);
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    for (int i = 1; i < argc; ++i)
        if (std::strcmp(argv[i], "-v") == 0) g_verbose = true;

    Golden gold;
    if (check(load_golden("sim/cordic_golden.hex", gold),
              "golden file present, header matches tb, 2**16 rows")) {
        check_cardinals(gold);
        check_pipeline(gold);
        check_invariants(gold);
    }

    std::printf("\nSummary: %d failed out of %d checks\n", g_fail_count, g_checks_run);
    return g_fail_count ? 1 : 0;
}
