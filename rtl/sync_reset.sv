// rtl/sync_reset.sv
// asserts propagate instantly; deassertion is synchronized through two flops so the release can't emerge metastable.
// Instantiated once per clock domain at the boundary module; see de10nano_top.

module sync_reset (
    input  logic clk_i,
    input  logic rst_n_i,
    output logic rst_sync_n_o
);

(* syncthreads = "true" *)
/* verilator lint_off SYNCASYNCNET */
logic [1:0] d;

always_ff @(posedge clk_i or negedge rst_n_i) begin
    if (!rst_n_i) begin
        d <= 2'b00;
    end else begin
        d <= {d[0], 1'b1};
    end
end
/* verilator lint_on SYNCASYNCNET */
assign rst_sync_n_o = d[1];
endmodule
