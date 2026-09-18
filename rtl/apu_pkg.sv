package apu_pkg;
    // VGA 640x480@60Hz timing constants
    // Derived from VESA DMT standard. All values in pixel clocks.
    // Derived totals — every base constant contributes
    localparam int unsigned H_TOTAL = ACTIVE_W + H_FP + HSYNC_WIDTH + H_BP;
    localparam int unsigned V_TOTAL = ACTIVE_H + V_FP + VSYNC_WIDTH + V_BP;
    localparam int unsigned HSYNC_WIDTH = 96;
    localparam int unsigned VSYNC_WIDTH = 2;

    localparam int unsigned ACTIVE_W = 640;
    localparam int unsigned ACTIVE_H = 480;
    localparam int unsigned H_FP     = 16;
    localparam int unsigned H_BP     = 48;
    localparam int unsigned V_FP     = 10;
    localparam int unsigned V_BP     = 33;

    typedef logic [7:0] rgb332_t;
    typedef logic [9:0] coord_t;
endpackage
