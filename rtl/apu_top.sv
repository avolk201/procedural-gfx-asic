// rst_n_i comes from the board's sync_reset (async assert, sync deassert), but
// is flopped asynchronously by the scenes and synchronously by apu_cordic. That
// mixed use is intentional; same scoped waiver as de10nano_top.rst_cnt.
/* verilator lint_off SYNCASYNCNET */
module apu_top #(
    parameter int unsigned SCENE = apu_pkg::SCENE_COLORBARS
) (
    input  logic             clk_pix_i,
    input  logic             rst_n_i,
    
    output logic             hsync_o,
    output logic             vsync_o,
    output logic             sof_o,
    output logic             sol_o,
    output logic             de_o,      // from the selected scene, each aligned to its own rgb_o
    output apu_pkg::rgb332_t rgb_o
);

    logic             vga_de;
    apu_pkg::coord_t  vga_x;
    apu_pkg::coord_t  vga_y;

    logic             cb_de;
    logic             pl_de;
    apu_pkg::rgb332_t cb_rgb;
    apu_pkg::rgb332_t pl_rgb;

    apu_vga_timing u_vga (
        .clk_pix_i (clk_pix_i),
        .rst_n_i   (rst_n_i),
        .hsync_o   (hsync_o),
        .vsync_o   (vsync_o),
        .sof_o     (sof_o),
        .sol_o     (sol_o),
        .de_o      (vga_de),
        .x_o       (vga_x),
        .y_o       (vga_y)
    );

    apu_colorbars u_colorbars (
        .clk_pix_i (clk_pix_i),
        .rst_n_i   (rst_n_i),
        .de_i      (vga_de),
        .x_i       (vga_x),
        .y_i       (vga_y),
        .de_o      (cb_de),
        .rgb_o     (cb_rgb)
    );

    apu_plasma u_plasma (
        .clk_pix_i (clk_pix_i),
        .rst_n_i   (rst_n_i),
        .de_i      (vga_de),
        .sof_i     (sof_o),
        .x_i       (vga_x),
        .y_i       (vga_y),
        .de_o      (pl_de),
        .rgb_o     (pl_rgb)
    );

    // SCENE is a constant at elaboration, so Quartus prunes the unselected
    // branch and the board pays area for exactly one scene.
    assign de_o  = (SCENE == apu_pkg::SCENE_PLASMA) ? pl_de  : cb_de;
    assign rgb_o = (SCENE == apu_pkg::SCENE_PLASMA) ? pl_rgb : cb_rgb;

endmodule
/* verilator lint_on SYNCASYNCNET */
