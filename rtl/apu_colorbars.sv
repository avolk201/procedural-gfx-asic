module apu_colorbars (
    input  logic               clk_pix_i,
    input  logic               rst_n_i,
    input  logic               de_i,
    input  apu_pkg::coord_t    x_i,
    input  apu_pkg::coord_t    y_i,       // unused: bars are vertical; kept for the scene interface
    output logic               de_o,      // delayed DE, aligned with rgb_o
    output apu_pkg::rgb332_t   rgb_o
);

    localparam apu_pkg::rgb332_t WHITE   = 8'hFF;
    localparam apu_pkg::rgb332_t YELLOW  = 8'hFC;
    localparam apu_pkg::rgb332_t CYAN    = 8'h1F;
    localparam apu_pkg::rgb332_t GREEN   = 8'h1C;
    localparam apu_pkg::rgb332_t MAGENTA = 8'hE3;
    localparam apu_pkg::rgb332_t RED     = 8'hE0;
    localparam apu_pkg::rgb332_t BLUE    = 8'h03;
    localparam apu_pkg::rgb332_t BLACK   = 8'h00;
    apu_pkg::rgb332_t color_next;

    always_ff @(posedge clk_pix_i or negedge rst_n_i) begin
        if (!rst_n_i) begin
            de_o  <= 1'b0;
            rgb_o <= '0;
        end else begin
            de_o  <= de_i;              // delay de by 1 cycle to match rgb_o
            rgb_o <= color_next;
        end
    end

    always_comb begin
        if      (x_i <  80) color_next = WHITE;
        else if (x_i < 160) color_next = YELLOW;
        else if (x_i < 240) color_next = CYAN;
        else if (x_i < 320) color_next = GREEN;
        else if (x_i < 400) color_next = MAGENTA;
        else if (x_i < 480) color_next = RED;
        else if (x_i < 560) color_next = BLUE;
        else color_next = BLACK;
    end

    logic _unused_ok = &{1'b0, y_i};

endmodule
