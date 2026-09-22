// tb/tb_adv7513_config.sv
// Integration wrapper: stitches adv7513_config to i2c_controller and exposes
// open-drain pad controls to sim_adv7513_config.cpp (D4).

module tb_adv7513_config #(
    parameter int unsigned CLK_DIV = 250
)(
    input  logic clk_i,
    input  logic rst_n_i,
    input  logic sda_i,
    input  logic scl_i,
    output logic sda_oe_o,
    output logic scl_oe_o,
    output logic done_o,
    output logic error_o
);

    logic       start;
    logic [6:0] dev_addr;
    logic [7:0] reg_addr;
    logic [7:0] data;
    logic       busy;
    logic       done;
    logic       ack_err;

    adv7513_config u_cfg (
        .clk_i      (clk_i),
        .rst_n_i    (rst_n_i),
        .busy_i     (busy),
        .done_i     (done),
        .ack_err_i  (ack_err),
        .start_o    (start),
        .dev_addr_o (dev_addr),
        .reg_addr_o (reg_addr),
        .data_o     (data),
        .done_o     (done_o),
        .error_o    (error_o)
    );

    i2c_controller #(
        .CLK_DIV(CLK_DIV)
    ) u_i2c (
        .clk_i      (clk_i),
        .rst_n_i    (rst_n_i),
        .start_i    (start),
        .dev_addr_i (dev_addr),
        .reg_addr_i (reg_addr),
        .data_i     (data),
        .busy_o     (busy),
        .done_o     (done),
        .ack_err_o  (ack_err),
        .sda_i      (sda_i),
        .scl_i      (scl_i),
        .sda_oe_o   (sda_oe_o),
        .scl_oe_o   (scl_oe_o)
    );

endmodule
