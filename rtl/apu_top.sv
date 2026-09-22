module apu_top (
    input  logic             clk_pix_i,
    input  logic             rst_n_i,
    
    output logic             hsync_o,
    output logic             vsync_o,
    output logic             sof_o,
    output logic             sol_o,
    output logic             de_o,      // delayed by scene generator to match registered rgb_o
    output apu_pkg::rgb332_t rgb_o
);

    logic             vga_de;
    apu_pkg::coord_t  vga_x;
    apu_pkg::coord_t  vga_y;

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
        .de_o      (de_o),
        .rgb_o     (rgb_o)
    );

endmodule
