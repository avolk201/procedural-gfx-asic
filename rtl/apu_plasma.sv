// rtl/apu_plasma.sv
// Plasma for 640x480@60Hz: ONE shared field F = sin_x + sin_y + sin_z from
// three non-collinear CORDIC gratings, hue-mapped to RGB. A single field keeps
// the pattern coherent (it boils as one surface); per-channel grating pairs
// made it look like three independent slides. Three non-collinear gratings are
// what makes it boil at all: a sum of an x- and a y-grating is provably a pure
// translation (a*dx=fx, b*dy=fy always solves), so it can only scroll.

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

    // Grating spatial frequencies and per-frame phase drift. Mutually coprime
    // drift rates; with these vectors the composite is never a translation.
    localparam logic [15:0] KX = 102, KY = 137, KZ = 110;
    localparam logic [15:0] DX = 257, DY = 163, DZ = 97;

    logic [15:0] frame_x, frame_y, frame_z;
    logic [15:0] phase_x, phase_y, phase_z;
    logic [15:0] sum_xy;

    logic               cordic_x_vld, cordic_y_vld, cordic_z_vld;
    logic signed [23:0] cordic_x_sin, cordic_x_cos;
    logic signed [23:0] cordic_y_sin, cordic_y_cos;
    logic signed [23:0] cordic_z_sin, cordic_z_cos;

    // Shared field. Each sin is Q2.22, so F is within +-3*2**22; the 6-segment
    // hue wheel below maps that range to a full RGB cycle.
    logic signed [24:0] F;
    assign F = $signed(cordic_x_sin) + $signed(cordic_y_sin) + $signed(cordic_z_sin);

    // Integer 6-segment hue wheel. Fn = (F/64 + 3*2**16) in [0, 6*65536], split
    // into segment index (0..5) and fraction. q3/q2 are the fraction scaled to
    // 3 and 2 bits. Offsets 0, 1/3, 2/3 of the cycle land on red/green/blue.
    logic [18:0] Fn;
    assign Fn = 19'((F >>> 6) + 25'sd196608);
    logic [2:0]  seg;
    assign seg = (Fn >= 19'd393216) ? 3'd5 : Fn[18:16];
    logic [2:0] q3;
    logic [1:0] q2;
    assign q3 = Fn[15:13];
    assign q2 = Fn[15:14];

    logic [2:0] r3, g3;
    logic [1:0] b2;
    always_comb begin
        case (seg)
            3'd0:    begin r3 = 3'd7;   g3 = q3;     b2 = 2'd0;   end
            3'd1:    begin r3 = 3'd7 - q3; g3 = 3'd7;     b2 = 2'd0;   end
            3'd2:    begin r3 = 3'd0;   g3 = 3'd7;   b2 = q2;     end
            3'd3:    begin r3 = 3'd0;     g3 = 3'd7 - q3; b2 = 2'd3;   end
            3'd4:    begin r3 = q3;     g3 = 3'd0;   b2 = 2'd3;   end
            default: begin r3 = 3'd7;     g3 = 3'd0;     b2 = 2'd3 - q2; end
        endcase
    end
    assign rgb_o = {r3, g3, b2};

    // 16-bit phase arithmetic: products and offsets wrap at 2**16 = one turn
    // (see apu_cordic). sum_xy widened first: x_i+y_i exceeds coord_t's 10 bits.
    assign phase_x = (x_i * KX) + frame_x;
    assign phase_y = (y_i * KY) + frame_y;
    assign sum_xy  = {6'd0, x_i} + {6'd0, y_i};
    assign phase_z = (sum_xy * KZ) + frame_z;

    apu_cordic u_cordic_x (
        .clk_i (clk_pix_i), .rst_n_i (rst_n_i), .vld_i (de_i),
        .phase_i (phase_x), .vld_o (cordic_x_vld),
        .cos_o (cordic_x_cos), .sin_o (cordic_x_sin)
    );
    apu_cordic u_cordic_y (
        .clk_i (clk_pix_i), .rst_n_i (rst_n_i), .vld_i (de_i),
        .phase_i (phase_y), .vld_o (cordic_y_vld),
        .cos_o (cordic_y_cos), .sin_o (cordic_y_sin)
    );
    apu_cordic u_cordic_z (
        .clk_i (clk_pix_i), .rst_n_i (rst_n_i), .vld_i (de_i),
        .phase_i (phase_z), .vld_o (cordic_z_vld),
        .cos_o (cordic_z_cos), .sin_o (cordic_z_sin)
    );

    // de_o is the shared CORDIC valid: de_i delayed by the pipeline, 19 clk
    // at system level (D18; sim_cordic's fill of 18 counts iterations).
    assign de_o = cordic_x_vld & cordic_y_vld & cordic_z_vld;

    // Cosines are unused here (the field sums sines only); fold them into the
    // repo's standard unused-signal sink so -Wall stays clean.
    logic _unused_ok = &{1'b0, cordic_x_cos, cordic_y_cos, cordic_z_cos};

    always_ff @(posedge clk_pix_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            frame_x <= '0;
            frame_y <= '0;
            frame_z <= '0;
        end else if (sof_i) begin
            frame_x <= frame_x + DX;
            frame_y <= frame_y + DY;
            frame_z <= frame_z + DZ;
        end
    end

endmodule
