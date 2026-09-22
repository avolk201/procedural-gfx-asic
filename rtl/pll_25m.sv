// rtl/pll_25m.sv
// Generates 25.175 MHz pixel clock from 50.0 MHz oscillator.
// Uses altera_pll for Quartus synthesis; falls back to behavioral model in Verilator.

module pll_25m (
    input  logic refclk,
    input  logic rst,
    output logic outclk_0,
    output logic locked
);

`ifdef VERILATOR
    // Behavioral clock divider for local lint and simulation
    always_ff @(posedge refclk or posedge rst) begin
        if (rst) begin
            outclk_0 <= 1'b0;
            locked   <= 1'b0;
        end else begin
            outclk_0 <= ~outclk_0;
            locked   <= 1'b1;
        end
    end
`else
    // Hardware PLL instance for Cyclone V (Quartus synthesis)
    altera_pll #(
        .fractional_vco_multiplier("false"),
        .reference_clock_frequency("50.0 MHz"),
        .operation_mode("direct"),
        .number_of_clocks(1),
        .output_clock_frequency0("25.175000 MHz"),
        .phase_shift0("0 ps"),
        .duty_cycle0(50),
        .pll_type("General"),
        .pll_subtype("General")
    ) altera_pll_i (
        .rst    (rst),
        .outclk (outclk_0),
        .locked (locked),
        .fbclk  (1'b0),
        .refclk (refclk)
    );
`endif

endmodule
