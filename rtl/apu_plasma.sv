// rtl/apu_plasma.sv
// Generates a plasma effect in 640x480@60Hz VGA timing
// Uses a CORDIC to compute sin/cos of a moving phase.

module apu_plasma (
    input  logic             clk_pix_i,
    input  logic             rst_n_i,
    input  logic             de_i,
    input  logic             sof_i,
    input  apu_pkg::coord_t  x_i,
    input  apu_pkg::coord_t  y_i,
    output logic             de_o,
    output apu_pkg::rgb332_t rgb_o
);

    logic [15:0] frame_x;
    logic [15:0] frame_y;
    logic [15:0] phase_x;
    logic [15:0] phase_y;

    logic                    cordic_x_vld;
    logic signed [23:0]      cordic_x_sin;
    logic signed [23:0]      cordic_x_cos;
    logic                    cordic_y_vld;
    logic signed [23:0]      cordic_y_sin;
    logic signed [23:0]      cordic_y_cos;

    logic signed [24:0] red_wave;
    logic signed [24:0] green_wave;
    logic signed [24:0] blue_wave;

    // wave_to_3/2 keep only the most-significant bits of a 25-bit biased sum;
    // the discarded low bits are sub-LSB colour detail by design, so the
    // partial-read warning is waived here (same idiom as the SYNCASYNCNET and
    // UNUSEDPARAM waivers used elsewhere in this tree).
    /* verilator lint_off UNUSEDSIGNAL */
    function automatic logic [2:0] wave_to_3(input logic signed [24:0] wave);
        logic signed [24:0] biased;
        begin
            biased = wave + 25'sd8388608;
            wave_to_3 = biased[23:21];
        end
    endfunction

    function automatic logic [1:0] wave_to_2(input logic signed [24:0] wave);
        logic signed [24:0] biased;
        begin
            biased = wave + 25'sd8388608;
            wave_to_2 = biased[23:22];
        end
    endfunction
    /* verilator lint_on UNUSEDSIGNAL */

    // 16-bit phase arithmetic on purpose: the product and the per-frame offset
    // sum wrap at 2**16, and 2**16 phase codes are exactly one turn (see
    // apu_cordic), so the wrap is the intended mod-1-turn, not a lost carry.
    assign phase_x = (x_i * 16'd102) + frame_x;
    assign phase_y = (y_i * 16'd137) + frame_y;

    apu_cordic u_cordic_x (
        .clk_i   (clk_pix_i),
        .rst_n_i (rst_n_i),
        .vld_i   (de_i),
        .phase_i (phase_x),
        .vld_o   (cordic_x_vld),
        .cos_o   (cordic_x_cos),
        .sin_o   (cordic_x_sin)
    );

    apu_cordic u_cordic_y (
        .clk_i   (clk_pix_i),
        .rst_n_i (rst_n_i),
        .vld_i   (de_i),
        .phase_i (phase_y),
        .vld_o   (cordic_y_vld),
        .cos_o   (cordic_y_cos),
        .sin_o   (cordic_y_sin)
    );

    // Each channel is a different phase relationship of the two sine waves.
    // Bias signed Q2.22 sums into an unsigned range before reducing to RGB332.
    assign red_wave   = $signed(cordic_x_sin) + $signed(cordic_y_sin);
    assign green_wave = $signed(cordic_x_sin) - $signed(cordic_y_sin);
    assign blue_wave  = -$signed(cordic_x_cos) + $signed(cordic_y_cos);
    assign rgb_o = {wave_to_3(red_wave), wave_to_3(green_wave), wave_to_2(blue_wave)};
    assign de_o = cordic_x_vld & cordic_y_vld;

    // Two offsets advancing at different rates: the x and y gratings drift
    // against each other, so the interference morphs (boils) instead of sliding
    // rigidly. 257 and 163 are odd and coprime, so the pattern has a long
    // period before it repeats. Async reset matches the scenes and the CORDIC.
    always_ff @(posedge clk_pix_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            frame_x <= '0;
            frame_y <= '0;
        end else if (sof_i) begin
            frame_x <= frame_x + 16'd257;
            frame_y <= frame_y + 16'd163;
        end
    end

endmodule
