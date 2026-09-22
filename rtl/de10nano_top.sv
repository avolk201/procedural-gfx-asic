// rtl/de10nano_top.sv
// Board top-level for DE10-Nano: connects PLL, pixel pipeline, and ADV7513 I2C
// config to physical pins. Exposes open-drain pads with tri-states (D4).

module de10nano_top (
    input  logic        clk_50m_i,
    input  logic [1:0]  btn_n_i,
    output logic [7:0]  led_o,
    output logic        hdmi_tx_clk,
    output logic        hdmi_tx_de,
    output logic        hdmi_tx_hs,
    output logic        hdmi_tx_vs,
    output logic [23:0] hdmi_tx_d,
    inout  wire         hdmi_i2c_scl,
    inout  wire         hdmi_i2c_sda
);

    // POR: holds reset low for ~1.3ms (2^15 clocks at 50MHz) after power-up
    /* verilator lint_off SYNCASYNCNET */
    logic [15:0] rst_cnt;
    /* verilator lint_on SYNCASYNCNET */
    logic sys_rst_n;

    always_ff @(posedge clk_50m_i or negedge btn_n_i[0]) begin
        if (!btn_n_i[0]) begin
            rst_cnt <= '0;
        end else if (!rst_cnt[15]) begin
            rst_cnt <= rst_cnt + 1'b1;
        end
    end
    assign sys_rst_n = rst_cnt[15];

    // Pixel clock: 50 MHz -> 25.175 MHz for 640x480@60 VESA timing
    logic clk_pix;
    logic pll_locked;
    logic pix_rst_n;

    pll_25m u_pll (
        .refclk   (clk_50m_i),
        .rst      (!btn_n_i[0]),
        .outclk_0 (clk_pix),
        .locked   (pll_locked)
    );

    // Gate video pipeline until PLL locks and power rails stabilize
    assign pix_rst_n   = sys_rst_n && pll_locked;
    assign hdmi_tx_clk = clk_pix;

    // Open-drain I2C bus driver (D4): line is pulled low on oe, floats to pull-up otherwise
    logic sda_oe, scl_oe;
    logic sda_in, scl_in;

    assign hdmi_i2c_sda = sda_oe ? 1'b0 : 1'bz;
    assign sda_in       = hdmi_i2c_sda;
    assign hdmi_i2c_scl = scl_oe ? 1'b0 : 1'bz;
    assign scl_in       = hdmi_i2c_scl;

    logic       cfg_start;
    logic [6:0] cfg_dev_addr;
    logic [7:0] cfg_reg_addr;
    logic [7:0] cfg_data;
    logic       i2c_busy;
    logic       i2c_done;
    logic       i2c_ack_err;
    logic       cfg_done;
    logic       cfg_error;

    adv7513_config u_cfg (
        .clk_i      (clk_50m_i),
        .rst_n_i    (sys_rst_n),
        .busy_i     (i2c_busy),
        .done_i     (i2c_done),
        .ack_err_i  (i2c_ack_err),
        .start_o    (cfg_start),
        .dev_addr_o (cfg_dev_addr),
        .reg_addr_o (cfg_reg_addr),
        .data_o     (cfg_data),
        .done_o     (cfg_done),
        .error_o    (cfg_error)
    );

    i2c_controller u_i2c (
        .clk_i      (clk_50m_i),
        .rst_n_i    (sys_rst_n),
        .start_i    (cfg_start),
        .dev_addr_i (cfg_dev_addr),
        .reg_addr_i (cfg_reg_addr),
        .data_i     (cfg_data),
        .busy_o     (i2c_busy),
        .done_o     (i2c_done),
        .ack_err_o  (i2c_ack_err),
        .sda_i      (sda_in),
        .scl_i      (scl_in),
        .sda_oe_o   (sda_oe),
        .scl_oe_o   (scl_oe)
    );

    // Diagnostics: verify power-up, PLL lock, and I2C completion before HDMI syncs
    assign led_o[0]   = cfg_done;
    assign led_o[1]   = cfg_error;
    assign led_o[2]   = pll_locked;
    assign led_o[3]   = hdmi_tx_vs;
    assign led_o[7:4] = '0;

    apu_pkg::rgb332_t apu_rgb;
    logic _unused_sof, _unused_sol;

    apu_top u_apu (
        .clk_pix_i (clk_pix),
        .rst_n_i   (pix_rst_n),
        .hsync_o   (hdmi_tx_hs),
        .vsync_o   (hdmi_tx_vs),
        .sof_o     (_unused_sof),
        .sol_o     (_unused_sol),
        .de_o      (hdmi_tx_de),
        .rgb_o     (apu_rgb)
    );

    // Style 1 bus pinout: replicate upper bits to fill full 8-bit dynamic range
    assign hdmi_tx_d[23:16] = {apu_rgb[7:5], apu_rgb[7:5], apu_rgb[7:6]};
    assign hdmi_tx_d[15:8]  = {apu_rgb[4:2], apu_rgb[4:2], apu_rgb[4:3]};
    assign hdmi_tx_d[7:0]   = {4{apu_rgb[1:0]}};

    logic _unused_ok = &{1'b0, btn_n_i[1], _unused_sof, _unused_sol};

endmodule
