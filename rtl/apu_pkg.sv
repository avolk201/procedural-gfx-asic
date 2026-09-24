/* verilator lint_off UNUSEDPARAM */
package apu_pkg;
    // VGA 640x480@60Hz timing constants, from the VESA DMT standard.
    // All values in pixel clocks. Base constants come first and derived
    // totals last: package items need declare-before-use (B8). Verilator
    // accepts the reverse order, stricter parsers do not.
    localparam int unsigned ACTIVE_W = 640;
    localparam int unsigned ACTIVE_H = 480;
    localparam int unsigned H_FP     = 16;
    localparam int unsigned HSYNC_WIDTH = 96;
    localparam int unsigned H_BP     = 48;
    localparam int unsigned V_FP     = 10;
    localparam int unsigned VSYNC_WIDTH = 2;
    localparam int unsigned V_BP     = 33;
    localparam int unsigned SCENE_COLORBARS = 0;
    localparam int unsigned SCENE_PLASMA = 1;

    localparam int unsigned H_TOTAL = ACTIVE_W + H_FP + HSYNC_WIDTH + H_BP;
    localparam int unsigned V_TOTAL = ACTIVE_H + V_FP + VSYNC_WIDTH + V_BP;

    typedef logic [7:0] rgb332_t;
    typedef logic [9:0] coord_t;
endpackage
/* verilator lint_on UNUSEDPARAM */
