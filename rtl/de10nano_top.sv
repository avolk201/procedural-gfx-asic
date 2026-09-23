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

    // POR: ADV7513 Programming Guide (Rev B) 4.1 requires waiting 200 ms after
    // supplies are stable before I2C, so the ADV7513 can latch its PD/AD address
    // strap. Hold reset for 2^24 cycles = 335 ms at 50 MHz.
    /* verilator lint_off SYNCASYNCNET */
    logic [24:0] rst_cnt;
    /* verilator lint_on SYNCASYNCNET */
    logic sys_rst_n;
    logic rst_50m_n;

    always_ff @(posedge clk_50m_i or negedge btn_n_i[0]) begin
        if (!btn_n_i[0]) begin
            rst_cnt <= '0;
        end else if (!rst_cnt[24]) begin
            rst_cnt <= rst_cnt + 1'b1;
        end
    end
    assign sys_rst_n = rst_cnt[24];

    sync_reset u_sync_rst (
        .clk_i      (clk_50m_i),
        .rst_n_i    (sys_rst_n),
        .rst_sync_n_o (rst_50m_n)
    );

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
        .rst_n_i    (rst_50m_n),
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
        .rst_n_i    (rst_50m_n),
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

    sync_reset u_sync_rst_pix (
        .clk_i      (clk_pix),
        .rst_n_i    (sys_rst_n && pll_locked),
        .rst_sync_n_o(pix_rst_n)
    );

    // Diagnostics: LED0 config done, LED1 config error, LED2 PLL lock,
    // LED3 "pipeline alive": ~1 Hz blink proves pixel clock running, reset
    // released, and frames completing (sof pulses crossing to 50 MHz).
    assign led_o[0]   = cfg_done;
    assign led_o[1]   = cfg_error;
    assign led_o[2]   = pll_locked;
    assign led_o[3]   = led_alive;
    assign led_o[7:4] = '0;

    // Frame-rate blinker. sof toggles a flop in the pixel domain; a toggle
    // pair is the metastability-tolerant way to cross an event to a faster
    // clock domain: sync the toggle with two flops, edge-detect on the
    // synchronized copies. 60 frames/s, every 30th edge re-toggles, so the
    // LED inverts at ~1 Hz.
    logic pix_alive_tgl;
    always_ff @(posedge clk_pix or negedge pix_rst_n) begin
        if (!pix_rst_n)        pix_alive_tgl <= 1'b0;
        else if (apu_sof)      pix_alive_tgl <= ~pix_alive_tgl;
    end

    (* syncthreads = "true" *) logic [1:0] tgl_sync;
    logic [4:0] alive_div;
    logic led_alive;
    always_ff @(posedge clk_50m_i or negedge rst_50m_n) begin
        if (!rst_50m_n) begin
            tgl_sync   <= '0;
            alive_div  <= '0;
            led_alive  <= 1'b0;
        end else begin
            tgl_sync <= {tgl_sync[0], pix_alive_tgl};
            if (tgl_sync[1] ^ tgl_sync[0]) begin
                if (alive_div == 5'd29) begin
                    alive_div <= '0;
                    led_alive <= ~led_alive;
                end else begin
                    alive_div <= alive_div + 1'b1;
                end
            end
        end
    end

    apu_pkg::rgb332_t apu_rgb;
    logic apu_sof;
    logic _unused_sol;

    apu_top u_apu (
        .clk_pix_i (clk_pix),
        .rst_n_i   (pix_rst_n),
        .hsync_o   (hdmi_tx_hs),
        .vsync_o   (hdmi_tx_vs),
        .sof_o     (apu_sof),
        .sol_o     (_unused_sol),
        .de_o      (hdmi_tx_de),
        .rgb_o     (apu_rgb)
    );

    // ADV7513 input pin map per Programming Guide Table 16 (RGB 4:4:4,
    // Input ID 0): D[23:16]=R, D[15:8]=G, D[7:0]=B. Bit-replicate RGB332
    // to fill each 8-bit channel's full range.
    assign hdmi_tx_d[23:16] = {apu_rgb[7:5], apu_rgb[7:5], apu_rgb[7:6]};
    assign hdmi_tx_d[15:8]  = {apu_rgb[4:2], apu_rgb[4:2], apu_rgb[4:3]};
    assign hdmi_tx_d[7:0]   = {4{apu_rgb[1:0]}};

    logic _unused_ok = &{1'b0, btn_n_i[1], _unused_sol};

endmodule
