// apu_cordic - fixed-point CORDIC rotation-mode sine/cosine generator.
// Contract (mirrors tb/cordic_golden.py exactly):
//   phase_i = angle / 2pi in turns, unsigned Q0.16, wraps mod 1.
//   cos_o/sin_o = signed Q2.22, value = int / 2**22. |result| <= 1.
//   latency = 18 clk, throughput 1 sample/clk. The number is not asserted
//   here; tb/sim_cordic.cpp measures the fill delay and checks it, so this
//   comment cannot rot away from the RTL.
//   vld_o[p] is high iff out_* corresponds to phase_i[p - 18].
// Bit-exactness depends on signed >>> and the z==0 positive tie-break; see the
// golden model. Accuracy vs libm <= 2**-14 (measured 3.17e-05); that bound is
// checked in tb/sim_cordic.cpp, not asserted by this module.
module apu_cordic #(
    parameter int unsigned N  = 16,
    parameter int unsigned W  = 24,
    parameter int unsigned FZ = 24,
    parameter int unsigned NA = 16
)(
    input  logic             clk_i,
    input  logic             rst_n_i,
    input  logic             vld_i,
    input  logic [NA-1:0]    phase_i,
    output logic             vld_o,
    output logic signed [W-1:0] cos_o,
    output logic signed [W-1:0] sin_o
);

    localparam int unsigned AZ = FZ + 1;
    localparam logic signed [W-1:0] X0 = 24'sd2547003;

    logic signed [W-1:0] x_pipe [0:N];
    logic signed [W-1:0] y_pipe [0:N];
    logic signed [AZ-1:0] z_pipe [0:N];
    logic [1:0] quadrant_pipe [0:N];
    logic valid_pipe [0:N];
    logic signed [W-1:0] cos_mid, sin_mid;
    logic vld_mid;
    logic [1:0] fold_quadrant;
    logic signed [AZ-1:0] fold_z;
    logic signed [AZ-1:0] fold_remainder;

    always_comb begin
        fold_remainder = {{(AZ - NA + 2){1'b0}}, phase_i[NA-3:0]};
        fold_quadrant = phase_i[NA-1:NA-2];
        if (fold_remainder >= (1 << (NA - 3))) begin
            fold_remainder = fold_remainder - (1 << (NA - 2));
            fold_quadrant = fold_quadrant + 1'b1;
        end
        fold_z = fold_remainder <<< (FZ - NA);
    end

    function automatic logic signed [AZ-1:0] atan_value(input int unsigned index);
        case (index)
            0: atan_value = 25'sd2097152;
            1: atan_value = 25'sd1238021;
            2: atan_value = 25'sd654136;
            3: atan_value = 25'sd332050;
            4: atan_value = 25'sd166669;
            5: atan_value = 25'sd83416;
            6: atan_value = 25'sd41718;
            7: atan_value = 25'sd20860;
            8: atan_value = 25'sd10430;
            9: atan_value = 25'sd5215;
            10: atan_value = 25'sd2608;
            11: atan_value = 25'sd1304;
            12: atan_value = 25'sd652;
            13: atan_value = 25'sd326;
            14: atan_value = 25'sd163;
            default: atan_value = 25'sd81;
        endcase
    endfunction

    integer i;
    always_ff @(posedge clk_i) begin
        if (!rst_n_i) begin
            vld_o <= 1'b0;
            cos_o <= '0;
            sin_o <= '0;
            vld_mid <= 1'b0;
            cos_mid <= '0;
            sin_mid <= '0;
            for (i = 0; i <= N; i = i + 1) begin
                x_pipe[i] <= '0;
                y_pipe[i] <= '0;
                z_pipe[i] <= '0;
                quadrant_pipe[i] <= '0;
                valid_pipe[i] <= 1'b0;
            end
        end else begin
            quadrant_pipe[0] <= fold_quadrant;
            x_pipe[0] <= X0;
            y_pipe[0] <= '0;
            z_pipe[0] <= fold_z;
            valid_pipe[0] <= vld_i;

            for (i = 0; i < N; i = i + 1) begin
                quadrant_pipe[i + 1] <= quadrant_pipe[i];
                valid_pipe[i + 1] <= valid_pipe[i];
                if (z_pipe[i][AZ-1]) begin
                    x_pipe[i + 1] <= x_pipe[i] + (y_pipe[i] >>> i);
                    y_pipe[i + 1] <= y_pipe[i] - (x_pipe[i] >>> i);
                    z_pipe[i + 1] <= z_pipe[i] + atan_value(i);
                end else begin
                    x_pipe[i + 1] <= x_pipe[i] - (y_pipe[i] >>> i);
                    y_pipe[i + 1] <= y_pipe[i] + (x_pipe[i] >>> i);
                    z_pipe[i + 1] <= z_pipe[i] - atan_value(i);
                end
            end

            vld_mid <= valid_pipe[N];
            case (quadrant_pipe[N])
                2'd0: begin cos_mid <= x_pipe[N];  sin_mid <= y_pipe[N];  end
                2'd1: begin cos_mid <= -y_pipe[N]; sin_mid <= x_pipe[N];  end
                2'd2: begin cos_mid <= -x_pipe[N]; sin_mid <= -y_pipe[N]; end
                default: begin cos_mid <= y_pipe[N]; sin_mid <= -x_pipe[N]; end
            endcase
            vld_o <= vld_mid;
            cos_o <= cos_mid;
            sin_o <= sin_mid;
        end
    end

endmodule
